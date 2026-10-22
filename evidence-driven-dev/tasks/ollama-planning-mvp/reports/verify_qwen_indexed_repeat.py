"""離線核對第二次 Qwen 請求、設定與外部逾時證據；不呼叫模型。"""
from hashlib import sha256
import json
from pathlib import Path

from evaluations.three_stage_view_selection_runner import SchemaCatalog, fingerprint

task = Path('evidence-driven-dev/tasks/ollama-planning-mvp')
result = json.loads((task / 'reports/qwen-indexed-recall-repeat-results.json').read_text(encoding='utf-8'))
folder = task / result['artifact_folder']
assert {p.name for p in folder.iterdir()} == set(result['artifact_hashes'])
for name, digest in result['artifact_hashes'].items():
    assert sha256((folder / name).read_bytes()).hexdigest() == digest
meta = json.loads((folder / 'run.json').read_text(encoding='utf-8'))
old = task / '.local/qwen-indexed-20261021T035651Z-ab0b06'
prior = json.loads((old / 'run.json').read_text(encoding='utf-8'))
for key in ('version', 'provider', 'model', 'frozen', 'request', 'reasoning', 'temperature',
            'top_p', 'seed', 'context_window', 'output_limit', 'schema_enforcement', 'harness_sha256', 'budget'):
    assert meta[key] == prior[key], key
assert (folder / 'recall-request.json').read_bytes() == (old / 'recall-request.json').read_bytes()
raw = (task / '.local/index-recall-request.txt').read_bytes()
catalog = SchemaCatalog('projects/retail')
case = dict(case_id='diagnostic-request-' + sha256(raw).hexdigest()[:12], request=raw.decode('utf-8'),
            source_case_id='cross-view-11', profile_id=catalog.profile_id, contract_fingerprint=catalog.fingerprint)
assert meta['frozen'] == fingerprint(catalog, case)
assert meta['harness_sha256'] == sha256((task / 'reports/run_qwen_indexed_probe.py').read_bytes()).hexdigest()
evidence = json.loads((task / result['evidence'][0]).read_text(encoding='utf-8'))
assert evidence['exit_code'] == 124 and evidence['source_unchanged']
assert evidence['output_sha256'] == sha256((task / evidence['raw_output']).read_bytes()).hexdigest()
assert json.loads((folder / 'budget.json').read_text(encoding='utf-8'))['calls'] == 1
assert not (folder / 'recall-call.json').exists()
assert not (folder / 'recall-provider-error.json').exists()
assert 'artifact_hashes' not in meta and meta['calls'] == 0
print(json.dumps(dict(result='PASS', scope='request/settings/fingerprint/artifacts/outer timeout',
                      provider_attempts=1, raw_replays=0, semantic_result='NOT_VERIFIED'), ensure_ascii=False))
