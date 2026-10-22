import json

import pytest
from pydantic import ValidationError

from cpea.application.models.query_pipeline import QueryPipelineResponse, TaskSQLResult
from cpea.workflows.task_decomposition.validation import render_task_request
from tests.decomposition_support import catalog_at, settings
from tests.query_pipeline_support import generation, planning


def test_sql_ready_requires_every_task_ready_and_no_skipped_or_issues(tmp_path):
    catalog = catalog_at(tmp_path)
    plan = planning(catalog)
    results = [TaskSQLResult(task_id=t.task_id, status='ready', gate_passed=True, generation=generation(t, catalog, settings()))
               for t in plan.draft.tasks]
    values = dict(run_id='run', status='sql_ready', planning=plan, task_results=results,
                  contract_fingerprint=catalog.fingerprint)
    assert QueryPipelineResponse(**values).status == 'sql_ready'
    for change in [dict(task_results=results[:1]), dict(skipped_task_ids=['sales']),
                   dict(issues=[dict(stage='handoff', code='invalid_handoff', message='失敗')]),
                   dict(task_results=[r.model_copy(update={'generation': None}) for r in results])]:
        with pytest.raises(ValidationError):
            QueryPipelineResponse(**(values | change))


def test_non_ready_response_has_no_dispatchable_sql(tmp_path):
    catalog = catalog_at(tmp_path)
    plan = planning(catalog, single=True)
    result = TaskSQLResult(task_id='stock', status='ready', generation=generation(plan.draft.tasks[0], catalog, settings()))
    response = QueryPipelineResponse(run_id='x', status='error', planning=plan,
        task_results=[result], contract_fingerprint=catalog.fingerprint)
    assert response.task_results[0].generation is None
    assert result.generation.sql  # sanitization must not mutate private diagnostics
    assert 'SELECT' not in response.model_dump_json()


@pytest.mark.parametrize('ids', [('stock', 'stock'), ('unknown',)])
def test_duplicate_or_unknown_task_results_are_rejected(tmp_path, ids):
    catalog = catalog_at(tmp_path)
    with pytest.raises(ValidationError):
        QueryPipelineResponse(run_id='x', status='error', planning=planning(catalog),
            task_results=[TaskSQLResult(task_id=i, status='error') for i in ids],
            contract_fingerprint=catalog.fingerprint)


def test_render_task_request_preserves_legacy_payload(tmp_path):
    plan = planning(catalog_at(tmp_path), single=True)
    rendered = render_task_request(plan.draft.tasks[0])
    assert rendered == plan.prepared_requests[0].payload['request']
    assert rendered.splitlines()[0] == '只執行以下單一 View 資料查詢；保留全部條件及指定輸出粒度，不作跨來源整合或業務決策。'
    assert json.loads(rendered.split('\n', 1)[1]) == {
        'view': 'demo.stock', 'required_columns': ['store_id', 'product_id', 'stock_qty'],
        'filters': [], 'metrics': {}, 'conditional_metrics': [], 'metadata_collections': [],
        'attributes': ['stock_qty'], 'group_by': [], 'output_grain': ['store_id', 'product_id']}


def test_render_task_request_rejects_over_4000_characters(tmp_path):
    task = planning(catalog_at(tmp_path), single=True).draft.tasks[0]
    size = len(render_task_request(task))
    task.attributes.append('x' * (4000 - size - 4))
    assert len(render_task_request(task)) == 4000
    task.attributes[-1] += 'x'
    with pytest.raises(ValueError):
        render_task_request(task)


def test_pending_response_does_not_expose_trace_sql(tmp_path):
    from cpea.application.models.query import SQLGenerationResponse, QueryTaskTrace
    catalog = catalog_at(tmp_path)
    pending = SQLGenerationResponse(status='unsupported', supported=False, explanation='停止',
        query_trace=QueryTaskTrace(request='x', sql='SELECT private diagnostic'))
    result = TaskSQLResult(task_id='stock', status='unsupported', generation=pending)
    response = QueryPipelineResponse(run_id='x', status='unsupported', planning=planning(catalog),
        task_results=[result], contract_fingerprint=catalog.fingerprint)
    assert 'SELECT' not in response.model_dump_json()
