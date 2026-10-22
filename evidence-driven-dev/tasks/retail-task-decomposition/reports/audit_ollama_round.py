"""重播本地單輪與既存雲端對照；不呼叫模型或 SQL。"""
import argparse
from collections import Counter
from contextlib import redirect_stdout
from hashlib import sha256
import importlib.util
import io
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


def rows(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def audit(local):
    directory = Path(__file__).parent
    spec = importlib.util.spec_from_file_location('previous_comparison', directory / 'audit_model_comparison.py')
    previous = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(previous)
    old = read(directory / 'model-comparison-audit.json')
    with redirect_stdout(io.StringIO()):
        assert previous.audit(Path(old['rounds']['gpt-6-sol']['run']), Path(old['rounds']['DeepSeek-V4.1-Flash']['run'])) == 0
    old = read(directory / 'model-comparison-audit.json')
    catalog = SchemaCatalog(Path('projects/retail'))
    casefile = Path('projects/retail/evaluations/task_decomposition_cases.jsonl')
    cases = {c['case_id']: c for c in load_decomposition_cases(casefile, catalog)}
    metadata = read(local / 'run.json')
    results = rows(local / 'results.jsonl')
    calls = rows(local / 'calls.jsonl')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True, encoding='utf-8').strip()
    diff = subprocess.check_output(['git', 'diff', 'HEAD', '--binary'])
    assert not diff and metadata['revision'] == revision == old['revision']
    assert metadata['diff_sha256'] == sha256(diff).hexdigest()
    assert metadata['provider'] == 'ollama' and metadata['model'] == 'qwen3.8:27b'
    assert metadata['runs'] == 1 and metadata['planned'] == 30 and metadata.get('finished_at')
    assert metadata['harness_unchanged']
    harness = directory.parent / '.local/run_ollama_decomposition.py'
    assert metadata['harness_sha256'] == sha256(harness.read_bytes()).hexdigest()
    assert metadata['casefile_sha256'] == sha256(casefile.read_bytes()).hexdigest() == old['casefile_sha256']
    assert metadata['contract_fingerprint'] == catalog.fingerprint
    schema = DecompositionDraft.model_json_schema()
    assert metadata['schema_sha256'] == sha256(json.dumps(schema, sort_keys=True).encode('utf-8')).hexdigest()
    assert metadata['prompt_sha256'] == sha256(DECOMPOSITION_PROMPT.encode('utf-8')).hexdigest()
    assert metadata['prompt_version'] == DECOMPOSITION_PROMPT_VERSION
    assert metadata['sdk_retries'] == 0 and metadata['model_calls'] == len(calls)
    assert len(results) == 30 and Counter(r['case_id'] for r in results) == Counter(cases.keys())
    events = {(c['case_id'], c['run']): c for c in calls}
    assert len(events) == len(calls)
    cloud_events = {c['case_id']: c for c in rows(Path(old['rounds']['DeepSeek-V4.1-Flash']['run']) / 'calls.jsonl')}
    tokens = Counter()
    for row in results:
        assert row['run'] == 0
        if row['status'] == 'skipped':
            assert row.get('reason')
            continue
        event = events[(row['case_id'], 0)]
        assert event['messages'] == cloud_events[row['case_id']]['messages']
        response = DecompositionResponse.model_validate(row['response'])
        assert response.contract_fingerprint == catalog.fingerprint
        if row['status'] == 'failed':
            assert 'error' in event and response.status == 'error' and not response.prepared_requests
            continue
        assert row['status'] == 'completed' and 'error' not in event
        assert (event.get('response_metadata') or {}).get('model', metadata['model']) == metadata['model']
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
        assert row['score'] == grade_decomposition(cases[row['case_id']], response, catalog)
        tokens.update({k: (event.get('usage') or {}).get(k, 0) for k in ('input_tokens', 'output_tokens')})
    summary = summarize(results, planned=30, runs=1)
    assert read(local / 'summary.json') == summary
    assert all(metadata[key] == value for key, value in summary.items())
    result = dict(revision=revision, local_run=str(local), local_summary=summary,
        cloud_summaries={k: v['summary'] for k, v in old['rounds'].items()},
        usage=dict(tokens), failures=[dict(case_id=r['case_id'], status=r['status'],
            response_code=r.get('response', {}).get('code'), score=r.get('score'),
            validation_errors=r.get('response', {}).get('validation_errors'))
            for r in results if not r.get('score', {}).get('automated_pass')],
        local_settings={k: metadata[k] for k in ('model', 'model_digest', 'reasoning', 'temperature', 'top_p', 'seed', 'context_window', 'timeout_seconds', 'response_format')},
        calls_sha256=sha256((local / 'calls.jsonl').read_bytes()).hexdigest(),
        results_sha256=sha256((local / 'results.jsonl').read_bytes()).hexdigest(),
        field_score_with_missing_used_columns=[r['case_id'] for r in results
            if r.get('score', {}).get('views_and_columns_match') and any(
                'used column absent from required_columns' in e for e in r.get('response', {}).get('validation_errors', []))],
        caveats=['本地temperature0/reasoningTrue/native schema；Azure temperature1/JSON object，不能視為所有生成設定相同。',
                 '本地共用服務排程、timeout900秒；不是隔離延遲實驗。',
                 '自動分數既有等價表示漏判與額外聚合等語意盲點；日期alias寬鬆規則也可能放過真正漏列的filter欄位，相關案例另列，不回寫原分。request就緒不是全面語意安全。',
                 '只驗規劃與request準備，未生成或執行SQL；本輪同agent用獨立既有oracle及fresh subprocess重播驗收。'])
    (directory / 'ollama-audit.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local', type=Path, required=True)
    raise SystemExit(audit(parser.parse_args().local))
