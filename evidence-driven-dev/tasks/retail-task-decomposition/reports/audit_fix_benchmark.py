"""重播固定版本的規劃回覆，稽核輸入隔離與修復成效，不呼叫模型。"""
import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path.cwd()))
from cpea.application.models.decomposition import DecompositionDraft, DecompositionResponse
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT, DECOMPOSITION_PROMPT_VERSION
from cpea.workflows.task_decomposition.validation import validate_decomposition, prepare_requests
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition
from evaluations.decomposition_reports import summarize


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def read_lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def audit(run):
    profile = Path('projects/retail')
    catalog = SchemaCatalog(profile)
    casefile = profile / 'evaluations/task_decomposition_cases.jsonl'
    cases = load_decomposition_cases(casefile, catalog)
    by_id = {c['case_id']: c for c in cases}
    metadata = read_json(run / 'run.json')
    rows = read_lines(run / 'results.jsonl')
    calls = read_lines(run / 'calls.jsonl')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, encoding='utf-8').strip()
    diff = subprocess.check_output(['git', 'diff', 'HEAD', '--binary'])
    assert not diff and metadata['diff_sha256'] == sha256(diff).hexdigest()
    assert metadata['revision'] == revision and metadata.get('finished_at')
    assert metadata['runs'] == 3 and metadata['planned'] == 90 and len(cases) == 30
    assert metadata['model'] == 'gpt-6-sol' and metadata['provider'] == 'azure'
    assert metadata['sdk_retries'] == 0 and metadata['max_model_calls'] is None
    assert metadata['model_calls'] == len(rows) == len(calls) == 90
    assert metadata['contract_fingerprint'] == catalog.fingerprint
    assert metadata['casefile_sha256'] == sha256(casefile.read_bytes()).hexdigest()
    assert metadata['prompt_version'] == DECOMPOSITION_PROMPT_VERSION
    assert metadata['prompt_sha256'] == sha256(DECOMPOSITION_PROMPT.encode('utf-8')).hexdigest()
    schema = DecompositionDraft.model_json_schema()
    assert metadata['schema_sha256'] == sha256(json.dumps(schema, sort_keys=True).encode('utf-8')).hexdigest()
    assert Counter((r['case_id'], r['run']) for r in rows) == Counter((c['case_id'], n) for c in cases for n in range(3))
    events = {(c['case_id'], c['run']): c for c in calls}
    assert len(events) == 90
    expected_views = [{'view': v.name, **v.policy} for v in catalog.views()]
    tokens = Counter()
    for row in rows:
        assert row['status'] == 'completed'
        case = by_id[row['case_id']]
        event = events[(row['case_id'], row['run'])]
        assert 'error' not in event
        messages = event['messages']
        assert len(messages) == 2 and messages[0]['content'] == DECOMPOSITION_PROMPT
        assert messages[0]['role'] == 'system' and messages[1]['role'] == 'human'
        context = json.loads(messages[1]['content'])
        assert context == {'request': case['request'], 'views': expected_views, 'response_schema': schema}
        draft = parse_model(SimpleNamespace(content=event['response']), DecompositionDraft)
        response = DecompositionResponse.model_validate(row['response'])
        assert response.contract_fingerprint == catalog.fingerprint
        assert response.draft == draft
        errors = validate_decomposition(draft, catalog)
        payloads = [] if errors else prepare_requests(draft, catalog)
        assert response.validation_errors == errors
        assert response.status == ('error' if errors else draft.status)
        assert response.prepared_requests == payloads
        assert row['score'] == grade_decomposition(case, response, catalog)
        usage = event.get('usage') or {}
        tokens.update({k: usage.get(k, 0) for k in ('input_tokens', 'output_tokens')})

    summary = summarize(rows, planned=90, runs=3)
    assert read_json(run / 'summary.json') == summary
    assert all(metadata[key] == value for key, value in summary.items())
    development = {1, 5, 6, 7, 12, 13, 14, 15, 16, 17, 19, 20, 22, 23, 26, 28, 30}
    holdout = [r for r in rows if int(r['case_id'].rsplit('-', 1)[1]) not in development]
    assert len(holdout) == 39
    unseen = [r for r in rows if int(r['case_id'].rsplit('-', 1)[1]) in {24, 25, 27, 29}]
    assert len(unseen) == 12
    # 同一 grader、oracle、validator 下比較舊回覆，保留舊原始結果。
    baseline_dir = profile / 'artifacts/task_decomposition/20261020T050127310992Z-bf626def-7b4f2d-regrade-018243'
    baseline = read_lines(baseline_dir / 'results.jsonl')
    baseline_metadata = read_json(baseline_dir / 'run.json')
    assert baseline_metadata.get('finished_at') and baseline_metadata['planned'] == 90 and baseline_metadata['runs'] == 3
    assert len(baseline) == 90 and all(r['status'] == 'completed' for r in baseline)
    assert Counter((r['case_id'], r['run']) for r in baseline) == Counter((c['case_id'], n) for c in cases for n in range(3))
    source_run = Path(baseline_metadata['source_run'])
    assert baseline_metadata['source_results_sha256'] == sha256((source_run / 'results.jsonl').read_bytes()).hexdigest()
    source_metadata = read_json(source_run / 'run.json')
    assert source_metadata.get('finished_at') and source_metadata['model_calls'] == 90
    assert source_metadata['casefile_sha256'] == sha256((source_run / 'original-cases.jsonl').read_bytes()).hexdigest()
    original_cases = {c['case_id']: c for c in read_lines(source_run / 'original-cases.jsonl')}
    assert set(original_cases) == set(by_id)
    assert all(original_cases[key]['request'] == by_id[key]['request'] for key in by_id)
    original_events = {(c['case_id'], c['run']): c for c in read_lines(source_run / 'calls.jsonl')}
    assert len(original_events) == 90
    for row in baseline:
        original = original_events[(row['case_id'], row['run'])]
        raw_draft = parse_model(SimpleNamespace(content=original['response']), DecompositionDraft)
        assert raw_draft == DecompositionResponse.model_validate(row['response']).draft
    old_summary = summarize(baseline, planned=90, runs=3)
    for row in baseline:
        response = DecompositionResponse.model_validate(row['response'])
        if response.draft and response.draft.status == 'ready':
            errors = validate_decomposition(response.draft, catalog)
            payloads = [] if errors else prepare_requests(response.draft, catalog)
            response = response.model_copy(update=dict(status='error' if errors else 'ready',
                prepared_requests=payloads, validation_errors=errors))
            row['response'] = response.model_dump()
        row['score'] = grade_decomposition(by_id[row['case_id']], response, catalog)
    corrected_baseline = summarize(baseline, planned=90, runs=3)
    result = dict(run=str(run), revision=revision, summary=summary,
        holdout_summary=summarize(holdout, planned=39, runs=3),
        unseen_prompt_cases_summary=summarize(unseen, planned=12, runs=3),
        original_baseline=old_summary, corrected_baseline=corrected_baseline,
        usage=dict(tokens), run_json_sha256=sha256((run / 'run.json').read_bytes()).hexdigest(),
        results_sha256=sha256((run / 'results.jsonl').read_bytes()).hexdigest(),
        calls_sha256=sha256((run / 'calls.jsonl').read_bytes()).hexdigest(),
        baseline_results_sha256=sha256((baseline_dir / 'results.jsonl').read_bytes()).hexdigest(),
        casefile_sha256=metadata['casefile_sha256'], prompt_sha256=metadata['prompt_sha256'],
        schema_sha256=metadata['schema_sha256'],
        evidence_scope='完整原始輸入隔離、回覆解析、驗證、payload及評分重播；不生成SQL，不呼叫模型或DB。')
    destination = Path(__file__).parent / 'fix-benchmark-audit.json'
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if summary['automated_pass_count'] == 90 else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', type=Path, required=True)
    raise SystemExit(audit(parser.parse_args().run))
