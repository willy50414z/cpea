"""Synthetic contracts and model outputs for the planning boundary."""
import json
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace

import yaml
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog


def catalog_at(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    columns = {
        'stock': {'store_id':'number','product_id':'number','stock_qty':'number','snapshot_date':'date'},
        'sales': {'store_id':'number','product_id':'number','quantity':'number','order_date':'date','sales_channel':'string'},
        'kpi': {'store_id':'number','sales_month':'date','target_amount':'number'},
        'monthly': {'store_id':'number','product_id':'number','units_sold':'number','sales_month':'date'},
    }
    grains = {'stock':['store_id','product_id'],'sales':['store_id','product_id','order_date','sales_channel'],
              'kpi':['store_id','sales_month'],'monthly':['store_id','product_id','sales_month']}
    index = {}
    for name, fields in columns.items():
        view = 'demo.' + name
        data = {'version':3,'view':view,'summary':f'Synthetic {name}',
                'grain':{'description':name,'keys':grains[name]},
                'columns':{c:{'type':t,'role':'identifier' if c.endswith('_id') else 'dimension' if t!='number' else 'measure',
                              'description':c} for c,t in fields.items()}}
        (root / (name+'.yaml')).write_text(yaml.safe_dump(data),encoding='utf-8')
        index[view] = {'path':name+'.yaml'}
    (root/'catalog.yaml').write_text(yaml.safe_dump({'schema':'demo','views':index}),encoding='utf-8')
    (root/'manifest.yaml').write_text(yaml.safe_dump({'profile_id':'synthetic-planning','contract_version':'3','source_kind':'sql','catalog':'catalog.yaml','status':'approved'}),encoding='utf-8')
    return SchemaCatalog(root)


def settings():
    return replace(AssistantSettings.from_env(), context_window=64000, max_output_tokens=8000,
                   token_count_endpoint=None, llm_provider='azure')


def draft():
    return {'status':'ready','strategy':'multi_view','tasks':[
        {'task_id':'stock','view':'demo.stock','required_columns':['store_id','product_id','stock_qty'],
         'output_grain':['store_id','product_id'],'attributes':['stock_qty'],'request':'目前庫存'},
        {'task_id':'sales','view':'demo.sales','required_columns':['store_id','product_id','quantity','order_date'],
         'filters':[{'column':'order_date','operator':'>=','value':'2026-09-01'},
                    {'column':'order_date','operator':'<','value':'2026-10-01'}],
         'metrics':{'quantity':'sum'},'group_by':['store_id','product_id'],
         'output_grain':['store_id','product_id'],'request':'九月銷量'}],
        'integration':{'anchor_task':'stock','output_grain':['store_id','product_id'],'edges':[
            {'left_task':'stock','right_task':'sales','left_keys':['store_id','product_id'],
             'right_keys':['store_id','product_id'],'mode':'left','cardinality':'one_to_one','preserve_task':'stock'}],
            'notes':['目前庫存與九月銷量按門市商品合併，不跨日加總庫存。']}}


class FakeLLM:
    def __init__(self, payload=None, error=None):
        self.payload = draft() if payload is None else payload
        self.error = error
        self.calls = []

    def invoke(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        return SimpleNamespace(content=json.dumps(self.payload,ensure_ascii=False),usage_metadata={'input_tokens':10,'output_tokens':20})
