"""Offline artifact validation; native graph execution is integration-tested separately."""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import socket

import pytest

from tests.decomposition_support import catalog_at
from tests.unit.test_wrenai_node_oracles import oracle_case, run_for


def fingerprint(value):
    return sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def recording(path, catalog):
    path.mkdir()
    payload = {'request': '庫存與九月銷量', 'case_id': 'synthetic-only',
               'catalog_fingerprint': catalog.fingerprint, 'response_schema': {'type': 'object'}}
    identity = {k: 'fixture-' + k for k in (
        'upstream_sha', 'patch_sha', 'lock_sha256', 'python_version', 'model', 'embedding_model',
        'tokenizer', 'prompt_sha256', 'index_identity', 'configuration_sha256')}
    identity.update(input_sha256=fingerprint(payload), catalog_fingerprint=catalog.fingerprint,
                    schema_sha256=fingerprint(payload['response_schema']))
    contents = {'runtime.json': {'identity': identity, 'fixture_source': 'fake'},
                'input.json': payload, 'response.json': run_for(catalog)['response'],
                'ledger.json': {'calls': ['call-1.json'], 'transport_complete': True},
                'call-1.json': {'run_id': 'r', 'case_id': 'synthetic-only', 'node_id': 'draft',
                                'call_id': 'call-1', 'batch_id': None, 'attempt': 1,
                                'kind': 'completion', 'request': {'model': 'offline'},
                                'request_fingerprint': fingerprint({'model': 'offline'}),
                                'raw_response': {'private': 'response sentinel'}, 'status': 'response',
                                'money': {'status': 'unknown', 'amount': None}}}
    for name, value in contents.items(): (path / name).write_text(json.dumps(value), encoding='utf-8')
    return identity


@pytest.mark.parametrize('key', ['upstream_sha', 'patch_sha', 'lock_sha256', 'python_version', 'model',
                                 'embedding_model', 'tokenizer', 'prompt_sha256', 'schema_sha256',
                                 'input_sha256', 'catalog_fingerprint', 'index_identity', 'configuration_sha256'])
def test_each_runtime_identity_mismatch_refuses_graph_execution(tmp_path, monkeypatch, key):
    from evaluations.wrenai_replay import replay
    catalog = catalog_at(tmp_path / 'catalog')
    identity = recording(tmp_path / 'run', catalog)
    identity[key] = 'drift'
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('must reject before executing graph'))
    with pytest.raises(ValueError, match='identity'):
        replay(tmp_path / 'run', runtime_identity=identity)


def test_regrade_uses_only_recorded_response_and_keeps_unknown_cost(tmp_path, monkeypatch):
    from evaluations.wrenai_replay import regrade
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    recording(root, catalog)
    monkeypatch.setattr(socket, 'create_connection', lambda *a, **kw: pytest.fail('network forbidden'))
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('regrade must not start worker'))
    result = regrade(root, oracle_case(catalog), catalog)
    assert result['automated_pass']
    assert result['cost_complete'] is False
    assert result['spend'] is None
    assert root.stat().st_mode & 0o777 == 0o700
    assert all(p.stat().st_mode & 0o777 == 0o600 for p in root.glob('*.json'))


def test_regrade_refuses_same_case_id_with_different_user_request(tmp_path):
    from evaluations.wrenai_replay import regrade
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    recording(root, catalog)
    case = oracle_case(catalog)
    case['request'] = 'a different requirement'
    with pytest.raises(ValueError, match='request'):
        regrade(root, case, catalog)


