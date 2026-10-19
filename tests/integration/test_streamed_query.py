import asyncio
from contextlib import contextmanager
from datetime import date, datetime, time, timezone
from decimal import Decimal
import json
import socket
from threading import Event, Thread
import time as clock
from uuid import UUID

from fastapi.testclient import TestClient
import httpx
import pytest
import uvicorn

from cpea.application.models.query import SQLGenerationResponse
from cpea.bootstrap import AssistantRuntime
from cpea.interfaces.api.app import create_app
from cpea.interfaces.api.streaming import ERROR_MESSAGE, STREAM_PATH
from tests.support import dependencies, QUESTION


def make_runtime(tmp_path, executor=None, binding='synthetic-binding'):
    settings, catalog, packer, llm, retriever = dependencies(tmp_path)
    return AssistantRuntime(settings, catalog=catalog, llm=llm, retriever=retriever,
                            context_packer=packer, executor=executor, datasource_id=binding)


def events(response):
    return [(frame.splitlines()[0].removeprefix('event: '),
             json.loads(frame.splitlines()[1].removeprefix('data: ')))
            for frame in response.text.strip().split('\n\n')]


@pytest.mark.parametrize('payload', [{}, {'request': ''}, {'request': ' \n '},
    {'request': 'x'*4001}, {'request': 123}, {'request': QUESTION, 'history': []},
    {'request': QUESTION, 'sql': 'SELECT 1'}, {'request': QUESTION, 'datasource': 'secret'},
    {'request': QUESTION, 'profile_path': '/secret'}, {'request': None}])
def test_fixed_validation_no_calls(tmp_path, payload):
    calls = []
    runtime = make_runtime(tmp_path, lambda d, s: calls.append(s))
    response = TestClient(create_app(runtime)).post(STREAM_PATH, json=payload)
    assert response.status_code == 422
    assert response.json() == {'message': ERROR_MESSAGE}
    assert not calls and runtime.llm.calls == 0


def test_malformed_json_and_missing_dependency(tmp_path):
    runtime = make_runtime(tmp_path)
    client = TestClient(create_app(runtime))
    bad = client.post(STREAM_PATH, content='{PWD=secret', headers={'Content-Type': 'application/json'})
    assert bad.status_code == 422 and bad.json() == {'message': ERROR_MESSAGE}
    response = client.post(STREAM_PATH, json={'request': QUESTION})
    assert response.status_code == 503 and response.json() == {'message': ERROR_MESSAGE}
    assert runtime.llm.calls == 0


@pytest.mark.parametrize('rows,truncated', [([], False), ([['A', 1]], False),
    ([['A', 1], ['B', 2]], False), ([['A', 1], ['B', 2], ['C', 3]], True)])
def test_success_single_generation_execution_trace_and_bounding(tmp_path, rows, truncated):
    calls = []
    runtime = make_runtime(tmp_path, lambda d, s: (calls.append((d, s)) or (['倉庫', '數量'], rows)))
    service = runtime.staged_query_service()
    stage = service.generate(QUESTION)
    assert not calls and runtime.llm.calls == 1
    result = service.execute(QUESTION, stage)
    assert len(calls) == 1 and calls[0] == ('synthetic-binding', stage.sql)
    assert result.execution.attempts == 1 and not result.execution.repaired
    assert result.execution.generation.query_trace.execution_attempts == 1
    assert result.execution.rows_truncated == truncated
    calls.clear()
    runtime.llm.calls = 0
    response = TestClient(create_app(runtime)).post(STREAM_PATH, json={'request': QUESTION})
    parsed = events(response)
    assert [e[0] for e in parsed] == ['sql', 'result']
    assert calls[0][1] == parsed[0][1]['sql'] and len(calls) == 1
    assert runtime.llm.calls == 1
    assert parsed[1][1] == {'columns': ['倉庫', '數量'], 'rows': rows[:2],
                            'rows_truncated': truncated, 'row_limit': 2}
    assert response.headers['cache-control'] == 'no-cache, no-transform'
    assert response.headers['x-accel-buffering'] == 'no'
    assert response.headers['content-type'].startswith('text/event-stream')


