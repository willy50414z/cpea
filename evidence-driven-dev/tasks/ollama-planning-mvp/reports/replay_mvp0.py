"""零模型、零密鑰讀取的原始重播與診斷；只新增 sidecar。"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests/unit'))
from test_planning_mvp import canonical, case
from cpea.application.models.decomposition import DecompositionDraft, PlanningFilter
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.workflows.task_decomposition.prompt import DECOMPOSITION_PROMPT
from evaluations.decomposition_grading import grade_decomposition
from evaluations.planning_mvp import close_columns, finish, semantic_check, used_columns, SemanticPlan, compile_plan


DEST = Path(__file__).resolve().parent
catalog = SchemaCatalog(ROOT / 'projects/retail')
base = ROOT / 'projects/retail/artifacts/task_decomposition'
folder = base / '20261020T055210984742Z-bc09c67f-432a10'
rows = lambda p: [json.loads(s) for s in p.read_text(encoding='utf-8').splitlines() if s.strip()]
records = [r for r in rows(folder / 'results.jsonl') if r['run'] == 0]
events = {r['case_id']:r for r in rows(folder / 'calls.jsonl') if r['run'] == 0}
assert len(records) == len(events) == 30
before_hash = {name:sha256((folder / name).read_bytes()).hexdigest() for name in ('calls.jsonl','results.jsonl')}
sidecar = []
for r in records:
    cid = r['case_id']; c = case(int(cid[-2:])); event = events[cid]
    assert event['messages'][0]['content'] == DECOMPOSITION_PROMPT
    context = json.loads(event['messages'][1]['content'])
    assert context == {'request':c['request'], 'views':[{'view':v.name, **v.policy} for v in catalog.views()],
                       'response_schema':DecompositionDraft.model_json_schema()}
    raw = event['response']
    if isinstance(raw, str):
        raw = json.loads(raw.strip().removeprefix('```json').removesuffix('```'))
    d = DecompositionDraft.model_validate(raw)
    original = finish(d, catalog)
    for key in ('status','code','draft','validation_errors','prepared_requests','contract_fingerprint'):
        assert original.model_dump()[key] == r['response'][key], (cid, key)
    assert grade_decomposition(c, original, catalog) == r['score'], cid
    additions, closure_error = [], None
    try:
        closed, additions = close_columns(d, catalog)
    except ValueError as exc:
        closed, closure_error = d, str(exc)
    after = finish(closed, catalog)
    guarded = finish(closed, catalog, guard=True)
    typed_coverage = all(used_columns(t) <= set(t.required_columns) for t in closed.tasks)
    sidecar.append({'case_id':cid, 'original_score':r['score'], 'original':original.model_dump(),
        'closure':after.model_dump(), 'guarded':guarded.model_dump(), 'additions':additions,
        'closure_error':closure_error, 'typed_coverage':typed_coverage,
        'new_ready':original.status != 'ready' and after.status == 'ready',
        'semantic_diagnostic':semantic_check(c, guarded, catalog)})

# Independent-oracle injected references are compiler tests, never model results.
controls, injected = [], []
for number in (2,7,9,14,16,28):
    d = canonical(number)
    assert finish(d, catalog, guard=True).status == 'ready', (number, finish(d, catalog, guard=True).validation_errors)
    assert semantic_check(case(number), finish(d, catalog), catalog)['safe'], number
    p = SemanticPlan.model_validate({'status':'ready', 'anchor_task':d.integration.anchor_task,
        'root_grain':d.integration.output_grain,
        'tasks':[{**{k:v for k,v in t.model_dump().items() if k in ('task_id','view','filters','metrics','conditional_metrics','attributes','metadata_collections')},
                   'query_grain':t.output_grain} for t in d.tasks],
        'links':[{'parent':e.left_task,'child':e.right_task,'parent_keys':e.left_keys,'child_keys':e.right_keys,
                  'mode':e.mode,'cardinality':e.cardinality,
                  'shape':'collection' if any(x.task_id == e.right_task and x.kind == 'nest' for x in d.integration.preparation)
                    else 'context' if e.cardinality == 'many_to_one' else 'merge'} for e in d.integration.edges]})
    compiled = compile_plan(p, catalog)
    checked = semantic_check(case(number), finish(compiled, catalog, guard=True), catalog)
    assert checked['safe'], (number, checked)
    controls.append({'case_id':case(number)['case_id'], 'safe':True})
    injected.append({'case_id':case(number)['case_id'], 'plan':p.model_dump(), 'response':finish(compiled,catalog,guard=True).model_dump()})

mutations = []
def mutation(label, number, change):
    d = canonical(number); change(d)
    try:
        d, _ = close_columns(d, catalog)
        runtime = finish(d, catalog, guard=True)
    except ValueError as exc:
        runtime = finish(d, catalog)
        runtime = runtime.model_copy(update={'status':'error','code':'closure_rejected', 'prepared_requests':[], 'validation_errors':[str(exc)]})
    semantic = semantic_check(case(number), runtime, catalog)
    assert not semantic['safe'], label
    mutations.append({'label':label, 'case_id':case(number)['case_id'], 'runtime_rejected':runtime.status != 'ready',
                      'oracle_rejected':not semantic['safe'], 'errors':semantic['errors'],
                      'boundary':'型別護欄可拒絕' if runtime.status != 'ready' else '僅oracle可判定需求不符；runtime證據不足'})

mutation('未表達期間', 7, lambda d:setattr(d.tasks[1], 'filters', [f for f in d.tasks[1].filters if f.column == 'sales_channel']))
mutation('非法來源欄位', 7, lambda d:d.tasks[1].metrics.update(order_count='count'))
mutation('漏通路', 7, lambda d:setattr(d.tasks[1], 'filters', [f for f in d.tasks[1].filters if f.column != 'sales_channel']))
mutation('inner刪母體', 7, lambda d:setattr(d.integration.edges[0], 'mode', 'inner'))
mutation('缺nest', 20, lambda d:setattr(d.integration, 'preparation', []))
mutation('錯final grain', 20, lambda d:d.integration.output_grain.append('product_id'))
mutation('任意FD', 14, lambda d:d.tasks[0].attributes.append('product_name'))
mutation('非加性百分比', 7, lambda d:d.tasks[1].metrics.update(gross_margin_pct='sum'))
def conditional_to_filter(d):
    d.tasks[0].filters.extend(d.tasks[0].conditional_metrics[0].conditions)
    d.tasks[0].conditional_metrics = []
mutation('條件count誤變filter', 14, conditional_to_filter)
mutation('跨快照sum', 5, lambda d:d.tasks[0].metrics.update(stock_qty='sum'))
mutation('缺月份值', 4, lambda d:d.tasks[1].filters.__setitem__(0, PlanningFilter(column='sales_month',operator='=',value='2026-09-01')))
mutation('缺值填零', 7, lambda d:setattr(d.integration, 'missing_data_policy', '未匹配者一律補零'))

# A typed-only omission must be recovered; semantic omissions must never be invented.
safe = canonical(7); safe.tasks[1].required_columns.remove('sales_channel')
closed, additions = close_columns(safe,catalog)
assert semantic_check(case(7),finish(closed,catalog,guard=True),catalog)['safe'] and len(additions) == 1

def distribution(events):
    out = {}
    for key in ('input_tokens','output_tokens','total_tokens'):
        values = sorted(e.get('usage',{}).get(key) for e in events if e.get('usage',{}).get(key) is not None)
        out[key] = {'n':len(values), 'median':statistics.median(values) if values else None,
                    'p95':values[min(len(values)-1, int((len(values)-1)*.95)+1)] if values else None,
                    'max':max(values) if values else None}
    return out

usage = {'deepseek':distribution(list(events.values()))}
qwen_folder = base / '20261020T061324037572Z-bc09c67f-4a2192'
if not qwen_folder.exists():
    candidates = []
    for p in base.glob('*/run.json'):
        meta = json.loads(p.read_text(encoding='utf-8'))
        if 'qwen' in meta.get('model','').lower() and (p.parent/'calls.jsonl').exists():
            candidates.append(p.parent)
    if candidates:qwen_folder = sorted(candidates)[-1]
if qwen_folder.exists():
    usage['qwen'] = {'path':str(qwen_folder.relative_to(ROOT)), 'tokens':distribution(rows(qwen_folder/'calls.jsonl')),
                     'thinking_token_accounting':'既有usage未分開thinking，口徑未知'}
assert before_hash == {name:sha256((folder / name).read_bytes()).hexdigest() for name in before_hash}
summary = {'original_replay':len(sidecar), 'original_automated_pass':sum(r['original_score']['automated_pass'] for r in sidecar),
    'original_ready':sum(r['original']['status']=='ready' for r in sidecar),
    'closure_ready':sum(r['closure']['status']=='ready' for r in sidecar),
    'guarded_ready':sum(r['guarded']['status']=='ready' for r in sidecar),
    'new_ready':sum(r['new_ready'] for r in sidecar),
    'closed_ready_typed_coverage':all(r['typed_coverage'] for r in sidecar if r['closure']['status']=='ready'),
    'unsafe_mutations':mutations, 'legal_controls':controls,
    'safe_omission_recovered':True, 'compiler_injected_controls':len(injected), 'usage':usage,
    'source_hashes':before_hash, 'catalog':catalog.fingerprint,
    'model_calls':0,'sql_db_calls':0,
    'decision':'A安全可救0<3，只保留型別護欄；B人工參考注入節點通過，待獨立核准後測六題自然抽取。',
    'limitation':'oracle檢查不是runtime證明；free-text缺值政策需人工審查。編譯注入不代表模型能產生骨架。'}
for name, value in [('mvp0-sidecar.json',sidecar),('mvp0-summary.json',summary),('b1-injected-controls.json',injected)]:
    (DEST/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in summary.items() if k not in ('unsafe_mutations','usage')},ensure_ascii=False))
