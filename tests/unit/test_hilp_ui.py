import json
from itertools import groupby
from types import SimpleNamespace

import pytest
from cpea.application.errors import DependencyUnavailable
from cpea.application.models.confirmation import ConfirmationRequest, ConfirmationError
from cpea.interfaces.web.ui import SessionGate, single_question_updates, reset_question
from tests.hilp_support import QUESTION, runtime_for, selection


@pytest.mark.parametrize('error,error_code', [
    (DependencyUnavailable(), 'sql_executor_unavailable'),
    (ValueError('top-secret connection details'), 'unclassified'),
])
def test_generation_failure_logs_safe_error_identity(caplog, error, error_code):
    def require_execution():
        raise error

    runtime = SimpleNamespace(require_execution=require_execution)
    frames = list(single_question_updates(runtime, QUESTION, SessionGate(), stream_progress=False))

    assert [frame.state for frame in frames] == ['generating', 'error']
    assert f'error_type={type(error).__name__}' in caplog.text
    assert f'error_code={error_code}' in caplog.text
    assert 'top-secret' not in caplog.text
    assert 'top-secret' not in str(frames[-1].messages)


def test_generation_only_hilp_without_executor_stays_generation_only_on_resume(tmp_path, monkeypatch):
    runtime = runtime_for(tmp_path)
    monkeypatch.setattr(runtime, 'staged_query_service', lambda: pytest.fail('must not initialize execution'))
    gate = SessionGate('retail')
    try:
        initial = list(single_question_updates(runtime, QUESTION, gate))
        assert initial[-1].state == 'waiting_confirmation' and not initial[-1].sql
        assert gate.execution_enabled is False and runtime.llm.calls == 1
        assert '尚未連接資料庫' in initial[-1].messages[-1]['content']
        # Configuring an executor later must not upgrade this request to DB work.
        runtime.executor = lambda *args: pytest.fail('must not execute')
        payload = selection(SimpleNamespace(clarification=gate.pending))
        resumed = list(single_question_updates(runtime, '', gate, payload=payload))
        assert resumed[-1].state == 'completed' and 'order_amount' in gate.sql
        assert resumed[-1].sql == gate.sql
        assert '未執行查詢' in resumed[-1].messages[-1]['content']
        assert not resumed[-1].rows['data']
        assert runtime.llm.calls == 1 and not runtime.generation_service().workflow.registry.runs
        assert (tmp_path / 'terms_mapping.json').is_file()
    finally:
        runtime.close()


def test_generation_only_ready_without_confirmation(tmp_path, monkeypatch):
    from tests.integration.test_streamed_query import make_runtime
    from tests.support import QUESTION as inventory_question
    runtime = make_runtime(tmp_path)
    monkeypatch.setattr(runtime, 'staged_query_service', lambda: pytest.fail('must not initialize execution'))
    try:
        gate = SessionGate('retail')
        frames = list(single_question_updates(runtime, inventory_question, gate))
        assert frames[-1].state == 'completed' and gate.sql
        assert frames[-1].sql == gate.sql
        assert '未執行查詢' in frames[-1].messages[-1]['content']
        assert '查無資料' not in frames[-1].messages[-1]['content']
        assert runtime.llm.calls == 1 and not runtime.generation_service().workflow.registry.runs
    finally:
        runtime.close()


def test_generation_failure_logs_traceback_and_missing_provider_dependency(caplog):
    def initialize_services():
        try:
            raise ModuleNotFoundError('secret import details', name='langchain_openai')
        except ModuleNotFoundError as cause:
            raise RuntimeError('top-secret provider credentials') from cause

    gate = SessionGate('gms2')
    runtime = SimpleNamespace(require_execution=lambda: None, staged_query_service=initialize_services)
    frames = list(single_question_updates(runtime, QUESTION, gate))

    assert frames[-1].state == 'error'
    assert 'project=gms2' in caplog.text
    assert 'phase=initialize_services' in caplog.text
    assert 'error_code=llm_dependency_missing' in caplog.text
    assert 'Traceback' in caplog.text and 'initialize_services' in caplog.text
    assert 'ModuleNotFoundError' in caplog.text and 'RuntimeError' in caplog.text
    assert 'langchain-openai' in caplog.text
    assert 'top-secret' not in caplog.text and 'secret import details' not in caplog.text


