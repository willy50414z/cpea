"""合成列只見證參考語意，不宣稱執行未實作的 preparation 或 SQL。"""
from collections import defaultdict
import json
from pathlib import Path


witnesses = []
inventory = {(1,11):8, (1,12):0, (2,21):5}
sales = {(1,11):2}
left = {k:(v,sales.get(k)) for k,v in inventory.items()}
inner = {k:(v,sales[k]) for k,v in inventory.items() if k in sales}
assert len(left) == 3 and len(inner) == 1 and left[(2,21)][1] is None
witnesses.append({'id':'有庫存無銷售','expected_rows':3,'inner_rows':1,'missing_is_zero':False})

members = {1,2,3}; orders = {1:[101,102],2:[103]}
member_children = {m:orders.get(m,[]) for m in members}
assert member_children[3] == [] and len(member_children) == 3
witnesses.append({'id':'有會員無訂單','expected_members':3,'unmatched_child':[],'fabricated_order':False})

counts = defaultdict(int)
for (store,product),qty in inventory.items():
    counts[store] += int(qty == 0)
filtered_stores = {store for (store,product),qty in inventory.items() if qty == 0}
assert dict(counts) == {1:1,2:0} and 2 not in filtered_stores
witnesses.append({'id':'零缺貨門市','conditional_count':dict(counts),'global_filter_loses_store':2})

months = {'2026-08-01':4}
series = [(m,months.get(m)) for m in ('2026-08-01','2026-09-01')]
assert series == [('2026-08-01',4),('2026-09-01',None)]
witnesses.append({'id':'雙月缺一月','labeled_values':series,'sum_loses_month_identity':True})

target = {1:100}; products = {1:[11,12]}
attached = [(store,product,target[store]) for store,ps in products.items() for product in ps]
assert sum(target.values()) == 100 and sum(r[2] for r in attached) == 200
witnesses.append({'id':'多商品共享KPI','background_value':100,'incorrect_reaggregation':200})

snapshots = [(1,11,'2026-10-18',8),(1,12,'2026-10-19',3)]
dates = {r[2] for r in snapshots}
assert len(dates) == 2
by_date = defaultdict(int)
for store,product,date,qty in snapshots:by_date[date] += qty
assert dict(by_date) == {'2026-10-18':8,'2026-10-19':3}
witnesses.append({'id':'不同盤點日','dates':sorted(dates),'per_date_qty':dict(by_date),
                  'metadata_proves_same_day':False,'cross_date_stock_sum_allowed':False})

result = {'result':'PASS','witnesses':witnesses,'new_model_calls':0,'sql_db_calls':0,
          'limitation':'合成參考語意見證；沒有執行candidate preparation，不證明SQL API實際相容。'}
Path(__file__).with_name('relational-witnesses.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False))
