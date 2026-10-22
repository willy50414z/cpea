"""唯讀重播已完成12筆；不建立provider、不重跑模型。"""
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from cpea.application.models.decomposition import DecompositionDraft
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.decomposition_cases import case_sha256
from evaluations.decomposition_grading import grade_decomposition
from evaluations.planning_mvp import SemanticPlan, compile_plan, finish, semantic_check
from evaluations.planning_mvp_runner import messages, freeze, SELECTED


task = Path(__file__).resolve().parents[1]
folder = task/'.local/mvp1-b1-20261020T125608Z-a7f325'
read = lambda p:json.loads(p.read_text(encoding='utf-8'))
rows = lambda p:[json.loads(s) for s in p.read_text(encoding='utf-8').splitlines()]
meta = read(folder/'run.json')
events = {(r['case_id'],r['arm']):r for r in rows(folder/'calls.jsonl')}
results = rows(folder/'results.jsonl')
catalog = SchemaCatalog(ROOT/'projects/retail')
cases = rows(ROOT/'projects/retail/evaluations/task_decomposition_cases.jsonl')
selected = [next(c for c in cases if c['case_id']==cid) for cid in SELECTED]
assert len(events) == len(results) == meta['model_calls'] == meta['completed'] == 12
assert meta['finished_at'] and meta['stopped'] is None
assert meta['fingerprints'] == freeze(catalog,selected)
review = read(task/'agents/oracle-audit/review-manifest.json')
approved = {c['case_id']:c for c in review['cases']}
for c in selected:
    assert case_sha256(c) == c['case_sha256'] == approved[c['case_id']]['case_sha256']
for r in results:
    c = next(c for c in selected if c['case_id']==r['case_id'])
    event = events[r['case_id'],r['arm']]
    assert 'error' not in event
    if r['arm']=='B1':
        assert event['messages'] == [{'role':m.type,'content':m.content} for m in messages(c,catalog)]
        plan = parse_model(SimpleNamespace(content=event['response']),SemanticPlan)
        assert plan.model_dump() == r['semantic_plan']
        replay = finish(compile_plan(plan,catalog),catalog,guard=True)
    else:
        replay = finish(parse_model(SimpleNamespace(content=event['response']),DecompositionDraft),catalog)
    for key in ('status','code','draft','validation_errors','prepared_requests','contract_fingerprint'):
        assert replay.model_dump()[key] == r['response'][key], (r['case_id'],r['arm'],key)
    assert grade_decomposition(c,replay,catalog) == r['original_score']
    assert semantic_check(c,replay,catalog) == r['diagnostic']
for name in ('calls','results'):
    assert sha256((folder/(name+'.jsonl')).read_bytes()).hexdigest() == meta[name+'_sha256']
report = {'result':'PASS','replayed':12,'current_sources_match_frozen':True,'actual_case_hashes_match_independent_approval':True,
          'raw_response_payload_score_diagnostic_exact':True,'calls_unchanged':True,
          'new_model_calls':0,'sql_db_calls':0,'ollama_calls':0,
          'meaning':'實驗完整性通過；B1品質僅2/6 ready，MVP1 Gate失敗。'}
(task/'reports/mvp1-artifact-verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False))
