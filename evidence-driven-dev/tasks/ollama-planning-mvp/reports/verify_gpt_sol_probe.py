"""離線重播四筆 GPT 診斷，封存 API 加密 reasoning，不解密或補寫摘要。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT))
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.parsing import parse_model
from cpea.workflows.task_decomposition.validation import validate_decomposition, prepare_requests
from evaluations.decomposition_cases import load_decomposition_cases
from evaluations.decomposition_grading import grade_decomposition
from evaluations.planning_mvp import SemanticPlan,compile_plan,finish,semantic_check
from evaluations.planning_mvp_runner import TASK,messages,freeze
from evaluations.planning_reasoning_probe import capture_response,failure_ids


folder = TASK/'.local/gpt-sol-b1-failures-20261020T131351Z-7d555a'
read = lambda p:json.loads(p.read_text(encoding='utf-8'))
meta = read(folder/'run.json')
assert meta['attempts']==meta['completed']==4 and meta['stopped'] is None
assert meta['model']=='gpt-6-sol' and meta['sdk_retries']==0
for name,h in meta['artifact_hashes'].items():assert sha256((folder/name).read_bytes()).hexdigest()==h
catalog = SchemaCatalog(Path('projects/retail'))
all_cases = load_decomposition_cases(Path('projects/retail/evaluations/task_decomposition_cases.jsonl'),catalog)
cases = [next(c for c in all_cases if c['case_id']==name) for name in meta['cases']]
assert freeze(catalog,cases)==meta['frozen']
assert sha256(Path('evaluations/planning_reasoning_probe.py').read_bytes()).hexdigest()==meta['probe_source_sha256']
assert failure_ids(read(TASK/'agents/oracle-audit/mvp1-semantic-review.json'))==meta['cases']
archive,results = [],[]
totals = {'input_tokens':0,'output_tokens':0,'total_tokens':0,'reasoning_tokens':0}
for case in cases:
    cid = case['case_id'];raw = read(folder/(cid+'-raw.json'));row = read(folder/(cid+'-result.json'))
    assert raw['model']=='gpt-6-sol'
    captured = capture_response(raw)
    for key,value in captured.items():assert row[key]==value
    req = read(folder/(cid+'-request.json'))
    assert req['input']==[{'role':'system' if m.type=='system' else 'user','content':m.content} for m in messages(case,catalog)]
    assert req['reasoning']=={'effort':'medium','summary':'auto'}
    plan = parse_model(SimpleNamespace(content=captured['output_text']),SemanticPlan)
    draft = compile_plan(plan,catalog);response = finish(draft,catalog,guard=True)
    assert plan.model_dump()==row['semantic_plan'] and response.model_dump()==row['response']
    assert grade_decomposition(case,response,catalog)==row['original_score']
    assert semantic_check(case,response,catalog)==row['diagnostic']
    items = [deepcopy(i) for i in raw['output'] if i['type']=='reasoning']
    path = folder/(cid+'-reasoning-items.json')
    path.write_text(json.dumps(items,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');path.chmod(0o600)
    archive.append({'case_id':cid,'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
                    'items':len(items),'encrypted_items':sum(bool(i.get('encrypted_content')) for i in items),
                    'readable_summary_count':len(captured['reasoning_summary']),
                    'reasoning_tokens':captured['reasoning_tokens'],'decryption_attempted':False})
    for key in ('input_tokens','output_tokens','total_tokens'):totals[key]+=row['usage'].get(key,0)
    totals['reasoning_tokens']+=row.get('reasoning_tokens') or 0
    results.append({'case_id':cid,'runtime_status':response.status,
                    'automated_pass':row['original_score']['automated_pass'],
                    'diagnostic_safe':row['diagnostic']['safe'],'validation_errors':response.validation_errors,
                    'reasoning_summary_status':captured['reasoning_summary_status'],
                    'reasoning_tokens':captured['reasoning_tokens']})

# A separate, non-scoring diagnostic: the frozen runtime rejects an already
# documented store-name FD. Do not overwrite the original error or payloads.
r14=read(folder/'cross-view-14-result.json')
d14=compile_plan(SemanticPlan.model_validate(r14['semantic_plan']),catalog)
assert r14['response']['validation_errors']==['inventory_by_store: attributes lack uniqueness proof']
assert validate_decomposition(d14,catalog)==[]
offline_payloads=prepare_requests(d14,catalog)
assert len(offline_payloads)==2
inventory=d14.tasks[0]
assert inventory.output_grain==['store_id'] and inventory.filters==[]
assert len(inventory.conditional_metrics)==1
metric=inventory.conditional_metrics[0]
assert metric.column=='product_id' and metric.aggregation=='count'
assert [f.model_dump() for f in metric.conditions]==[{'column':'stock_qty','operator':'=','value':0}]
assert inventory.metadata_collections==['snapshot_date']
# Contract-admissible store/product rows: COUNT and DISTINCT coincide and zero
# qualifying products preserve a store because the predicate is conditional.
rows=[(1,11,0),(1,12,4),(2,21,3)]
actual={s:sum(q==0 for ss,p,q in rows if ss==s) for s,_,_ in rows}
expected={s:len({p for ss,p,q in rows if ss==s and q==0}) for s,_,_ in rows}
assert actual==expected=={1:1,2:0}

summary={'artifact_result':'PASS','model':'gpt-6-sol','cases':meta['cases'],'calls':4,
    'elapsed_seconds':meta['elapsed_seconds'],'runtime_ready':sum(r['runtime_status']=='ready' for r in results),
    'original_automated_pass':sum(r['automated_pass'] for r in results),
    'reasoning_readable_summaries':sum(r['readable_summary_count'] for r in archive),
    'cases_with_encrypted_reasoning':sum(r['encrypted_items']>0 for r in archive),
    'usage':totals,'results':results,'reasoning_archive':archive,
    'manual_semantic_review':{'reviewer':'main-agent','independence':'既有獨立oracle與FD審核依據；本輪逐題審查由主agent執行，未另派reviewer',
        'semantic_plan_correct':4,'end_to_end_safe_ready':3,
        'case14':'骨架語意正確；凍結typed guard未編碼已核准store_id→store_name FD而拒絕。COUNT product_id與COUNT DISTINCT在真store/product唯一列等價。原error不改、仍不算端到端通過。',
        'case14_offline_existing_validator':'PASS，只有既有validator的離線診斷可生成2個payload；不計入原結果。',
        'fd_evidence':'projects/retail/contract_review.md:15-16；agents/oracle-audit/baseline-semantic-review.md 第15題'},
    'new_model_calls_during_verification':0,'sql_db_calls':0,'ollama_calls':0,
    'limitation':'四題已見失敗集，Responses／reasoning設定與先前DeepSeek Chat不同；不是DeepSeek Gate，不解密或偽造推理摘要。'}
(TASK/'reports/gpt-sol-failure-probe.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('results','reasoning_archive')},ensure_ascii=False))
