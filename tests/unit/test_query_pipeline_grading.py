from copy import deepcopy

import pytest

from cpea.application.models.decomposition import DecompositionDraft
from cpea.workflows.task_decomposition.validation import prepare_requests
from evaluations.query_pipeline_grading import grade_pipeline_case, summarize_pipeline
from tests.decomposition_support import catalog_at
from tests.query_pipeline_support import planning


def case_for(plan):
    return dict(case_id='synthetic', request='目前庫存與九月銷量', expected_stage_status='sql_ready',
                expected_planning_status='ready', approved_plans=[plan.draft.model_dump()])


def test_task_order_and_ids_do_not_change_semantic_score(tmp_path):
    catalog = catalog_at(tmp_path)
    response = planning(catalog)
    case = case_for(response)
    response.draft.tasks.reverse()
    response.draft.tasks[0].task_id = 'b'
    response.draft.tasks[1].task_id = 'a'
    response.draft.integration.anchor_task = 'a'
    edge = response.draft.integration.edges[0]
    edge.left_task, edge.right_task, edge.preserve_task = 'a', 'b', 'a'
    response.prepared_requests = prepare_requests(response.draft, catalog)
    score = grade_pipeline_case(case, response, mode='planning', catalog=catalog)
    assert score['planning_semantics'] and score['automated_pass']
    assert score['semantic_review_required']
    assert score['supported_capability']


@pytest.mark.parametrize('change', ['period', 'channel', 'metric', 'grain', 'output', 'integration'])
def test_valid_schema_with_wrong_period_channel_metric_or_grain_fails_semantics(tmp_path, change):
    catalog = catalog_at(tmp_path)
    response = planning(catalog)
    case = case_for(response)
    task = response.draft.tasks[1]
    if change == 'period': task.filters[0].value = '2026-08-01'
    if change == 'channel': task.filters.pop()
    if change == 'metric': task.metrics['quantity'] = 'avg'
    if change == 'grain': task.output_grain = ['store_id']
    if change == 'output': task.attributes.append('order_date')
    if change == 'integration': response.draft.integration.edges[0].mode = 'inner'
    score = grade_pipeline_case(case, response, mode='planning', catalog=catalog)
    assert not score['planning_semantics']
    assert score['first_error_stage'] == 'planning'


def test_alternative_plan_must_be_complete_not_mixed_fragments(tmp_path):
    catalog = catalog_at(tmp_path)
    response = planning(catalog)
    case = case_for(response)
    alternate = deepcopy(case['approved_plans'][0])
    alternate['tasks'][0]['attributes'] = []
    alternate['tasks'][0]['required_columns'].remove('stock_qty')
    alternate['tasks'][1]['metrics']['quantity'] = 'avg'
    case['approved_plans'].append(alternate)
    response.draft.tasks[1].metrics['quantity'] = 'avg'
    assert not grade_pipeline_case(case, response, mode='planning', catalog=catalog)['planning_semantics']
    response.draft = DecompositionDraft.model_validate(alternate)
    response.prepared_requests = prepare_requests(response.draft, catalog)
    assert grade_pipeline_case(case, response, mode='planning', catalog=catalog)['planning_semantics']


def test_consistent_failure_is_not_stable_success():
    entries = [dict(case_id='a', round=i, status='completed', kind='natural',
                    grading=dict(automated_pass=False, success=False)) for i in range(3)]
    entries.append(dict(case_id='b', round=0, status='skipped', kind='natural'))
    result = summarize_pipeline(entries, planned=6, runs=3)
    assert result['success_rate'] == 0 and result['three_round_all_success'] == 0
    assert result['planned'] == 6 and result['unfinished'] == 2 and result['skipped'] == 1


def test_mode_response_type_mismatch_is_evaluation_error(tmp_path):
    catalog = catalog_at(tmp_path)
    with pytest.raises(ValueError):
        grade_pipeline_case(case_for(planning(catalog)), planning(catalog), mode='sql', catalog=catalog)


def test_correct_planning_with_sql_drift_is_attributed_downstream(tmp_path):
    from tests.unit.test_query_pipeline_workflow import service
    catalog = catalog_at(tmp_path)
    plan = planning(catalog)
    pipeline, _ = service(catalog, plan, failure=True)
    response = pipeline.invoke('原文')
    case = case_for(plan)
    score = grade_pipeline_case(case, response, mode='integrated', catalog=catalog)
    assert score['planning_semantics'] and score['first_error_stage'] == 'sql_generation'
    response.issues[0].stage = 'sql_validation'
    assert grade_pipeline_case(case, response, mode='integrated', catalog=catalog)['first_error_stage'] == 'sql_validation'
    response.planning.draft.tasks[1].filters.pop()
    assert grade_pipeline_case(case, response, mode='integrated', catalog=catalog)['first_error_stage'] == 'planning'


def test_pending_and_skipped_supported_cases_remain_in_denominator():
    entries = [dict(case_id='a', round=0, status='completed', kind='natural', supported_case=True,
        response={'status': 'needs_confirmation'}, grading={'automated_pass': False, 'success': False}),
        dict(case_id='b', round=0, status='skipped', kind='natural', supported_case=True)]
    result = summarize_pipeline(entries, planned=3, runs=1, support_planned=3)
    assert result['pending'] == 1
    assert result['support_planned'] == 3 and result['supported_success_rate'] == 0
    assert result['unfinished'] == 1