@pytest.mark.parametrize('phase', ['generation', 'unsupported', 'policy', 'plan', 'execution', 'timeout', 'encoding', 'nan'])
def test_stage_errors_are_fixed_without_secrets(tmp_path, monkeypatch, caplog, phase):
    calls = []
    def executor(d, s):
        calls.append(s)
        if phase in ['execution', 'timeout']:
            raise TimeoutError('PWD=top-secret;Server=private;raw-sql')
        if phase == 'encoding':
            return ['value'], [[object()]]
        if phase == 'nan':
            return ['value'], [[float('nan')]]
        return ['value'], [[1]]
    runtime = make_runtime(tmp_path, executor)
    if phase in ['generation', 'unsupported', 'policy', 'plan']:
        original = runtime.staged_query_service
        def service_factory():
            service = original()
            if phase == 'generation':
                def fail(*args, **kwargs):
                    raise RuntimeError('PWD=top-secret')
                service.agent.generator.generate = fail
            elif phase == 'unsupported':
                service.agent.generator.generate = lambda *a, **k: SQLGenerationResponse(supported=False, explanation='資料不足')
            else:
                generation = service.agent.generator.generate(QUESTION)
                generation = generation.model_copy(update={'sql': 'DELETE FROM gms2.v_inventory'} if phase == 'policy' else {'query_plan': None})
                service.agent.generator.generate = lambda *a, **k: generation
            return service
        monkeypatch.setattr(runtime, 'staged_query_service', service_factory)
    response = TestClient(create_app(runtime)).post(STREAM_PATH, json={'request': QUESTION})
    parsed = events(response)
    before_sql = phase in ['generation', 'unsupported', 'policy', 'plan']
    assert [e[0] for e in parsed] == (['unsupported'] if phase == 'unsupported' else ['error'] if before_sql else ['sql', 'error'])
    if phase != 'unsupported':
        assert parsed[-1][1] == {'message': ERROR_MESSAGE}
    assert len(calls) == (0 if before_sql else 1)
    assert 'top-secret' not in response.text and 'top-secret' not in caplog.text


def test_precise_result_encoding(tmp_path):
    values = [None, '中文', date(2026, 10, 14), datetime(2026, 10, 14, 12, tzinfo=timezone.utc),
              time(12, 34), Decimal('12345678901234567890.00001'),
              UUID('12345678-1234-5678-1234-567812345678'), b'\x00\xff']
    runtime = make_runtime(tmp_path, lambda d, s: ([str(i) for i in range(len(values))], [values]))
    parsed = events(TestClient(create_app(runtime)).post(STREAM_PATH, json={'request': QUESTION}))
    assert parsed[-1][1]['rows'] == [[None, '中文', '2026-10-14', '2026-10-14T12:00:00+00:00',
        '12:34:00', '12345678901234567890.00001', '12345678-1234-5678-1234-567812345678', 'base64:AP8=']]


def scope():
    return {'type': 'http', 'asgi': {'version': '3.0', 'spec_version': '2.3'},
        'http_version': '1.1', 'method': 'POST', 'scheme': 'http', 'path': STREAM_PATH,
        'raw_path': STREAM_PATH.encode(), 'query_string': b'', 'root_path': '',
        'headers': [(b'content-type', b'application/json')],
        'client': ('127.0.0.1', 12345), 'server': ('127.0.0.1', 80)}


