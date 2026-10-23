"""Evaluator-only synthetic fixtures; these are not a benchmark dataset."""
from copy import deepcopy
import json

import pytest

from evaluations.decomposition_cases import case_sha256
from tests.decomposition_support import catalog_at, draft


def oracle_case(catalog):
    data = draft()
    return {
        'case_id': 'synthetic-only', 'profile_id': catalog.profile_id,
        'contract_fingerprint': catalog.fingerprint, 'request': '庫存與九月銷量',
        'expected_status': 'ready', 'expected_strategy': 'multi_view',
        'expected_tasks': deepcopy(data['tasks']),
        'expected_integration': {
            'anchor_task': 'stock', 'keys': ['store_id', 'product_id'], 'mode': 'left',
            'edges': deepcopy(data['integration']['edges']),
            'null_policy': 'preserve_null',
        },
    }


def approve(case, catalog):
    case['case_sha256'] = case_sha256(case)
    case.update(review_status='approved', reviewer='synthetic-reviewer', reviewed_at='2026-10-23',
                reviewed_case_sha256=case_sha256(case), reviewed_contract_fingerprint=catalog.fingerprint)
    return case


def run_for(catalog, data=None):
    from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
    from cpea.workflows.task_decomposition.validation import prepare_requests
    d = DecompositionDraft.model_validate(data or draft())
    try:
        prepared = prepare_requests(d, catalog)
    except ValueError:
        # Deliberately invalid recorded response; grading must reject it rather
        # than having the fixture constructor reject it before the evaluator.
        prepared = [{'task_id': t.task_id, 'view': t.view,
                     'payload': {'request': t.request, 'history': []}} for t in d.tasks]
    return {'response': DecompositionResponse(
        status=d.status, draft=d, contract_fingerprint=catalog.fingerprint,
        prepared_requests=prepared if d.status == 'ready' else [],
    ).model_dump()}


@pytest.mark.parametrize('mutation', [
    'extra_metric', 'extra_conditional', 'missing_filter', 'wrong_negation', 'wrong_end',
    'cross_source', 'anchor', 'preserve', 'cardinality', 'zero_fill', 'background_sum', 'background_preparation',
])
def test_semantic_mutation_cannot_hide_behind_schema_validity(tmp_path, mutation):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    case = oracle_case(catalog)
    if mutation == 'cross_source':
        case['expected_tasks'][1]['filters'].append({'column': 'product_id', 'operator': '!=', 'value': 999})
    baseline = deepcopy(draft())
    if mutation == 'cross_source':
        baseline['tasks'][1]['filters'].append({'column': 'product_id', 'operator': '!=', 'value': 999})
    assert grade_wrenai_run(case, run_for(catalog, baseline), catalog)['automated_pass']
    data = deepcopy(baseline)
    stock, sales = data['tasks']
    if mutation == 'extra_metric':
        sales['metrics']['product_id'] = 'count'
    elif mutation == 'extra_conditional':
        sales['conditional_metrics'] = [{'column': 'quantity', 'aggregation': 'sum',
                                        'conditions': [{'column': 'quantity', 'operator': '>', 'value': 1}]}]
    elif mutation == 'missing_filter':
        sales['filters'].pop()
    elif mutation == 'wrong_negation':
        sales['filters'][0]['operator'] = '!='
    elif mutation == 'wrong_end':
        sales['filters'][1]['value'] = '2026-10-02'
    elif mutation == 'cross_source':
        stock['filters'] = [sales['filters'].pop()]
    elif mutation == 'anchor':
        data['integration']['anchor_task'] = 'sales'
    elif mutation == 'preserve':
        data['integration']['edges'][0]['preserve_task'] = 'sales'
    elif mutation == 'cardinality':
        data['integration']['edges'][0]['cardinality'] = 'many_to_many'
    elif mutation == 'zero_fill':
        data['integration']['missing_data_policy'] = '缺值一律補零'
    elif mutation == 'background_sum':
        stock['metrics'] = {'stock_qty': 'sum'}
        stock['group_by'] = stock['output_grain']
    elif mutation == 'background_preparation':
        data['integration']['preparation'] = [{'task_id': 'stock', 'kind': 'aggregate',
                                               'keys': ['store_id', 'product_id'], 'description': '背景數值再次加總'}]
    assert not grade_wrenai_run(case, run_for(catalog, data), catalog)['automated_pass']


def test_task_renaming_order_and_approved_null_paraphrase_are_equivalent(tmp_path):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    data = draft()
    names = {'stock': 'a', 'sales': 'b'}
    data['tasks'].reverse()
    for task in data['tasks']: task['task_id'] = names[task['task_id']]
    integration = data['integration']
    integration['anchor_task'] = 'a'
    for edge in integration['edges']:
        for field in ('left_task', 'right_task', 'preserve_task'): edge[field] = names[edge[field]]
    integration['missing_data_policy'] = 'Keep unmatched rows and preserve NULL; never fill with zero.'
    assert grade_wrenai_run(oracle_case(catalog), run_for(catalog, data), catalog)['automated_pass']


def test_helper_columns_date_equivalence_and_free_reason_are_allowed(tmp_path):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    data = draft()
    data['tasks'][0]['required_columns'].append('snapshot_date')
    data['tasks'][1]['filters'][1] = {'column': 'order_date', 'operator': '<=', 'value': '2026-09-30'}
    data['integration']['notes'] = ['自由說明不需與 oracle 文字一致']
    assert grade_wrenai_run(oracle_case(catalog), run_for(catalog, data), catalog)['automated_pass']


