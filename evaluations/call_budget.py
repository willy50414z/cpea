"""Atomic per-model call reservation with optional private persistent ledger."""

from __future__ import annotations

import fcntl
import json
import os
from pathlib import Path
from threading import Lock


class ModelStopped(RuntimeError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ProviderCallError(RuntimeError):
    """The triggering provider call failed; subsequent work is stopped."""


def model_key(target) -> str:
    return json.dumps([target.provider, target.model, target.deployment], ensure_ascii=False)


def provider_stop_reason(exc: Exception) -> str | None:
    text = f"{type(exc).__name__}: {exc}".casefold()
    if any(part in text for part in ("rate limit", "rate_limit", "ratelimit", "too many requests", "429", "quota exceeded")):
        return "rate_limit"
    if any(part in text for part in ("authentication", "unauthorized", "invalid api key", "invalid_api_key", "401", "403")):
        return "authentication"
    return None


class CallBudget:
    def __init__(self, max_calls: int | None = None, ledger: str | Path | None = None):
        if max_calls is not None and max_calls < 1:
            raise ValueError("max_model_calls must be positive")
        self.max_calls = max_calls
        self.ledger = Path(ledger) if ledger else None
        self._lock = Lock()
        self._counts: dict[str, int] = {}
        self._stopped: dict[str, str] = {}

    def reason(self, key: str) -> str | None:
        with self._lock:
            return self._stopped.get(key)

    def stop(self, key: str, reason: str) -> None:
        with self._lock:
            self._stopped.setdefault(key, reason)

    def reserve(self, key: str) -> None:
        with self._lock:
            if key in self._stopped:
                raise ModelStopped(self._stopped[key])
            if self.ledger is None:
                count = self._counts.get(key, 0)
                if self.max_calls is not None and count >= self.max_calls:
                    self._stopped[key] = "quota_cap_reached"
                    raise ModelStopped("quota_cap_reached")
                self._counts[key] = count + 1
                return
            self.ledger.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.ledger, os.O_CREAT | os.O_RDWR, 0o600)
            with os.fdopen(fd, "r+", encoding="utf-8") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX)
                stream.seek(0)
                raw = stream.read()
                data = json.loads(raw) if raw else {}
                count = data.get(key, 0)
                if self.max_calls is not None and count >= self.max_calls:
                    self._stopped[key] = "quota_cap_reached"
                    raise ModelStopped("quota_cap_reached")
                data[key] = count + 1
                stream.seek(0)
                stream.truncate()
                stream.write(json.dumps(data, ensure_ascii=False, sort_keys=True))
                stream.flush()
                fcntl.flock(stream, fcntl.LOCK_UN)

    def counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    def stopped(self) -> dict[str, str]:
        with self._lock:
            return dict(self._stopped)
