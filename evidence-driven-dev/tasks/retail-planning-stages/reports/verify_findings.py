"""Fresh evidence checks for the investigation claims, with no model calls."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
reports = ROOT / 'reports'
read = lambda p: json.loads(p.read_text(encoding='utf-8'))
lines = lambda p: [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
audit = read(reports/'stages-audit.json')
analysis = read(reports/'stages-analysis.json')
folder = Path(audit['run'])
meta = read(folder/'run.json')
results, calls = lines(folder/'results.jsonl'), lines(folder/'calls.jsonl')
assert len(results) == 30 and len(calls) == 57
assert not any('error_type' in c for c in calls)
assert audit['replayed_case_arms'] == 30 and audit['replayed_calls'] == 57
for name, digest in audit['hashes'].items():
    assert digest == sha256((folder/name).read_bytes()).hexdigest()
assert meta['harness_sha256'] == sha256((ROOT/'.local/compare_stages.py').read_bytes()).hexdigest()
assert audit['summary'] == analysis['summary'] == meta['summary']
expected = {'A_original':(10,7,7,3,74663,8744),
            'B_checklist':(10,5,2,2,78103,7466),
            'C_staged':(37,5,2,1,161045,10839)}
for arm, values in expected.items():
    rr, cc = [r for r in results if r['arm']==arm], [c for c in calls if c['arm']==arm]
    assert len(rr) == 10
    actual = (len(cc), sum(r['response']['status']=='ready' for r in rr),
        sum(r['score']['automated_pass'] for r in rr),
        sum(r['score']['automated_pass'] for r in rr if r['case_id'] in ('cross-view-02','cross-view-07','cross-view-18')),
        sum(c['usage']['input_tokens'] for c in cc), sum(c['usage']['output_tokens'] for c in cc))
    assert actual == values, (arm, actual)
old = Path('projects/retail/artifacts/task_decomposition/20261020T055210984742Z-bc09c67f-432a10')
old_calls = {c['case_id']:c for c in lines(old/'calls.jsonl')}
old_meta = read(old/'run.json')
for c in calls:
    if c['arm'] == 'A_original':
        assert c['messages'] == old_calls[c['case_id']]['messages']
for key in ('temperature','top_p','seed','context_window','max_output_tokens'):
    assert meta['settings'][key] == old_meta[key]
assert meta['settings']['request_timeout_seconds'] == old_meta['timeout_seconds']
selected = {r['case_id'] for r in results}
assert sum(r['score']['automated_pass'] for r in lines(old/'results.jsonl') if r['case_id'] in selected) == 3
routes = analysis['phase_diagnostics']['routes']
assert len(routes)==10 and sum(r['canonical_views_match'] for r in routes)==9
assert len(analysis['phase_diagnostics']['task_contract_failure_cases'])==2
witnesses = read(reports/'representation-witnesses.json')
assert witnesses['result']=='PASS' and all(f'case{n}' in witnesses for n in (14,18,29))
assert not subprocess.check_output(['git','diff','HEAD','--binary'])
assert subprocess.check_output(['git','rev-parse','HEAD'],text=True,encoding='utf-8').strip()==meta['revision']
for path in reports.glob('*'):
    if path.suffix in ('.md','.py','.json'):
        assert not path.read_bytes().startswith(b'\xef\xbb\xbf')
        path.read_text(encoding='utf-8')
for cid in ('cross-view-07','cross-view-11'):
    r=next(r for r in results if r['case_id']==cid and r['arm']=='C_staged')
    for t in r['response']['draft']['tasks']:
        if t['view'].endswith('v_inventory_status'):
            assert set(t['attributes']) & set(t['metadata_collections'])
print(json.dumps({'result':'PASS','case_arms':30,'calls':57,
    'original_prompt_messages_and_generation_settings_identical':True,
    'original_selected_pass':3,'fresh_original_pass':7,
    'research_conclusion':'本次三階段未達預設改善標準，不推論所有拆分都無效。',
    'report_sha256':sha256((reports/'results.md').read_bytes()).hexdigest()},ensure_ascii=False))
