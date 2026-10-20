import json
from pathlib import Path

from evaluations.hilp_cases import HilpCase, ConfirmationStep
from evaluations.governance_inputs import load_cases, ModelTarget
from evaluations.governance_runner import evaluate
from tests.hilp_support import QUESTION, runtime_for


def test_reviewed_script_runs_three_times_in_isolated_stores(tmp_path):
    root = tmp_path / 'profile'
    runtime = runtime_for(root)
    case = HilpCase(case_kind='hilp', case_id='HILP-001', profile_id=runtime.catalog.profile_id,
        contract_fingerprint=runtime.catalog.fingerprint, question=QUESTION,
        expected_initial_status='needs_confirmation', expected_terms=['含稅發票總額'],
        expected_columns=['order_amount'], verify_reuse=True,
        steps=[ConfirmationStep(action='confirm', choices={'含稅發票總額': 'order_amount'},
            expected_status='ready', expected_source='confirmed_this_request')])
    case = case.model_copy(update={'review_status': 'approved', 'reviewer': 'synthetic-test',
        'reviewed_at': '2026-10-16T00:00:00Z', 'reviewed_case_sha256': case.content_sha256(),
        'reviewed_contract_fingerprint': runtime.catalog.fingerprint})
    path = tmp_path / 'cases.jsonl'
    path.write_text(case.model_dump_json() + '\n', encoding='utf-8')
    loaded = load_cases(path).cases
    assert loaded[0].hilp_case.approved_for(runtime.catalog.fingerprint)
    target = ModelTarget(provider='local', transport='ollama', model='offline-test')
    output = tmp_path / 'evaluations' / 'test-run'
    results, calls = evaluate(loaded, [target], runtime=runtime, output=output, runs=3,
        concurrency=1, live=False, model_factory=lambda target, settings: runtime.llm,
        repo_root=Path(__file__).resolve().parents[2], allowed_output_root=output.parent)
    assert len(results) == 3 and all(r['status'] == 'pass' for r in results)
    assert all([p['status'] for p in r['hilp_phases']] == ['needs_confirmation', 'ready', 'ready'] for r in results)
    assert len(calls) == 6  # Two initial questions per case; resume adds zero MATCH.
    assert not (root / 'terms_mapping.json').exists()
    summary = json.loads((output / 'hilp_summary.json').read_text(encoding='utf-8'))
    assert summary['semantic_false_accepts'] == 0
    assert summary['cases_stable_and_passing_three_repetitions'] == 1
    runtime.close()
