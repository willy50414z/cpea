"""Offline contracts for research strategies; no product schema changes."""
import json

import pytest
from pydantic import ValidationError

from evaluations.query_pipeline_grading import content_hash


def api():
    from evaluations import query_pipeline_experiments
    return query_pipeline_experiments


def descriptor(**updates):
    return api().StrategyDescriptor(**(dict(strategy_id='A1', strategy_version='1',
        adapter_id='coverage', adapter_version='1', implementation_kind='research_candidate',
        capabilities=['capability_resolution'], input_kind='approved_recall', output_kind='native_coverage',
        native_schema_id='coverage', native_schema_version='1', requires_model=True,
        requires_db=False, dialects=['postgres']) | updates))


def fixed_input(**updates):
    return api().EvaluationInput(**(dict(case_ref='private/cases/0000.json', case_sha256='a' * 64,
        request='門市商品庫存', catalog_snapshot={'views': ['inventory']},
        catalog_fingerprint=content_hash({'views': ['inventory']}),
        catalog_snapshot_sha256=content_hash({'views': ['inventory']}),
        capability='capability_resolution', input_origin='approved_recall',
        upstream_injected=True, upstream={'requirements': ['庫存']},
        approval_ref='private/approvals/0000.json', upstream_sha256=content_hash({'requirements': ['庫存']})) | updates))


def test_model_context_excludes_case_identity_and_approval_metadata():
    value = fixed_input()
    context = value.model_context()
    assert set(context) == {'request', 'catalog', 'upstream'}
    assert 'case_ref' not in json.dumps(context)
    context['catalog']['views'].clear()
    assert value.catalog_snapshot['views'] == ['inventory']


@pytest.mark.parametrize('updates', [dict(oracle='secret'), dict(upstream_injected=False),
    dict(approval_ref=None), dict(upstream_sha256='b' * 64), dict(catalog_snapshot_sha256='c' * 64)])
def test_input_rejects_oracles_and_unapproved_or_drifted_injection(updates):
    with pytest.raises((ValueError, ValidationError)):
        fixed_input(**updates)


def test_partial_candidate_cannot_enter_complete_planning_scope():
    with pytest.raises(ValueError, match='responsibility'):
        api().validate_strategy(descriptor(), fixed_input(), scope='complete_planning')
    api().validate_strategy(descriptor(), fixed_input(), scope='internal_coverage')


def test_db_candidate_rejected_before_any_call():
    with pytest.raises(ValueError, match='DB'):
        api().validate_strategy(descriptor(requires_db=True), fixed_input(), scope='internal_coverage')


def test_unknown_observation_fields_are_not_invented():
    value = api().StrategyObservation(node_id='coverage', native_schema_id='coverage',
        native_schema_version='1', status='failed', first_error='parse_error')
    assert value.normalized is None and value.input_tokens is None
    assert value.output_tokens is None and value.calls == 0 and value.retries == 0
    assert 'own_gap' not in value.model_dump()


def test_manifest_requires_frozen_cells_and_keeps_all_trials():
    m = api().ExperimentManifest(experiment_id='pilot', scope='internal_coverage', mode='planning',
        case_hashes=['a' * 64, 'b' * 64], strategies=[descriptor()], runs=2,
        group='Diagnostic', preregistration_ref='private/approval.json')
    assert m.planned == 4
    assert m.result_completeness == 'not_tested'
    with pytest.raises(ValueError):
        api().ExperimentManifest(**(m.model_dump(exclude={'planned'}) | {'case_hashes': []}))


def test_reuse_existing_case_loader_and_real_catalog_fingerprint(tmp_path):
    from evaluations.query_pipeline_cases import evaluation_input
    from tests.integration.test_query_pipeline_runner import dataset
    catalog, _, path = dataset(tmp_path)
    case = json.loads(path.read_text(encoding='utf-8'))[0]
    value = evaluation_input(case, catalog, capability='query_planning', case_ref='private/cases/0000.json')
    assert value.catalog_fingerprint == catalog.fingerprint
    assert value.catalog_snapshot_sha256 == content_hash(value.catalog_snapshot)
    assert value.catalog_fingerprint != value.catalog_snapshot_sha256
    assert 'oracle-secret-id' not in json.dumps(value.model_context())
    assert 'approved_plans' not in value.model_context()


def test_upstream_rejects_oracle_metadata_recursively():
    upstream = {'tasks': [{'expected_sql': 'oracle'}]}
    with pytest.raises(ValueError, match='oracle'):
        fixed_input(upstream=upstream, upstream_sha256=content_hash(upstream))


def test_manifest_rejects_scope_mode_mismatch():
    with pytest.raises(ValueError, match='scope/mode'):
        api().ExperimentManifest(experiment_id='wrong-mode', scope='single_view_sql', mode='planning',
            case_hashes=['a' * 64], strategies=[descriptor()], runs=1,
            group='Diagnostic', preregistration_ref='private/approval.json')
