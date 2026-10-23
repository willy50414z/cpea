"""Persistent serial worker with bounded pipes and fail-closed run correlation."""
from __future__ import annotations

import io
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
from time import monotonic
from uuid import uuid4

from .wrenai_protocol import (MAX_LINE_BYTES, MAX_PAYLOAD_BYTES, MAX_QUEUE, TERMINAL, WORKER_ERROR_CODES,
                              WorkerError, decode_event, encode_plan, verify_handshake)


class WrenAIWorkerClient:
    def __init__(self, command, *, expected_metadata, expected_import_root, artifact_root,
                 timeout=120, cancel_grace=2, terminate_grace=2,
                 max_line_bytes=MAX_LINE_BYTES, max_payload_bytes=MAX_PAYLOAD_BYTES,
                 max_queue=MAX_QUEUE, env=None):
        if min(timeout,cancel_grace,terminate_grace)<=0 or min(max_line_bytes,max_payload_bytes,max_queue)<=0:
            raise ValueError('worker limits must be positive')
        self.command,self.expected_metadata,self.import_root = command,dict(expected_metadata),expected_import_root
        self.root = Path(artifact_root)
        self.root.mkdir(parents=True,exist_ok=True,mode=0o700)
        self.root.chmod(0o700)
        self.timeout,self.cancel_grace,self.terminate_grace = timeout,cancel_grace,terminate_grace
        self.max_line,self.max_payload,self.max_queue = max_line_bytes,max_payload_bytes,max_queue
        self.env=env
        self.process=None
        self.runs={}
        self._lock=threading.Lock()
        self._threads=[]
        self._lifecycle_name=uuid4().hex+'.lifecycle.jsonl'
        self._private(self._lifecycle_name).close()
        self._record({'limits':{'timeout':timeout,'cancel_grace':cancel_grace,
            'terminate_grace':terminate_grace,'max_line_bytes':max_line_bytes,
            'max_payload_bytes':max_payload_bytes,'max_queue':max_queue}})

    def __enter__(self): return self

    def __exit__(self,*args): self.close()

    def _private(self,name):
        return os.fdopen(os.open(self.root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb',buffering=0)

    def _record(self,event):
        fd=os.open(self.root/self._lifecycle_name,os.O_WRONLY|os.O_APPEND)
        with os.fdopen(fd,'wb',buffering=0) as artifact:
            artifact.write(json.dumps(event,ensure_ascii=False,allow_nan=False).encode('utf-8')+b'\n')

    def _state(self,run,kind):
        run['states'].append(kind)
        self._record({'request_id':run['request_id'],'run_id':run['run_id'],
                      'case_id':run['case_id'],'state':kind})

    def _enqueue(self,event):
        try: self._queue.put_nowait(event)
        except queue.Full: self._failure=self._failure or 'protocol_limit_exceeded'

    def _stdout(self,stream,artifact):
        stream=io.BufferedReader(stream)
        try:
            while True:
                raw=stream.readline(self.max_line+1)
                if not raw: break
                artifact.write(raw)
                if len(raw)>self.max_line:
                    self._failure=self._failure or 'protocol_limit_exceeded'
                    # Continue draining bytes without accumulating an unbounded line.
                    while raw and not raw.endswith(b'\n'):
                        raw=stream.readline(self.max_line+1);artifact.write(raw)
                    continue
                if self._failure: continue
                try: self._enqueue(decode_event(raw,max_line_bytes=self.max_line))
                except WorkerError as exc: self._failure=self._failure or exc.code
        finally:
            artifact.close();stream.close();self._enqueue(None)

    @staticmethod
    def _stderr(stream,artifact):
        try:
            while chunk:=stream.read(8192): artifact.write(chunk)
        finally: artifact.close();stream.close()

    def _start(self):
        if self.process is not None: self._stop()
        self._queue=queue.Queue(self.max_queue)
        self._failure=None
        identifier=uuid4().hex
        try:
            self.process=subprocess.Popen(self.command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE,env=self.env,bufsize=0)
        except OSError:
            raise WorkerError('worker_startup_error') from None
        self._threads=[threading.Thread(target=self._stdout,args=(self.process.stdout,self._private(identifier+'.jsonl')),daemon=True),
                       threading.Thread(target=self._stderr,args=(self.process.stderr,self._private(identifier+'.stderr')),daemon=True)]
        for thread in self._threads: thread.start()
        try:
            event=self._next(monotonic()+self.timeout)
            verify_handshake(event,self.expected_metadata,self.import_root)
        except Exception:
            self._stop();raise

    def _next(self,deadline,cancel_run=None):
        while True:
            if cancel_run and cancel_run.get('cancel_requested'): raise WorkerError('worker_cancelled')
            if self._failure: raise WorkerError(self._failure)
            left=deadline-monotonic()
            if left<=0: raise WorkerError('worker_timeout')
            try: event=self._queue.get(timeout=min(left,0.05))
            except queue.Empty: continue
            if event is None: raise WorkerError('worker_crash')
            return event

    def _send(self,payload,deadline,*,cancel_run=None):
        raw=encode_plan(payload,max_payload_bytes=self.max_payload)
        finished=threading.Event();errors=[]
        def write():
            try:
                remaining=memoryview(raw)
                while remaining:
                    written=self.process.stdin.write(remaining)
                    if not written: raise BrokenPipeError()
                    remaining=remaining[written:]
                self.process.stdin.flush()
            except (BrokenPipeError,OSError,ValueError): errors.append(True)
            finally: finished.set()
        writer=threading.Thread(target=write,daemon=True);self._threads.append(writer);writer.start()
        while not finished.wait(0.02):
            if cancel_run and cancel_run.get('cancel_requested'): raise WorkerError('worker_cancelled')
            if monotonic()>=deadline: raise WorkerError('worker_timeout')
        if errors: raise WorkerError('worker_crash')

    def _stop(self):
        process=self.process
        if process is None: return
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=self.terminate_grace)
            except subprocess.TimeoutExpired:
                process.kill();process.wait()
        else: process.wait()
        if process.stdin: process.stdin.close()
        for thread in self._threads: thread.join(timeout=self.terminate_grace)
        if any(thread.is_alive() for thread in self._threads):
            raise WorkerError('worker_drain_failed')

    def _terminal(self,run,kind):
        if run['terminal'] is None:
            run['terminal']=kind;self._state(run,kind)

    def _correlate(self,event):
        run=self.runs.get(event.get('run_id'))
        if run is None or event.get('request_id')!=run['request_id'] or event.get('case_id')!=run['case_id']:
            raise WorkerError('event_id_mismatch')
        return run

    def _archive_late(self,event,owner):
        if owner['terminal'] is None: return False
        if event['type'] in TERMINAL:
            self._record({'request_id':owner['request_id'],'run_id':owner['run_id'],
                'case_id':owner['case_id'],'code':'duplicate_terminal',
                'event_type':event['type'],'original_terminal':owner['terminal']})
            self._failure='duplicate_terminal'
            raise WorkerError('duplicate_terminal')
        return True  # The reader has already archived it with its original IDs.

    def _drain_pending(self):
        if self._failure: raise WorkerError(self._failure)
        while True:
            try: event=self._queue.get_nowait()
            except queue.Empty: return
            if event is None: raise WorkerError('worker_crash')
            owner=self._correlate(event)
            if not self._archive_late(event,owner): raise WorkerError('invalid_event_order')

    def cancel(self,run_id):
        run=self.runs.get(run_id)
        if not run or run['terminal'] is not None: return False
        run['cancel_requested']=True
        return True

    def plan(self, *, request, run_id=None, case_id=None, **payload):
        with self._lock:
            run_id=run_id or uuid4().hex
            if run_id in self.runs: raise WorkerError('duplicate_run_id')
            run={'request_id':uuid4().hex,'run_id':run_id,'case_id':case_id,'terminal':None,'states':[]}
            self.runs[run_id]=run
            sent=False
            try:
                if self.process is None or self.process.poll() is not None: self._start()
                self._drain_pending()
                deadline=monotonic()+self.timeout
                message={**payload,'protocol_version':1,'type':'plan','request_id':run['request_id'],
                         'run_id':run_id,'case_id':case_id,'request':request}
                # Validate before marking a request as possibly dispatched.
                encode_plan(message,max_payload_bytes=self.max_payload)
                sent=True
                self._send(message,deadline,cancel_run=run)
                while True:
                    event=self._next(deadline,cancel_run=run)
                    owner=self._correlate(event)
                    if self._archive_late(event,owner): continue
                    if owner is not run: raise WorkerError('event_id_mismatch')
                    kind=event['type']
                    if kind=='accepted' and not run['states']: self._state(run,kind)
                    elif kind=='running' and run['states']==['accepted']: self._state(run,kind)
                    elif kind in TERMINAL:
                        if kind=='result' and run['states']!=['accepted','running']:
                            raise WorkerError('invalid_event_order')
                        self._terminal(run,kind)
                        if kind=='result': return event
                        if kind=='error':
                            code=event.get('code')
                            raise WorkerError(code if isinstance(code,str) and code in WORKER_ERROR_CODES else 'worker_error')
                        raise WorkerError('worker_'+kind)
                    else: raise WorkerError('invalid_event_order')
            except WorkerError as exc:
                if exc.code in {'worker_timeout','worker_cancelled'} and run['terminal'] is None and sent and self.process and self.process.poll() is None:
                    self._state(run,'cancel_requested')
                    try:
                        deadline=monotonic()+self.cancel_grace
                        self._send({'protocol_version':1,'type':'cancel','request_id':run['request_id'],'run_id':run_id},deadline)
                        while True:
                            event=self._next(deadline)
                            owner=self._correlate(event)
                            if owner is run and event['type']=='cancelled':
                                self._terminal(run,'cancelled');break
                    except WorkerError: pass
                self._terminal(run,'unknown_outcome' if sent and exc.code in {'worker_timeout','worker_crash','worker_cancelled'} else 'error')
                self._stop()
                raise

    def close(self):
        with self._lock:
            if self.process and self.process.poll() is None:
                try: self._send({'protocol_version':1,'type':'shutdown'},monotonic()+self.cancel_grace)
                except WorkerError: pass
                try: self.process.wait(timeout=self.cancel_grace)
                except subprocess.TimeoutExpired: pass
            self._stop()
