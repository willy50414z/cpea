"""Source selection needs complete evidence against every competing source."""
from types import SimpleNamespace

import pytest

from cpea.application.models.query import ClarificationRequest
from cpea.domain.models import SchemaLink
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow, ViewComparison


def compare(result, *, shortcut=False):
    request = '依地區分組，顯示核准預算合計。'
    schemas = {name: {'summary': summary, 'grain': grain, 'columns': {
        'amount': {'description': description}}} for name, summary, grain, description in [
        ('demo.v_budget', '每地區年度預算', '地區年度', '年度核定經費，單位元'),
        ('demo.v_actual', '每筆支出實績', '支出明細',
         '核准預算的實際使用金額，單位元' if shortcut else '已支付的實際費用，單位元')]}
    successful = [(name, {'links': SimpleNamespace(links=[SchemaLink(
        fact_text='核准預算' if shortcut else '核准預算合計',
        view=name, column='amount', role='metric', aggregation='sum')])}, {}, i)
        for i, name in enumerate(schemas)]
    calls = []
    workflow = SimpleNamespace(catalog=SimpleNamespace(fingerprint='test'),
        match_prompt=SimpleNamespace(version='v10'),
        _invoke_model=lambda *args, **kwargs: (calls.append(args) or ViewComparison.model_validate(result)))
    winner, clarification = SQLGenerationWorkflow._compare_valid_candidates(workflow, request, schemas, successful)
    return winner, clarification, calls


def selection():
    return {'decision': 'select', 'selected_view': 'demo.v_budget',
        'request_evidence': '核准預算', 'contract_evidence': '年度核定經費，單位元',
        'conflicts': [{'view': 'demo.v_actual', 'conflict_type': 'metric_definition', 'request_evidence': '核准預算',
                       'contract_evidence': '已支付的實際費用，單位元',
                       'reason': '核准額度與已付實績是不同指標，後者不能提供預算。'}]}


def test_paraphrased_selection_requires_grounded_competing_contract_conflicts():
    winner, clarification, _ = compare(selection())
    assert winner == 'demo.v_budget' and clarification is None


def test_multiple_distinct_grounded_conflicts_can_refute_one_competitor():
    result = selection()
    result['conflicts'].append({**result['conflicts'][0], 'request_evidence': '核准預算合計',
                               'reason': '預算合計與已付實績合計也不是相同指標。'})
    winner, clarification, _ = compare(result)
    assert winner == 'demo.v_budget' and clarification is None


@pytest.mark.parametrize('mutation', ['missing', 'quote', 'request', 'view', 'reason', 'duplicate', 'preference', 'type'])
def test_incomplete_or_fabricated_competitor_evidence_preserves_clarification(mutation):
    result = selection()
    if mutation == 'missing':
        result['conflicts'] = []
    elif mutation == 'duplicate':
        result['conflicts'] *= 2
    elif mutation == 'preference':
        result['conflicts'][0]['reason'] = '我較偏好預算來源，另一個順位較低。'
    elif mutation == 'type':
        result['conflicts'][0]['conflict_type'] = 'ranking'
    else:
        result['conflicts'][0][{'quote': 'contract_evidence', 'request': 'request_evidence'}.get(mutation, mutation)] = (
            '' if mutation == 'reason' else 'invented')
    winner, clarification, _ = compare(result)
    assert winner is None and isinstance(clarification, ClarificationRequest)


def test_single_short_phrase_cannot_override_the_complete_request():
    winner, clarification, calls = compare({'decision': 'clarify'}, shortcut=True)
    assert winner is None and clarification is not None
    assert len(calls) == 1
