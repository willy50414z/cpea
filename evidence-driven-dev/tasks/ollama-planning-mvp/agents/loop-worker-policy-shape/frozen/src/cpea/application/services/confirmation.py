"""Short-lived capability registry. Graph checkpoints hold the actual draft."""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock, RLock, Thread
import time
import weakref

from cpea.application.models.confirmation import Clarification, ConfirmationError


@dataclass
class PendingRun:
    id: str
    mode: str
    owner: str | None
    expires: float
    state: str = 'resolving'
    clarification: Clarification | None = None
    lock: Lock = field(default_factory=Lock)


class ConfirmationRegistry:
    def __init__(self, delete_thread, *, ttl=900, capacity=1000, clock=time.time):
        self.delete_thread = delete_thread
        self.ttl, self.capacity, self.clock = ttl, capacity, clock
        self.runs: dict[str, PendingRun] = {}
        self.ids: dict[str, str] = {}
        self.consumed: dict[str, tuple[float, int]] = {}
        self.lock = RLock()
        self.stop = Event()
        self.cleaner = None

    def begin(self, run_id, mode, owner):
        self.sweep()
        with self.lock:
            if len(self.runs) >= self.capacity:
                raise ConfirmationError('confirmation_capacity_reached', 503)
            run = PendingRun(run_id, mode, owner, self.clock() + self.ttl)
            self.runs[run_id] = run
            return run

    def pause(self, run_id, clarification):
        with self.lock:
            run = self.runs[run_id]
            if self.clock() >= run.expires:
                self.finish(run_id, code=410)
                raise ConfirmationError('confirmation_expired', 410)
            if run.clarification:
                old = run.clarification.confirmation_id
                self.ids.pop(old, None)
                self.consumed[old] = (run.expires, 409)
            run.state = 'waiting'
            run.clarification = clarification
            self.ids[clarification.confirmation_id] = run_id
            if self.cleaner is None:
                self.cleaner = Thread(target=self._clean, args=(weakref.ref(self), self.stop), daemon=True)
                self.cleaner.start()

    @staticmethod
    def _clean(reference, stop):
        while not stop.wait(5):
            registry = reference()
            if registry is None:
                return
            registry.sweep()
            del registry

    def claim(self, payload, mode, owner):
        self.sweep()
        with self.lock:
            run_id = self.ids.get(payload.confirmation_id)
            run = self.runs.get(run_id)
            if run is None:
                code = self.consumed.get(payload.confirmation_id, (0, 410))[1]
                raise ConfirmationError('confirmation_consumed' if code == 409 else 'confirmation_expired', code)
            if run.mode != mode or run.owner != owner:
                raise ConfirmationError('confirmation_scope_mismatch', 409)
            if run.state != 'waiting' or not run.lock.acquire(blocking=False):
                raise ConfirmationError('confirmation_in_progress', 409)
            try:
                if payload.action == 'confirm':
                    supplied = {d.item_id: d.option_id for d in payload.decisions}
                    expected = {item.id: {o.id for o in item.options} for item in run.clarification.items}
                    if (len(supplied) != len(payload.decisions) or supplied.keys() != expected.keys()
                            or any(supplied[k] not in choices for k, choices in expected.items())):
                        raise ConfirmationError('invalid_confirmation_options')
                run.state = 'resolving'
                return run
            except Exception:
                run.lock.release()
                raise

    def finish(self, run_id, *, code=409):
        with self.lock:
            run = self.runs.pop(run_id, None)
            if run is None:
                return
            if run.clarification:
                ident = run.clarification.confirmation_id
                self.ids.pop(ident, None)
                self.consumed[ident] = (run.expires, code)
            # Delete ALL checkpoint versions and pending writes, not only head.
            self.delete_thread(run_id)
            run.clarification = None
            run.owner = None

    def sweep(self):
        with self.lock:
            now = self.clock()
            for run in list(self.runs.values()):
                if run.state == 'waiting' and now >= run.expires and run.lock.acquire(blocking=False):
                    try:
                        self.finish(run.id, code=410)
                    finally:
                        run.lock.release()
            self.consumed = {k: v for k, v in self.consumed.items() if v[0] > now}

    def close(self):
        self.stop.set()
        with self.lock:
            for run_id in list(self.runs):
                self.finish(run_id, code=410)