def test_generation_failure_traceback_omits_exception_text_source_and_locals(caplog):
    password = 'top-secret-password'
    def initialize_services():
        raise RuntimeError(password)

    runtime = SimpleNamespace(require_execution=lambda: None, staged_query_service=initialize_services)
    list(single_question_updates(runtime, QUESTION, SessionGate('gms2')))

    assert 'Traceback' in caplog.text and 'initialize_services' in caplog.text
    assert 'top-secret-password' not in caplog.text
    assert 'raise RuntimeError(password)' not in caplog.text


def test_single_question_radio_confirm_and_new_question(tmp_path):
    calls = []
    runtime = runtime_for(tmp_path, executor=lambda d, s: (calls.append(s) or (['value'], [[1]])))
    gate = SessionGate()
    frames = list(single_question_updates(runtime, QUESTION, gate))
    assert [state for state, _ in groupby(f.state for f in frames)] == ['generating', 'waiting_confirmation']
    assert not calls and all(not f.sql for f in frames)
    assert gate.pending and gate.state == 'waiting_confirmation'
    assert list(single_question_updates(runtime, '另一題', gate)) == []
    response = SimpleNamespace(clarification=gate.pending)
    completed = list(single_question_updates(runtime, '', gate, payload=selection(response)))
    assert [state for state, _ in groupby(f.state for f in completed)] == ['resuming', 'executing', 'completed']
    assert '本次確認' in completed[-1].reasoning and len(calls) == 1
    assert runtime.llm.calls == 1
    fresh = reset_question(runtime, gate)
    assert fresh.state == 'idle' and not fresh.question and fresh.owner != gate.owner
    assert not fresh.reasoning and not fresh.summary and not fresh.steps
    runtime.close()


@pytest.mark.parametrize('action, state', [('cancel', 'cancelled'), ('rephrase', 'editing')])
def test_multi_group_cancel_without_partial_save(tmp_path, action, state):
    runtime = runtime_for(tmp_path, executor=lambda d, s: pytest.fail('must not execute'))
    original = runtime.llm.invoke
    def invoke(messages):
        value = original(messages)
        data = json.loads(value.content)
        data['fields'].append({'text': '淨額', 'column': 'net_amount'})
        return SimpleNamespace(content=json.dumps(data, ensure_ascii=False))
    runtime.llm.invoke = invoke
    gate = SessionGate()
    frames = list(single_question_updates(runtime, QUESTION.rstrip('。') + '、預估發票淨額。', gate))
    assert gate.state == 'waiting_confirmation' and len(gate.pending.items) == 2
    payload = ConfirmationRequest(confirmation_id=gate.pending.confirmation_id, action=action)
    stopped = list(single_question_updates(runtime, '', gate, payload=payload))
    assert stopped[-1].state == state and not (tmp_path / 'terms_mapping.json').exists()
    if action == 'rephrase':
        assert stopped[-1].draft == gate.question
    runtime.close()


def test_abandon_rotates_ui_owner_without_claiming_server_rollback(tmp_path):
    runtime = runtime_for(tmp_path, executor=lambda d, s: ([], []))
    gate = SessionGate()
    list(single_question_updates(runtime, QUESTION, gate))
    workflow = runtime.generation_service().workflow
    run = next(iter(workflow.registry.runs.values()))
    gate.state = 'resuming'
    with pytest.raises(ConfirmationError):
        reset_question(runtime, gate)
    fresh = reset_question(runtime, gate, abandon=True)
    assert gate.version == 2 and fresh.owner != gate.owner
    assert run.id in workflow.registry.runs  # May still finish, or expire normally.
    runtime.close()
