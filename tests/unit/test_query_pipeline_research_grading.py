"""Requirement projections do not invent missing native capabilities."""
from copy import deepcopy

import pytest

from evaluations.query_pipeline_grading import content_hash


def rules():
    return {'version': 'offline-v1', 'alternatives': [[
        {'requirement_id': 'scope', 'obligation': '九月資料', 'pointer': '/scope', 'expected': '2026-09'},
        {'requirement_id': 'population', 'obligation': '庫存母體', 'pointer': '/population', 'expected': 'inventory'},
        {'requirement_id': 'mapping', 'obligation': '庫存欄位', 'pointer': '/mapping', 'expected': ['stock_qty'], 'match': 'set'},
    ]]}


def assess(actual, **kwargs):
    from evaluations.query_pipeline_grading import assess_requirements
    return assess_requirements(actual, rules=rules(), input_sha256='input', **kwargs)


def test_equivalent_native_projection_covers_each_requirement_without_claiming_sql_or_db():
    value = assess({'scope': '2026-09', 'population': 'inventory', 'mapping': ['stock_qty']})
    assert all(r.verdict == 'PASS' for r in value.requirements)
    assert value.layers['requirements'] == 'PASS'
    assert value.layers['sql_static'] == 'NOT_OBSERVED' and value.layers['natural'] == 'NOT_OBSERVED'
    assert not value.independent_approval and not value.natural_success
    assert value.result_completeness == 'not_tested'


@pytest.mark.parametrize('key,value', [('scope', '2026-08'), ('population', 'sales'),
    ('mapping', ['stock_qty', 'irrelevant_id'])])
def test_mutations_fail_the_affected_obligation(key, value):
    actual = dict(scope='2026-09', population='inventory', mapping=['stock_qty'])
    actual[key] = value
    result = assess(actual)
    assert next(r for r in result.requirements if r.requirement_id == key).verdict == 'FAIL'
    assert result.first_error == 'requirements'


def test_unobserved_own_gap_and_missing_filter_are_not_pass():
    result = assess({'mapping': ['stock_qty']})
    assert result.requirements[0].verdict == 'NOT_OBSERVED'
    assert not any(r.requirement_id == 'own_gap' for r in result.requirements)
    assert result.layers['requirements'] == 'NOT_OBSERVED'


def test_cannot_mix_fragments_of_different_legal_alternatives():
    from evaluations.query_pipeline_grading import assess_requirements
    alternatives = rules()
    other = deepcopy(alternatives['alternatives'][0])
    other[0]['expected'], other[1]['expected'] = '2026-08', 'sales'
    alternatives['alternatives'].append(other)
    result = assess_requirements(dict(scope='2026-09', population='sales', mapping=['stock_qty']),
        rules=alternatives, input_sha256='input')
    assert result.layers['requirements'] == 'FAIL'


def test_approval_requires_independent_reviewer_and_exact_input_output_rule_hashes():
    actual = dict(scope='2026-09', population='inventory', mapping=['stock_qty'])
    review = dict(author='proposer', reviewer='independent', reviewed_at='2026-10-22', decision='approved',
        input_sha256='input', artifact_sha256=content_hash(actual), rules_sha256=content_hash(rules()))
    assert assess(actual, review=review).independent_approval
    for change in (dict(reviewer='proposer'), dict(input_sha256='drift'),
                   dict(artifact_sha256='drift'), dict(rules_sha256='drift')):
        assert not assess(actual, review=review | change).independent_approval
    # Even reviewed isolated projections cannot claim a complete natural flow.
    assert not assess(actual, review=review).natural_success


def test_oracle_calibration_keeps_disputes_and_unknowns_in_denominator():
    from evaluations.query_pipeline_grading import calibrate_oracle
    result = calibrate_oracle([
        dict(independent_verdict='legal', automated_pass=False),
        dict(independent_verdict='legal', automated_pass=True),
        dict(independent_verdict='illegal', automated_pass=True),
        dict(independent_verdict='illegal', automated_pass=False),
        dict(independent_verdict='disputed', automated_pass=False),
        dict(independent_verdict='unknown', automated_pass=None)])
    assert result['planned'] == 6 and result['disputed'] == 1 and result['unobserved'] == 1
    assert result['false_reject'] == {'numerator': 1, 'denominator': 2, 'rate': .5}
    assert result['false_accept'] == {'numerator': 1, 'denominator': 2, 'rate': .5}
    assert result['approval_verified'] is False


def test_mapping_metrics_penalize_irrelevant_identifiers_and_keep_unknowns():
    from evaluations.query_pipeline_grading import mapping_metrics
    result = mapping_metrics(expected=['stock_qty'], observed=['stock_qty', 'unrelated_id'])
    assert result['recall']['rate'] == 1 and result['precision']['rate'] == .5
    unknown = mapping_metrics(expected=['stock_qty'], observed=None)
    assert unknown['recall']['rate'] is None and unknown['precision']['rate'] is None
