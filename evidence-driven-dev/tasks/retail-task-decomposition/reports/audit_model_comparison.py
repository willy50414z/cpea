"""稽核 GPT 第一輪與 DeepSeek 第二輪；不呼叫模型或 SQL。"""
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


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def audit(gpt, deepseek):
    catalog = SchemaCatalog(Path('projects/retail'))
    casefile = Path('projects/retail/evaluations/task_decomposition_cases.jsonl')
    cases = load_decomposition_cases(casefile, catalog)
    by_id = {c['case_id']: c for c in cases}
    assert len(cases) == 30
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, encoding='utf-8').strip()
    diff = subprocess.check_output(['git', 'diff', 'HEAD', '--binary'])
    assert not diff
    schema = DecompositionDraft.model_json_schema()
    views = [{'view': v.name, **v.policy} for v in catalog.views()]
    messages_by_model = {}
    output = {'revision': revision, 'rounds': {}, 'casefile_sha256': sha256(casefile.read_bytes()).hexdigest(),
              'scope': '兩個模型的完整30題各一輪；原始輸入、回覆、驗證、prepared requests、評分重播，不生成SQL或查DB。'}
    settings = []
    for model, folder in [('gpt-6-sol', gpt), ('DeepSeek-V4.1-Flash', deepseek)]:
        meta = read(folder / 'run.json')
        rows = lines(folder / 'results.jsonl')
        calls = lines(folder / 'calls.jsonl')
        assert meta['model'] == model and meta['provider'] == 'azure'
        assert meta['revision'] == revision and meta['diff_sha256'] == sha256(diff).hexdigest()
        assert meta['contract_fingerprint'] == catalog.fingerprint
        assert meta['casefile_sha256'] == output['casefile_sha256']
        assert meta['prompt_version'] == DECOMPOSITION_PROMPT_VERSION
        assert meta['prompt_sha256'] == sha256(DECOMPOSITION_PROMPT.encode('utf-8')).hexdigest()
        assert meta['schema_sha256'] == sha256(json.dumps(schema, sort_keys=True).encode('utf-8')).hexdigest()
        assert meta['max_model_calls'] is None and meta['sdk_retries'] == 0
        settings.append({k: meta[k] for k in ('context_window', 'max_output_tokens', 'temperature', 'top_p', 'seed', 'timeout_seconds', 'context_safety_tokens')})
        if model == 'gpt-6-sol':
            assert not meta.get('finished_at') and read(folder / 'interruption.json')['not_a_completed_benchmark']
            assert meta['planned'] == 90 and meta['runs'] == 3
            assert len(rows) == meta['completed'] == 47
            assert len(calls) == meta['model_calls'] == 47
        else:
            assert meta.get('finished_at') and meta['planned'] == 30 and meta['runs'] == 1
            assert len(rows) == len(calls) == meta['model_calls'] == 30
        assert all(r['status'] == 'completed' for r in rows)
        events = {(c['case_id'], c['run']): c for c in calls}
        assert len(events) == len(calls)
        assert set(events) == {(r['case_id'], r['run']) for r in rows}
        first = [r for r in rows if r['run'] == 0]
        assert Counter(r['case_id'] for r in first) == Counter(by_id.keys())
        usage = Counter()
        elapsed = []
        messages_by_model[model] = {}
        for row in rows:
            event = events[(row['case_id'], row['run'])]
            assert 'error' not in event
            messages = event['messages']
            assert len(messages) == 2 and messages[0] == {'role': 'system', 'content': DECOMPOSITION_PROMPT}
            assert messages[1]['role'] == 'human'
            assert json.loads(messages[1]['content']) == {'request': by_id[row['case_id']]['request'], 'views': views, 'response_schema': schema}
            response = DecompositionResponse.model_validate(row['response'])
            assert response.contract_fingerprint == catalog.fingerprint
            payloads = []
            errors = []
            code = None
            try:
                draft = parse_model(SimpleNamespace(content=event['response']), DecompositionDraft)
            except (ValueError, TypeError):
                draft = None
                status, code = 'error', 'invalid_model_response'
            else:
                status = draft.status
                if status == 'ready':
                    errors = validate_decomposition(draft, catalog)
                    if errors:
                        status, code = 'error', 'invalid_plan'
                    else:
                        try:
                            payloads = prepare_requests(draft, catalog)
                        except ValueError:
                            status, code = 'error', 'invalid_prepared_request'
            assert response.draft == draft
            assert (response.status, response.code, response.validation_errors, response.prepared_requests) == (status, code, errors, payloads)
            assert row['score'] == grade_decomposition(by_id[row['case_id']], response, catalog)
            if row['run'] == 0:
                messages_by_model[model][row['case_id']] = messages
                usage.update({k: (event.get('usage') or {}).get(k, 0) for k in ('input_tokens', 'output_tokens')})
                elapsed.append(event['elapsed_ms'])
        fresh = summarize(rows, planned=meta['planned'], runs=meta['runs'])
        assert all(meta[k] == v for k, v in fresh.items())
        if model != 'gpt-6-sol':
            assert read(folder / 'summary.json') == fresh
        holdout = {2, 3, 4, 8, 9, 10, 11, 18, 21, 24, 25, 27, 29}
        unseen = {24, 25, 27, 29}
        output['rounds'][model] = dict(run=str(folder), logical_round=1 if model == 'gpt-6-sol' else 2,
            summary=summarize(first, planned=30, runs=1),
            holdout_summary=summarize([r for r in first if int(r['case_id'].rsplit('-', 1)[1]) in holdout], planned=13, runs=1),
            unseen_summary=summarize([r for r in first if int(r['case_id'].rsplit('-', 1)[1]) in unseen], planned=4, runs=1),
            failures=[{'case_id': r['case_id'], 'response_code': r['response'].get('code'), 'score': r['score']} for r in first if not r['score']['automated_pass']],
            usage=dict(usage), mean_elapsed_ms=sum(elapsed) / len(elapsed),
            run_json_sha256=sha256((folder / 'run.json').read_bytes()).hexdigest(),
            results_sha256=sha256((folder / 'results.jsonl').read_bytes()).hexdigest(),
            calls_sha256=sha256((folder / 'calls.jsonl').read_bytes()).hexdigest())
        if model == 'gpt-6-sol':
            partial = [r for r in rows if r['run'] == 1]
            assert len(partial) == 17 and not any(r['run'] > 1 for r in rows)
            output['gpt_partial_second_round'] = dict(summary=summarize(partial, planned=30, runs=1),
                not_completed=30 - len(partial), in_flight=read(folder / 'interruption.json'),
                note='使用者要求停止，這17筆不是完整輪次，不計入模型對照30題分母。')
    assert settings[0] == settings[1]
    assert messages_by_model['gpt-6-sol'] == messages_by_model['DeepSeek-V4.1-Flash']
    destination = Path(__file__).parent / 'model-comparison-audit.json'
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gpt', type=Path, required=True)
    parser.add_argument('--deepseek', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(audit(args.gpt, args.deepseek))
