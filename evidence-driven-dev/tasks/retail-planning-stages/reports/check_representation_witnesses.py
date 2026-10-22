"""以少量合成列檢查兩種表示差異；不執行 SQL、不改原分。"""
from collections import defaultdict
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
folder = Path(sys.argv[1])
records = [json.loads(l) for l in (folder/'results.jsonl').read_text(encoding='utf-8').splitlines()]
by_id = {(r['case_id'], r['arm']):r for r in records}

# These witnesses apply only after checking the actual generated clauses.
d14 = by_id[('cross-view-14','C_staged')]['response']['draft']
t14 = next(t for t in d14['tasks'] if t['view'].endswith('v_inventory_status'))
assert not t14['filters'] and not t14['metrics']
assert t14['conditional_metrics'] == [{'column':'stock_status','aggregation':'count',
    'conditions':[{'column':'stock_status','operator':'=','value':'缺貨'}]}]
inventory = [(1,11,0,'缺貨'),(1,12,8,'正常'),(2,21,4,'正常'),(3,31,0,'缺貨')]
expected, alternative = defaultdict(int), defaultdict(int)
for store, product, qty, status in inventory:
    expected[store] += int(qty == 0)
    alternative[store] += int(status == '缺貨' and status is not None)
assert expected == alternative == {1:1,2:0,3:1}
# The original failure used a global stock_qty=0 filter and loses store 2.
filtered_population = {s for s,p,q,status in inventory if q == 0}
assert 2 not in filtered_population

d18 = by_id[('cross-view-18','C_staged')]['response']['draft']
t18 = next(t for t in d18['tasks'] if t['view'].endswith('v_order_summary'))
assert not t18['metrics'] and len(t18['conditional_metrics']) == 1
m18 = t18['conditional_metrics'][0]
assert m18['column'] == 'order_id' and m18['aggregation'] == 'count_distinct'
canonical = lambda ff: sorted((f['column'],f['operator'],str(f['value'])) for f in ff)
assert canonical(t18['filters']) == canonical(m18['conditions'])
assert canonical(t18['filters']) == canonical([
    {'column':'order_month','operator':'=','value':'2026-09-01'},
    {'column':'sales_channel','operator':'=','value':'in_store'}])
orders = [(101,1,'2026-09-01','in_store'),(102,1,'2026-09-01','online'),
          (103,2,'2026-09-01','in_store'),(104,2,'2026-08-01','in_store')]
groups = defaultdict(list)
for oid,cid,month,channel in orders:
    if month == '2026-09-01' and channel == 'in_store':
        groups[cid].append(oid)
simple = {cid:len(ids) for cid,ids in groups.items()}
conditional = {cid:len(set(ids)) for cid,ids in groups.items()}
assert simple == conditional == {1:1,2:1}
# A member with no qualifying order remains unmatched in both source queries.
assert 3 not in simple and 3 not in conditional

d29 = by_id[('cross-view-29','C_staged')]['response']['draft']
t29 = next(t for t in d29['tasks'] if t['view'].endswith('v_store_monthly_kpi'))
assert canonical(t29['filters']) == canonical([
    {'column':'sales_month','operator':'>=','value':'2026-09-01'},
    {'column':'sales_month','operator':'<=','value':'2026-09-01'}])
samples = ['2026-08-01','2026-09-01','2026-09-15','2026-10-01']
equality = [d for d in samples if d == '2026-09-01']
same_bounds = [d for d in samples if '2026-09-01' <= d <= '2026-09-01']
assert equality == same_bounds == ['2026-09-01']
report = {'result':'PASS','scope':'合成見證，不是完整語意或 SQL 驗證，不回寫原始分數。',
    'case14':{'observation':'以契約stock_status映射作條件計數，合成資料保留零缺貨門市；原global filter版本刪除該門市。',
        'expected':dict(expected),'alternative':dict(alternative),'limited_to':'status映射與非空條件欄位契約成立；不涵蓋所有整合細節。'},
    'case18':{'observation':'來源filters已與conditional conditions完全相同，且order_id為來源唯一鍵；合成資料count與conditional count_distinct一致。',
        'expected':simple,'alternative':conditional,'limited_to':'只檢查這一特定計數表示，不能全面放寬conditional與一般度量的等價。'},
    'case29':{'observation':'同欄位>=同日且<=同日，在合成日期域與等於該日一致；原grader未正規化此表示。',
        'expected':equality,'alternative':same_bounds,'limited_to':'只檢查月份篩選表示，未全面核准其餘欄位角色與基數。'}}
(ROOT/'reports/representation-witnesses.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(report,ensure_ascii=False,indent=2))
