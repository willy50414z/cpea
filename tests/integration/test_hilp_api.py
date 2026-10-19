import json
from fastapi.testclient import TestClient
from cpea.interfaces.api.app import create_app
from tests.hilp_support import QUESTION, runtime_for, selection
from cpea.application.models.query import SQLGenerationResponse


def test_json_query_and_sql_confirmation_protocol(tmp_path):
    calls = []
    runtime = runtime_for(tmp_path, executor=lambda d, s: (calls.append(s) or (['value'], [[123]])))
    with TestClient(create_app(runtime)) as client:
        pending = client.post('/api/assistant/query', json={'request': QUESTION})
        assert pending.status_code == 200
        body = pending.json()
        assert body['status'] == 'needs_confirmation' and body['sql'] is None and not calls
        payload = selection(SQLGenerationResponse.model_validate(body)).model_dump()
        assert client.post('/api/assistant/sql/confirm', json=payload).status_code == 409
        ready = client.post('/api/assistant/query/confirm', json=payload)
        assert ready.status_code == 200 and len(calls) == 1
        result = ready.json()
        assert result['generation']['term_mapping_reasoning'] == result['term_mapping_reasoning']
        assert result['term_mapping_reasoning'][0]['source'] == 'confirmed_this_request'
        assert client.post('/api/assistant/query/confirm', json=payload).status_code == 409
        bad = client.post('/api/assistant/sql', json={'request': QUESTION, 'history': [{'role': 'user', 'content': '前題'}]})
        assert bad.status_code == 422 and 'history_not_supported' in bad.text
        reused = client.post('/api/assistant/sql', json={'request': QUESTION}).json()
        assert reused['term_mapping_reasoning'][0]['source'] == 'reused_confirmation'


def test_sse_pending_resume_and_cancel(tmp_path):
    calls = []
    runtime = runtime_for(tmp_path, executor=lambda d, s: (calls.append(s) or (['value'], [[1]])))
    with TestClient(create_app(runtime)) as client:
        response = client.post('/api/assistant/query/stream', json={'request': QUESTION})
        assert response.text.startswith('event: clarification')
        assert 'event: sql\n' not in response.text and not calls
        body = json.loads(response.text.split('data: ', 1)[1])
        payload = selection(SQLGenerationResponse.model_validate(body)).model_dump()
        resumed = client.post('/api/assistant/query/confirm/stream', json=payload)
        assert resumed.text.startswith('event: sql') and 'event: result' in resumed.text
        assert 'confirmed_this_request' in resumed.text and len(calls) == 1
        assert client.post('/api/assistant/query/confirm/stream', json=payload).status_code == 409


def test_cancel_does_not_need_decisions(tmp_path):
    runtime = runtime_for(tmp_path)
    with TestClient(create_app(runtime)) as client:
        pending = client.post('/api/assistant/sql', json={'request': QUESTION}).json()
        payload = {'confirmation_id': pending['clarification']['confirmation_id'], 'action': 'cancel'}
        assert client.post('/api/assistant/sql/confirm', json={**payload, 'decisions': []}).status_code == 422
        assert client.post('/api/assistant/sql/confirm', json=payload).json()['status'] == 'cancelled'
        assert not (tmp_path / 'terms_mapping.json').exists()


def test_resume_sse_awaits_sql_send_before_execution(tmp_path):
    import asyncio
    from tests.integration.test_streamed_query import scope
    calls = []
    runtime = runtime_for(tmp_path, executor=lambda d, s: (calls.append(s) or ([], [])))
    pending = runtime.generation_service().generate(QUESTION, mode='stream')
    payload = selection(pending).model_dump()
    app = create_app(runtime)
    async def run():
        queue = asyncio.Queue()
        await queue.put({'type': 'http.request', 'body': json.dumps(payload).encode('utf-8'), 'more_body': False})
        sent, release = asyncio.Event(), asyncio.Event()
        request_scope = scope()
        request_scope.update(path='/api/assistant/query/confirm/stream', raw_path=b'/api/assistant/query/confirm/stream')
        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body', b'').startswith(b'event: sql'):
                sent.set()
                await release.wait()
        task = asyncio.create_task(app(request_scope, queue.get, send))
        await asyncio.wait_for(sent.wait(), 5)
        assert not calls
        release.set()
        await asyncio.wait_for(task, 5)
        assert len(calls) == 1
    asyncio.run(run())
    runtime.close()
