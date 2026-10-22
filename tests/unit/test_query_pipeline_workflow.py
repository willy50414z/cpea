import json
from types import SimpleNamespace

import pytest

from cpea.application.models.decomposition import DecompositionResponse
from cpea.application.services.query_pipeline import QueryPipelineService
from tests.decomposition_support import catalog_at, settings
from tests.query_pipeline_support import generation, planning


def service(catalog, plan=None, failure=None, events=None):
    plan = plan or planning(catalog)
    calls = []
    def generate(request, history, **kwargs):
        body = json.loads(request.split('\n', 1)[1])
        task = next(t for t in plan.draft.tasks if t.view == body['view'])
        calls.append(task.task_id)
        if failure and len(calls) == 2: raise RuntimeError('private-error')
        return generation(task, catalog, settings())
    planner = SimpleNamespace(plan=lambda request: plan)
    pipeline = QueryPipelineService(planner, SimpleNamespace(generate=generate),
        catalog=catalog, settings=settings(), observer=events.append if events is not None else None)
    return pipeline, calls


def test_two_views_generate_two_independent_sql_results(tmp_path):
    catalog = catalog_at(tmp_path)
    events = []
    pipeline, calls = service(catalog, events=events)
    result = pipeline.invoke('目前庫存與九月銷量', run_id='run')
    assert result.status == 'sql_ready'
    assert calls == ['stock', 'sales']
    assert [r.task_id for r in result.task_results] == calls
    assert [e['event'] for e in events] == ['run_started', 'planning_finished', 'preflight_finished',
                                          'task_finished', 'task_finished', 'run_finished']
    assert set(pipeline.workflow.graph.get_graph().nodes) >= {'decompose_request', 'generate_task_sql'}


def test_generate_from_plan_skips_planner_and_uses_same_batch_gates(tmp_path):
    catalog = catalog_at(tmp_path)
    pipeline, calls = service(catalog)
    def forbidden(*args): raise AssertionError('planner must not run')
    pipeline.workflow.planner.plan = forbidden
    result = pipeline.generate_from_plan('核准輸入', planning(catalog, single=True))
    assert result.status == 'sql_ready' and calls == ['stock']


@pytest.mark.parametrize('status', ['needs_clarification', 'unsupported', 'error'])
def test_planning_pending_unsupported_and_error_skip_sql_node(tmp_path, status):
    catalog = catalog_at(tmp_path)
    pipeline, calls = service(catalog)
    pipeline.workflow.planner.plan = lambda request: DecompositionResponse(status=status,
        contract_fingerprint=catalog.fingerprint, code='provider_error' if status == 'error' else None)
    assert pipeline.invoke('需求').status == status
    assert not calls


def test_any_preflight_failure_skips_every_sql_task(tmp_path):
    catalog = catalog_at(tmp_path)
    plan = planning(catalog)
    plan.draft.tasks[1].metadata_collections = ['order_date']
    pipeline, calls = service(catalog, plan)
    result = pipeline.invoke('需求')
    assert result.status == 'unsupported' and not calls
    assert result.skipped_task_ids == ['stock', 'sales']


def test_second_task_failure_preserves_first_diagnostic_but_not_sql_ready(tmp_path):
    catalog = catalog_at(tmp_path)
    plan = planning(catalog)
    third = plan.draft.tasks[1].model_copy(deep=True, update={'task_id': 'third'})
    plan.draft.tasks.append(third)
    from cpea.application.models.decomposition import IntegrationEdge
    from cpea.workflows.task_decomposition.validation import prepare_requests
    plan.draft.integration.edges.append(IntegrationEdge(left_task='stock', right_task='third',
        left_keys=['store_id', 'product_id'], right_keys=['store_id', 'product_id'],
        cardinality='one_to_one', preserve_task='stock'))
    plan.prepared_requests = prepare_requests(plan.draft, catalog)
    events = []
    pipeline, calls = service(catalog, plan, failure=True, events=events)
    result = pipeline.invoke('需求')
    assert result.status == 'error' and calls == ['stock', 'sales']
    assert result.skipped_task_ids == ['third']
    assert result.task_results[0].generation is None
    assert next(e for e in events if e['event'] == 'task_finished')['diagnostic']['generation']['sql']
    assert 'SELECT' not in result.model_dump_json()


def test_request_and_catalog_state_do_not_leak_between_runs(tmp_path):
    catalog = catalog_at(tmp_path)
    pipeline, calls = service(catalog)
    for request in ['', ' ', 'x' * 4001]:
        assert pipeline.invoke(request).status == 'error'
    assert not calls
    assert pipeline.invoke('正常').status == 'sql_ready'
    assert pipeline.generate_from_plan('過期', planning(catalog).model_copy(update={'contract_fingerprint': 'old'})).status == 'error'
    assert pipeline.invoke('正常').status == 'sql_ready'


def test_no_db_executor_or_execution_runtime_is_constructed(tmp_path, monkeypatch):
    import cpea.infrastructure.database.factory as factory
    import cpea.bootstrap as bootstrap
    def forbidden(*args, **kwargs): raise AssertionError('DB runtime is forbidden')
    for module in [factory, bootstrap]:
        for name in vars(module).copy():
            if any(word in name.lower() for word in ['executor', 'executionagent', 'stagedquery', 'runtime']):
                monkeypatch.setattr(module, name, forbidden)
    pipeline, _ = service(catalog_at(tmp_path))
    assert pipeline.invoke('需求').status == 'sql_ready'