@pytest.mark.parametrize('corruption', ['duplicate', 'catalog', 'content', 'review', 'unapproved', 'unknown_field'])
def test_loader_rejects_invalid_or_unapproved_cases(tmp_path, corruption):
    from evaluations.wrenai_cases import load_wrenai_cases
    catalog = catalog_at(tmp_path / 'catalog')
    case = approve(oracle_case(catalog), catalog)
    if corruption == 'catalog': case['contract_fingerprint'] = 'stale'
    if corruption == 'content': case['request'] = 'tampered'
    if corruption == 'review': case['reviewed_contract_fingerprint'] = 'stale'
    if corruption == 'unapproved': case['review_status'] = 'pending'
    if corruption == 'unknown_field':
        case['expected_tasks'][0]['required_columns'].append('unknown')
        approve(case, catalog)
    cases = [case, case] if corruption == 'duplicate' else [case]
    path = tmp_path / 'cases.jsonl'
    path.write_text(''.join(json.dumps(c) + '\n' for c in cases), encoding='utf-8')
    with pytest.raises(ValueError): load_wrenai_cases(path, catalog)


@pytest.mark.parametrize('status', ['unsupported', 'needs_clarification', 'error'])
def test_nonready_case_does_not_require_ready_tasks_or_integration(tmp_path, status):
    from evaluations.wrenai_cases import load_wrenai_cases, model_input
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path / 'catalog')
    case = oracle_case(catalog)
    case.update(expected_status=status, oracle_notes='EXPECTED_SENTINEL', alternatives=['ANSWER_SENTINEL'])
    for key in ('expected_tasks', 'expected_integration', 'expected_strategy'): case.pop(key)
    approve(case, catalog)
    path = tmp_path / 'cases.jsonl'
    path.write_text(json.dumps(case) + '\n', encoding='utf-8')
    loaded = load_wrenai_cases(path, catalog)[0]
    assert model_input(loaded) == {'request': case['request'], 'case_id': case['case_id']}
    run = run_for(catalog, {'status': status})
    assert grade_wrenai_run(loaded, run, catalog)['automated_pass']


def test_node_raw_selection_and_rendered_schema_are_independent(tmp_path):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    case = oracle_case(catalog)
    case['node_oracles'] = {
        'retrieval': {'required_columns': {'demo.sales': ['quantity', 'order_date']},
                      'allowed_helper_columns': {'demo.sales': ['store_id']}}
    }
    run = run_for(catalog)
    run['nodes'] = {'retrieval': {
        'raw_selection': {'demo.sales': ['quantity', 'order_date', 'store_id']},
        'rendered_columns': {'demo.sales': ['quantity']}}}
    score = grade_wrenai_run(case, run, catalog)
    assert score['node_scores']['retrieval']['raw_selection']['pass']
    assert not score['node_scores']['retrieval']['rendered_columns']['pass']
    assert not score['automated_pass']


def test_ready_oracle_sentinels_are_excluded_from_model_input(tmp_path):
    from evaluations.wrenai_cases import model_input
    catalog = catalog_at(tmp_path)
    case = oracle_case(catalog)
    case['expected_tasks'][0]['request'] = 'EXPECTED_TASK_SENTINEL'
    case['oracle_notes'] = 'ORACLE_NOTES_SENTINEL'
    case['alternatives'] = ['ALTERNATIVE_SENTINEL']
    assert model_input(case) == {'case_id': 'synthetic-only', 'request': '庫存與九月銷量'}


def test_intent_rewrite_must_keep_oracle_facts_without_matching_reasoning(tmp_path):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    case = oracle_case(catalog)
    case['node_oracles'] = {'intent': {
        'acceptable_intents': ['TEXT_TO_SQL'],
        'required_facts': [['2026-09-01'], ['2026-10-01'], ['排除', '不包含'], ['未下單', '沒有下單']],
    }}
    run = run_for(catalog)
    run['nodes'] = {'intent': {'intent': 'TEXT_TO_SQL',
                              'rephrased_question': '2026-09-01 至 2026-10-01 排除退貨，包含未下單會員',
                              'reasoning': '自由理由'}}
    assert grade_wrenai_run(case, run, catalog)['automated_pass']
    run['nodes']['intent']['rephrased_question'] = '2026-09-01 至 2026-10-01 包含會員'
    assert not grade_wrenai_run(case, run, catalog)['automated_pass']


@pytest.mark.parametrize('policy', ['不保留未匹配資料，缺值仍為 NULL',
                                    '保留未匹配資料，將缺值設為0',
                                    'Preserve unmatched rows; set missing values to 0',
                                    '保留未匹配資料，缺值一律刪除',
                                    '保留未匹配資料，缺值資料直接排除',
                                    'Preserve unmatched rows; missing values must be discarded.'])
def test_null_policy_cannot_pass_on_a_preserve_keyword_alone(tmp_path, policy):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    data = draft()
    data['integration']['missing_data_policy'] = policy
    assert not grade_wrenai_run(oracle_case(catalog), run_for(catalog, data), catalog)['automated_pass']


def test_response_ready_cannot_mask_nonready_draft_to_skip_validation(tmp_path):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    run = run_for(catalog)
    run['response']['draft']['status'] = 'unsupported'
    assert not grade_wrenai_run(oracle_case(catalog), run, catalog)['automated_pass']


@pytest.mark.parametrize('corruption', ['view', 'request'])
def test_prepared_payload_must_represent_its_own_task(tmp_path, corruption):
    from evaluations.wrenai_oracles import grade_wrenai_run
    catalog = catalog_at(tmp_path)
    run = run_for(catalog)
    prepared = run['response']['prepared_requests'][0]
    if corruption == 'view': prepared['view'] = 'demo.sales'
    else: prepared['payload']['request'] = 'an unrelated requirement'
    assert not grade_wrenai_run(oracle_case(catalog), run, catalog)['automated_pass']
