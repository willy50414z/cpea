"""離線重播 GPT 與 DeepSeek 首輪結果，不建立模型連線。"""
import json
from hashlib import sha256
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.local'))
from compare_stages import generate, rows
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition

catalog = SchemaCatalog(Path('projects/retail'))
casefile = Path('projects/retail/evaluations/task_decomposition_cases.jsonl')
cases = {c['case_id']: c for c in load_decomposition_cases(casefile, catalog)}
base = Path('projects/retail/artifacts/task_decomposition')
folders = {
    'gpt-6-sol': base / '20261020T054500378064Z-bc09c67f-26fc31',
    'DeepSeek-V4.1-Flash': base / '20261020T055210984742Z-bc09c67f-432a10',
}
output = {'scope': '原始完整首輪各30筆；僅可觀察最終決策，不是GPT內部推理。', 'models': {}}
for model, folder in folders.items():
    results = [r for r in rows(folder / 'results.jsonl') if r['run'] == 0]
    calls = {c['case_id']: c for c in rows(folder / 'calls.jsonl') if c['run'] == 0}
    assert len(results) == len(calls) == len(cases) == 30
    assert set(calls) == set(cases)
    for row in results:
        event = calls[row['case_id']]
        def invoke(stage, messages):
            assert stage == 'single'
            assert event['messages'] == [{'role': m.type, 'content': m.content} for m in messages]
            return event['response']
        response, stop = generate('A_original', cases[row['case_id']]['request'], catalog, invoke)
        assert stop == 'complete'
        recorded = row['response']
        for key in ('status', 'code', 'draft', 'validation_errors', 'prepared_requests', 'contract_fingerprint'):
            assert response.model_dump()[key] == recorded[key], (model, row['case_id'], key)
        assert grade_decomposition(cases[row['case_id']], response, catalog) == row['score']
    output['models'][model] = {
        'run': str(folder), 'replayed': len(results),
        'automated_pass': sum(r['score']['automated_pass'] for r in results),
        'ready': sum(r['response']['status'] == 'ready' for r in results),
        'views_and_columns': sum(r['score']['views_and_columns_match'] for r in results),
        'event_keys': sorted(next(iter(calls.values()))),
        'reasoning_trace_available': any(any('reasoning' in k for k in e) for e in calls.values()),
        'hashes': {name: sha256((folder / name).read_bytes()).hexdigest() for name in ('calls.jsonl', 'results.jsonl')},
    }
    assert not output['models'][model]['reasoning_trace_available']
destination = ROOT / 'reports' / 'baseline-analysis.json'
destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(output, ensure_ascii=False, indent=2))
