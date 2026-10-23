"""Runner integration with synthetic offline artifacts only."""
import json
import os
from pathlib import Path
import subprocess
import sys
import pytest

from tests.decomposition_support import catalog_at
from tests.unit.test_wrenai_node_oracles import approve, oracle_case
from tests.unit.test_wrenai_replay import recording


def test_offline_runner_help_and_regrade_do_not_disclose_private_artifacts(tmp_path):
    catalog = catalog_at(tmp_path / 'catalog')
    root = tmp_path / 'run'
    recording(root, catalog)
    cases = tmp_path / 'cases.jsonl'
    cases.write_text(json.dumps(approve(oracle_case(catalog), catalog)) + '\n', encoding='utf-8')
    command = [sys.executable, '-m', 'evaluations.wrenai_runner']
    help_result = subprocess.run([*command, '--help'], text=True, capture_output=True)
    assert help_result.returncode == 0
    assert 'regrade' in help_result.stdout and 'replay' in help_result.stdout
    result = subprocess.run([*command, 'regrade', str(root), '--profile', str(tmp_path / 'catalog'),
                             '--cases', str(cases), '--case-id', 'synthetic-only'], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary['automated_pass'] is True and summary['cost_complete'] is False
    assert 'private request sentinel' not in result.stdout
    assert 'response sentinel' not in result.stdout


def test_runner_rejects_live_and_does_not_echo_secret_exception(tmp_path):
    command = [sys.executable, '-m', 'evaluations.wrenai_runner']
    result = subprocess.run([*command, 'live'], text=True, capture_output=True)
    assert result.returncode != 0
    malformed = tmp_path / 'secret-key-should-not-appear'
    result = subprocess.run([*command, 'replay', str(malformed), '--runtime-identity', str(malformed)], text=True, capture_output=True)
    assert result.returncode != 0
    assert 'secret-key-should-not-appear' not in result.stdout + result.stderr


@pytest.mark.skipif(not os.environ.get('WRENAI_OFFLINE_RECORDING'), reason='requires explicit fake-transport native recording')
def test_recorded_native_graph_regrades_and_reexecutes_offline():
    """Explicit opt-in fixture: real pinned graph/Qdrant, fake model transport."""
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    from evaluations.wrenai_replay import regrade, replay
    root = Path(os.environ['WRENAI_OFFLINE_RECORDING']).resolve()
    repo = Path(__file__).resolve().parents[2]
    catalog = SchemaCatalog(repo / 'projects/retail')
    view = 'demo_retail.v_customer_value'
    # Independent, synthetic fixture contract; no expected data read from Draft.
    case = {'case_id': 'offline-customer', 'request': 'customer_id',
            'contract_fingerprint': catalog.fingerprint, 'expected_status': 'ready',
            'expected_strategy': 'single_view',
            'expected_tasks': [{'task_id': 'customer', 'view': view, 'required_columns': ['customer_id'],
                                'output_grain': ['customer_id']}],
            'expected_integration': {'anchor_task': 'customer', 'keys': ['customer_id'], 'mode': 'left',
                                     'edges': [], 'null_policy': 'preserve_null'},
            'node_oracles': {'intent': {'acceptable_intents': ['TEXT_TO_SQL'], 'required_facts': [['customer_id']]},
                             'retrieval': {'required_columns': {view: list(catalog.columns(view))}}}}
    score = regrade(root, case, catalog)
    assert score['automated_pass'] and score['cost_complete'] is False
    metadata = json.loads((root / 'runtime.json').read_text(encoding='utf-8'))
    original = json.loads((root / 'response.json').read_text(encoding='utf-8'))
    ledger = json.loads((root / 'ledger.json').read_text(encoding='utf-8'))
    repeated = replay(root, runtime_identity=metadata['identity'])
    assert repeated['draft'] == original['draft']
    assert repeated['artifacts']['run_dir'] != str(root)
    assert repeated['exact_reproduction'] is True
    assert repeated['replay_mode'] == 'native_graph'
    assert repeated['replay']['transport_calls'] == len(ledger['calls'])
