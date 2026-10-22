import pytest
from pydantic import ValidationError

from cpea.application.models.decomposition import (
    DecompositionDraft, DecompositionResponse, ExplainedDecompositionDraft,
    PlanningDecisionSummary,
)
from evaluations.decision_summary_comparison import finish_explained, decision_messages
from tests.decomposition_support import catalog_at, draft


def summary():
    return dict(source_selection='各來源具備對應需求欄位。', field_roles='庫存原值、銷量加總。',
                conditions='期間只套用銷售來源。', grain='每店每商品。',
                population='保留所有庫存商品。', integration='按店商品左接。')


def test_summary_is_required_and_all_six_sections_are_nonempty():
    with pytest.raises(ValidationError):
        ExplainedDecompositionDraft.model_validate(draft())
    for section in summary():
        for empty in ('', '   '):
            bad = summary();bad[section] = empty
            with pytest.raises(ValidationError):PlanningDecisionSummary.model_validate(bad)


def test_existing_v3_models_keep_the_original_response_contract():
    assert 'decision_summary' not in DecompositionDraft.model_json_schema()['properties']
    assert 'decision_summary' not in DecompositionResponse.model_json_schema()['properties']
    assert 'decision_summary' in ExplainedDecompositionDraft.model_json_schema()['required']


def test_response_preserves_summary_without_changing_dispatch_payload(tmp_path):
    catalog = catalog_at(tmp_path)
    first = ExplainedDecompositionDraft.model_validate({**draft(),'decision_summary':summary()})
    second = first.model_copy(deep=True)
    second.decision_summary.source_selection = '另一份模型輸出的簡短決策說明。'
    a,b = finish_explained(first,catalog),finish_explained(second,catalog)
    assert a.status == b.status == 'ready'
    assert a.prepared_requests == b.prepared_requests
    assert a.model_dump()['decision_summary'] == summary()
    assert 'decision_summary' not in a.model_dump()['draft']
    assert all('決策說明' not in p.payload['request'] for p in b.prepared_requests)


def test_explanations_do_not_make_an_invalid_plan_dispatchable(tmp_path):
    data = draft();data['tasks'][1]['metrics'] = {'invented_order_count':'count'}
    data['decision_summary'] = summary()
    response = finish_explained(ExplainedDecompositionDraft.model_validate(data),catalog_at(tmp_path))
    assert response.status == 'error' and response.prepared_requests == []
    assert response.decision_summary.population == summary()['population']


def test_model_context_contains_summary_schema_but_no_oracle(tmp_path):
    msgs = decision_messages('QUESTION_SENTINEL',catalog_at(tmp_path))
    text = '\n'.join(m.content for m in msgs)
    assert 'decision_summary' in text and 'QUESTION_SENTINEL' in text
    assert 'expected_tasks' not in text and 'case_id' not in text
