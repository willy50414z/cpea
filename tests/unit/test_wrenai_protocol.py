import pytest


def test_protocol_rejects_invalid_json_versions_and_limits():
    from cpea.workflows.task_decomposition.wrenai_protocol import decode_event, encode_plan, WorkerError
    for raw,code in [(b'bad', 'invalid_protocol'),(b'{"protocol_version":2,"type":"result"}', 'invalid_protocol'),(b'x'*65,'protocol_limit_exceeded')]:
        with pytest.raises(WorkerError) as exc: decode_event(raw,max_line_bytes=64)
        assert exc.value.code==code
    with pytest.raises(WorkerError) as exc:
        encode_plan({'request':'a'*50},max_payload_bytes=20)
    assert exc.value.code=='protocol_limit_exceeded'


def test_handshake_rejects_metadata_and_sources_fail_closed(tmp_path):
    from cpea.workflows.task_decomposition.wrenai_protocol import verify_handshake, WorkerError
    event={'protocol_version':1,'type':'handshake','upstream_sha':'sha','import_sources':{'src':'/outside/core.py'}}
    with pytest.raises(WorkerError): verify_handshake(event,{'upstream_sha':'sha'},tmp_path)
    with pytest.raises(WorkerError): verify_handshake({**event,'import_sources':{}},{'upstream_sha':'sha'},tmp_path)
    with pytest.raises(WorkerError): verify_handshake(event,{'upstream_sha':'other'},'/outside')


def test_protocol_plan_payload_rejects_oracle_keys():
    from cpea.workflows.task_decomposition.wrenai_protocol import encode_plan, WorkerError
    for key in ('expected_tasks','alternatives','oracle_notes'):
        with pytest.raises(WorkerError) as exc:
            encode_plan({'type':'plan','protocol_version':1,'request':'question',key:[]})
        assert exc.value.code=='invalid_payload'


@pytest.mark.parametrize('raw',[
 b'{"protocol_version":true,"type":"handshake"}',
 b'{"protocol_version":1,"type":"result","run_id":[]}',
 b'{"protocol_version":1,"type":"result","run_id":"a","run_id":"b"}',
 b'{"protocol_version":1,"type":"result","context_tokens":NaN}',
])
def test_protocol_rejects_noncanonical_json_and_unhashable_ids(raw):
    from cpea.workflows.task_decomposition.wrenai_protocol import decode_event, WorkerError
    with pytest.raises(WorkerError): decode_event(raw)