def test_regrade_resolves_native_raw_selection_and_rendered_ddl_separately(tmp_path):
    from evaluations.wrenai_replay import regrade
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    recording(root, catalog)
    payload = json.loads((root / 'input.json').read_text(encoding='utf-8'))
    payload['schema'] = {'model_to_view': {'m_sales': 'demo.sales'}}
    metadata = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    metadata['identity']['input_sha256'] = fingerprint(payload)
    rows = {
        'input.json': payload, 'runtime.json': metadata,
        'response.json': {'response': run_for(catalog)['response'], 'nodes': {'retrieval': {
            'raw_selection': {'demo.sales': ['quantity', 'order_date']},
            'rendered_columns': {'demo.sales': ['quantity', 'order_date']}}}},
        'intent.json': {'intent': 'TEXT_TO_SQL', 'rephrased_question': '九月銷量'},
        'retrieval_schema-raw.json': {'results': [{'table_name': 'm_sales',
                                                  'table_contents': {'columns': ['quantity', 'order_date']}}]},
        'retrieval-rendered.json': {'retrieval_results': [{'table_name': 'm_sales',
                                    'table_ddl': 'CREATE TABLE m_sales (\n  quantity NUMERIC\n);'}]},
    }
    for name, value in rows.items(): (root / name).write_text(json.dumps(value), encoding='utf-8')
    case = oracle_case(catalog)
    case['node_oracles'] = {'retrieval': {'required_columns': {'demo.sales': ['quantity', 'order_date']}}}
    score = regrade(root, case, catalog)
    assert score['node_scores']['retrieval']['raw_selection']['pass']
    assert not score['node_scores']['retrieval']['rendered_columns']['pass']
    assert not score['automated_pass']


@pytest.mark.parametrize('mutation', ['input', 'call_path', 'attempt', 'request', 'missing_call', 'case_id'])
def test_corrupt_artifact_cannot_be_replayed(tmp_path, mutation, monkeypatch):
    from evaluations.wrenai_replay import replay
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    identity = recording(root, catalog)
    file = 'input.json' if mutation == 'input' else 'ledger.json' if mutation in {'call_path', 'missing_call'} else 'call-1.json'
    obj = json.loads((root / file).read_text(encoding='utf-8'))
    if mutation == 'input': obj['request'] = 'tampered'
    if mutation == 'call_path': obj['calls'] = ['../escape.json']
    if mutation == 'attempt': obj['attempt'] = 2
    if mutation == 'request': obj['request'] = {'model': 'tampered'}
    if mutation == 'missing_call': obj['calls'] = []
    if mutation == 'case_id': obj['case_id'] = 'a-different-case'
    (root / file).write_text(json.dumps(obj), encoding='utf-8')
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('corrupt artifacts must not enter graph'))
    with pytest.raises(ValueError): replay(root, runtime_identity=identity)


def test_oracle_keys_are_refused_even_in_consistently_fingerprinted_input(tmp_path, monkeypatch):
    from evaluations.wrenai_replay import replay
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    identity = recording(root, catalog)
    payload = json.loads((root / 'input.json').read_text(encoding='utf-8'))
    payload['expected_tasks'] = ['DO_NOT_SEND_ORACLE_SENTINEL']
    identity['input_sha256'] = fingerprint(payload)
    metadata = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    metadata['identity'] = identity
    for name, value in [('input.json', payload), ('runtime.json', metadata)]:
        (root / name).write_text(json.dumps(value), encoding='utf-8')
    monkeypatch.setattr('subprocess.run', lambda *a, **kw: pytest.fail('oracle-bearing input must not enter graph'))
    with pytest.raises(ValueError, match='input'):
        replay(root, runtime_identity=identity)


@pytest.mark.parametrize('changed_identity', [True, False])
def test_graph_result_must_be_newly_executed_and_drift_is_marked(tmp_path, monkeypatch, changed_identity):
    from evaluations.wrenai_replay import replay
    from types import SimpleNamespace
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    identity = recording(root, catalog)
    if changed_identity:
        identity['model'] = 'changed-model'
    # This unit test exercises the process boundary only, not native semantics.
    def graph(command, **kwargs):
        assert 'native_worker.replay' in command
        assert '--allow-drift' in command
        assert kwargs['env']['PYTHONPATH'].endswith('integrations/wrenai')
        assert kwargs['env']['LANGFUSE_ENABLED'] == 'false'
        assert kwargs['env']['HAYSTACK_TELEMETRY_ENABLED'] == 'false'
        assert kwargs['env']['LITELLM_LOCAL_MODEL_COST_MAP'] == 'true'
        return SimpleNamespace(returncode=0, stdout=json.dumps({'draft': {'status': 'unsupported'}}), stderr='private-error-sentinel')
    monkeypatch.setattr('subprocess.run', graph)
    result = replay(root, runtime_identity=identity, allow_drift=True)
    assert result['draft']['status'] == 'unsupported'
    assert result['exact_reproduction'] is False
    assert result['identity_drift'] == (['model'] if changed_identity else [])
    assert 'private-error-sentinel' not in json.dumps(result)
