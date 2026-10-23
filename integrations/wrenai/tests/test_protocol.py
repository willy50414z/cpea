import asyncio


def test_terminal_once_cancel_then_next_run():
    from native_worker.protocol import WorkerProtocol
    events=[]
    class Planner:
        last_recorder=None
        async def plan(self,payload):
            await asyncio.sleep(10)
            return {'draft':{},'context_tokens':0,'token_counter':'fake','artifacts':{}}
    async def run():
        worker=WorkerProtocol(Planner(),events.append)
        await worker.handle({'protocol_version':1,'type':'plan','request_id':'q','run_id':'r','case_id':'c'})
        await asyncio.sleep(0)
        await worker.handle({'protocol_version':1,'type':'cancel','request_id':'q','run_id':'r'})
        await worker.drain()
        assert [e['type'] for e in events]==['accepted','running','cancelled']
        assert all(e['run_id']=='r' and e['case_id']=='c' for e in events)
    asyncio.run(run())


def test_error_is_sanitized():
    from native_worker.protocol import WorkerProtocol
    events=[]
    class Planner:
        last_recorder=None
        async def plan(self,payload): raise RuntimeError('secret=forbidden')
    async def run():
        worker=WorkerProtocol(Planner(),events.append)
        await worker.handle({'protocol_version':1,'type':'plan','request_id':'q','run_id':'r'})
        await worker.drain()
    asyncio.run(run())
    assert events[-1]['type']=='error'
    assert 'secret' not in str(events)