def test_asgi_body_awaits_sql_send_before_execution(tmp_path):
    calls = []
    runtime = make_runtime(tmp_path, lambda d, s: (calls.append(s) or (['value'], [[1]])))
    app = create_app(runtime)
    async def run():
        queue = asyncio.Queue()
        await queue.put({'type': 'http.request', 'body': json.dumps({'request': QUESTION}).encode(), 'more_body': False})
        sent = asyncio.Event()
        release = asyncio.Event()
        messages = []
        async def send(message):
            messages.append(message)
            if message['type'] == 'http.response.body' and message.get('body', b'').startswith(b'event: sql'):
                sent.set()
                await release.wait()
        task = asyncio.create_task(app(scope(), queue.get, send))
        await asyncio.wait_for(sent.wait(), 5)
        assert not calls
        release.set()
        await asyncio.wait_for(task, 5)
        assert len(calls) == 1
        bodies = [m['body'] for m in messages if m['type'] == 'http.response.body']
        assert bodies[0].startswith(b'event: sql') and bodies[1].startswith(b'event: result')
    asyncio.run(run())


def test_disconnect_after_sql_does_not_start_db(tmp_path):
    calls = []
    runtime = make_runtime(tmp_path, lambda d, s: (calls.append(s) or ([], [])))
    app = create_app(runtime)
    async def run():
        queue = asyncio.Queue()
        await queue.put({'type': 'http.request', 'body': json.dumps({'request': QUESTION}).encode(), 'more_body': False})
        async def send(message):
            if message['type'] == 'http.response.body' and message.get('body', b'').startswith(b'event: sql'):
                await queue.put({'type': 'http.disconnect'})
                await asyncio.sleep(0)
        await asyncio.wait_for(app(scope(), queue.get, send), 5)
        assert not calls
    asyncio.run(run())


def test_disconnect_during_driver_work_eventually_closes_resources(tmp_path):
    from tests.unit.test_sql_server import Driver, adapter
    driver = Driver()
    executor = adapter(driver)
    started = Event()
    release = Event()
    original_connect = driver.connect
    def connect(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        original_cursor = connection.cursor
        def cursor():
            cursor = original_cursor()
            original_execute = cursor.execute
            def execute(sql):
                started.set()
                assert release.wait(5)
                original_execute(sql)
            cursor.execute = execute
            return cursor
        connection.cursor = cursor
        return connection
    driver.connect = connect
    runtime = make_runtime(tmp_path, executor, binding='logical-binding')
    app = create_app(runtime)
    async def run():
        queue = asyncio.Queue()
        await queue.put({'type': 'http.request', 'body': json.dumps({'request': QUESTION}).encode(), 'more_body': False})
        messages = []
        task = asyncio.create_task(app(scope(), queue.get, lambda m: send(messages, m)))
        assert await asyncio.to_thread(started.wait, 5)
        await queue.put({'type': 'http.disconnect'})
        await asyncio.sleep(0.05)
        release.set()
        await asyncio.wait_for(task, 5)
        assert not any(m.get('body', b'').startswith(b'event: result') for m in messages)
    async def send(messages, message):
        messages.append(message)
    try:
        asyncio.run(run())
    finally:
        release.set()
    assert driver.connections[0].closed and driver.connections[0].created_cursor.closed
    assert driver.connections[0].created_cursor.executions == 1


@contextmanager
def live_server(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='on'))
    thread = Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    deadline = clock.monotonic() + 10
    while not server.started and thread.is_alive() and clock.monotonic() < deadline:
        clock.sleep(0.01)
    assert server.started
    try:
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


def test_real_http_reads_sql_before_db_completes(tmp_path):
    started = Event()
    release = Event()
    finished = Event()
    calls = []
    def executor(datasource, sql):
        calls.append(sql)
        started.set()
        assert release.wait(5)
        finished.set()
        return ['中文'], [['值']]
    runtime = make_runtime(tmp_path, executor)
    with live_server(create_app(runtime)) as url:
        try:
            with httpx.stream('POST', url + STREAM_PATH, json={'request': QUESTION}, timeout=5) as response:
                lines = response.iter_lines()
                assert next(lines) == 'event: sql'
                sql = json.loads(next(lines).removeprefix('data: '))['sql']
                assert started.wait(2) and not finished.is_set()
                release.set()
                remaining = list(lines)
                assert 'event: result' in remaining
                assert len(calls) == 1 and calls[0] == sql
        finally:
            release.set()
