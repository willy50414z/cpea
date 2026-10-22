from types import SimpleNamespace

import pytest

from cpea.application.models.query import SQLGenerationResponse
from cpea.application.models.query_pipeline import TaskSQLInput
from cpea.workflows.query_pipeline.task_sql import generate_task_sql
from tests.decomposition_support import catalog_at, settings
from tests.hilp_support import QUESTION, runtime_for
from tests.query_pipeline_support import generation, planning


@pytest.mark.parametrize('outcome', ['ready', 'drift', 'provider', 'invalid', 'unsupported'])
def test_adapter_renders_approved_task_and_uses_empty_history(tmp_path, outcome):
    catalog = catalog_at(tmp_path)
    plan = planning(catalog, single=True)
    task = plan.draft.tasks[0]
    calls = []
    def generate(request, history, *, mode, owner):
        calls.append((request, history, mode))
        if outcome == 'provider': raise RuntimeError('secret provider detail')
        if outcome == 'invalid': return {'status': 'ready'}
        if outcome == 'unsupported': return SQLGenerationResponse(status='unsupported', supported=False, explanation='能力不足')
        result = generation(task, catalog, settings())
        if outcome == 'drift': result.selected_views = ['demo.sales']
        return result
    result = generate_task_sql(TaskSQLInput(original_request='多來源原文', task=task,
        contract_fingerprint=catalog.fingerprint), generator=SimpleNamespace(generate=generate),
        catalog=catalog, settings=settings())
    assert calls == [(plan.prepared_requests[0].payload['request'], [], 'sql')]
    assert result.status == ('ready' if outcome == 'ready' else 'unsupported' if outcome == 'unsupported' else 'error')
    assert result.gate_passed == (outcome == 'ready')
    assert 'secret' not in result.model_dump_json()


def test_inner_registry_is_finished_after_pending_without_response_run_id(tmp_path):
    runtime = runtime_for(tmp_path / 'hilp')
    generator = runtime.generation_service()
    # Real SQL workflow returns a pending HILP response without a response.run_id.
    catalog = catalog_at(tmp_path / 'catalog')
    task = planning(catalog, single=True).draft.tasks[0]
    original_generate = generator.generate
    generator.generate = lambda request, history, **kwargs: original_generate(QUESTION, history, **kwargs)
    result = generate_task_sql(TaskSQLInput(original_request=QUESTION, task=task,
        contract_fingerprint=catalog.fingerprint), generator=generator, catalog=catalog, settings=settings())
    assert result.status == 'needs_confirmation'
    assert result.generation.clarification.items
    assert not generator.workflow.registry.runs
    assert not generator.workflow.checkpointer.storage
    assert not generator.workflow.checkpointer.writes
    runtime.close()


def test_stale_or_unsupported_input_never_calls_generator(tmp_path):
    catalog = catalog_at(tmp_path)
    task = planning(catalog, single=True).draft.tasks[0]
    def forbidden(*args, **kwargs): raise AssertionError('must reject before model')
    for fingerprint in ['old', catalog.fingerprint]:
        if fingerprint == catalog.fingerprint: task.depends_on = ['upstream']
        result = generate_task_sql(TaskSQLInput(original_request='x', task=task,
            contract_fingerprint=fingerprint), generator=SimpleNamespace(generate=forbidden),
            catalog=catalog, settings=settings())
        assert result.status != 'ready'


def test_adapter_preserves_pending_clarification(tmp_path):
    from cpea.application.models.query import ClarificationRequest
    catalog = catalog_at(tmp_path)
    task = planning(catalog, single=True).draft.tasks[0]
    pending = SQLGenerationResponse(status='needs_clarification', supported=False, explanation='請選擇',
        clarification=ClarificationRequest(original_request='庫存', contract_fingerprint=catalog.fingerprint,
            question='哪一個粒度？', options=[dict(id='a', label='門市', description='依門市'),
                                           dict(id='b', label='商品', description='依商品')]))
    result = generate_task_sql(TaskSQLInput(original_request='庫存', task=task, contract_fingerprint=catalog.fingerprint),
        generator=SimpleNamespace(generate=lambda *args, **kwargs: pending), catalog=catalog, settings=settings())
    assert result.status == 'needs_clarification'
    assert result.generation.clarification.question == '哪一個粒度？'
    assert not result.gate_passed and result.generation.sql is None


def test_gate_rejection_retains_raw_generation_only_in_private_observer(tmp_path):
    catalog = catalog_at(tmp_path)
    task = planning(catalog, single=True).draft.tasks[0]
    bad = generation(task, catalog, settings())
    bad.selected_views = ['demo.sales']
    diagnostics = []
    result = generate_task_sql(TaskSQLInput(original_request='原文', task=task,
        contract_fingerprint=catalog.fingerprint), generator=SimpleNamespace(generate=lambda *args, **kwargs: bad),
        catalog=catalog, settings=settings(), observer=diagnostics.append)
    assert result.status == 'error' and result.generation is None
    assert diagnostics[0]['sql'] and diagnostics[0]['selected_views'] == ['demo.sales']


def test_legacy_parse_rejection_is_an_error_in_the_pipeline(tmp_path):
    from cpea.application.models.query import MappingAttempt, QueryTaskTrace
    catalog = catalog_at(tmp_path)
    task = planning(catalog, single=True).draft.tasks[0]
    rejected = SQLGenerationResponse(status='unsupported', supported=False, explanation='legacy parse rejection',
        query_trace=QueryTaskTrace(request='x', mapping_attempts=[
            MappingAttempt(attempt_index=0, outcome='parse_error', reason='invalid JSON')]))
    result = generate_task_sql(TaskSQLInput(original_request='原文', task=task, contract_fingerprint=catalog.fingerprint),
        generator=SimpleNamespace(generate=lambda *args, **kwargs: rejected), catalog=catalog, settings=settings())
    assert result.status == 'error'
    assert result.issues[0].code == 'invalid_model_response'
