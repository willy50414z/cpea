import asyncio
import json
import sys

ERROR_CODES={'context_budget_exceeded','invalid_selection_empty','invalid_selection_table',
    'invalid_selection_columns','invalid_selection_unknown_column','index_locked','index_not_ready',
    'index_drift','index_content_mismatch','manifest_identity_mismatch','completion_not_finished',
    'no_schema_candidates','replay_input_drift','replay_exhausted'}


class WorkerProtocol:
    # idle -> accepted -> running -> terminal -> idle. Cancel drains before terminal.
    def __init__(self, planner, emit):
        self.planner=planner; self.emit=emit; self.task=None; self.current=None
        self.terminal=False

    def event(self, kind, **extra):
        payload=self.current or {}
        self.emit({'protocol_version':1,'type':kind,
            **{k:payload.get(k) for k in ('request_id','run_id','case_id')},**extra})

    def finish(self, kind, **extra):
        if not self.terminal:
            self.terminal=True; self.event(kind,**extra)

    async def _plan(self, payload):
        try:
            result=await self.planner.plan(payload)
            self.finish('result',**result)
        except asyncio.CancelledError:
            recorder=self.planner.last_recorder
            attempts=recorder.sent_attempts if recorder else 0
            self.finish('unknown_outcome' if recorder and recorder.failed and attempts else 'cancelled',
                sent_attempts=attempts,cost_complete=False if attempts else True)
        except Exception as exc:
            recorder=self.planner.last_recorder
            value=str(exc)
            code=value if value in ERROR_CODES else ('rate_limit' if type(exc).__name__=='RateLimitError' else 'invalid_model_response' if type(exc).__name__ in {'ValidationError','JSONDecodeError','KeyError'} else 'transport_error' if recorder and recorder.failed else 'worker_error')
            self.finish('error',code=code,message=code,node_id=recorder.node_id if recorder else None,
                sent_attempts=recorder.sent_attempts if recorder else 0,cost_complete=False)

    async def handle(self, payload):
        if payload.get('protocol_version')!=1: raise ValueError('protocol_version')
        kind=payload.get('type')
        if kind=='plan':
            if self.task and not self.task.done(): raise ValueError('worker_busy')
            self.current=payload; self.terminal=False
            self.event('accepted')
            self.event('running')
            self.task=asyncio.create_task(self._plan(payload))
            self.task.add_done_callback(lambda task: self.finish('cancelled',sent_attempts=0,cost_complete=True) if task.cancelled() and not self.terminal else None)
        elif kind=='cancel':
            if self.current and all(payload.get(k)==self.current.get(k) for k in ('request_id','run_id')):
                if self.task and not self.task.done(): self.task.cancel()
        elif kind=='shutdown':
            if self.task and not self.task.done(): self.task.cancel()
            await self.drain()
        else: raise ValueError('unknown_protocol_event')

    async def drain(self):
        if self.task: await asyncio.gather(self.task,return_exceptions=True)


async def serve(planner, output):
    from .planner import provenance
    def emit(event):
        output.write(json.dumps(event,ensure_ascii=False)+'\n'); output.flush()
    emit({'protocol_version':1,'type':'handshake','request_id':None,'run_id':None,'case_id':None,**provenance()})
    worker=WorkerProtocol(planner,emit)
    reader=asyncio.StreamReader(limit=4*1024*1024)
    protocol=asyncio.StreamReaderProtocol(reader)
    await asyncio.get_running_loop().connect_read_pipe(lambda:protocol,sys.stdin)
    try:
        while line:=await reader.readline():
            if len(line)>2*1024*1024: raise ValueError('payload_too_large')
            payload=json.loads(line)
            await worker.handle(payload)
            if payload.get('type')=='shutdown': break
    finally:
        if worker.task and not worker.task.done(): worker.task.cancel()
        await worker.drain()
