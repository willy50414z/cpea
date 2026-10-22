"""Kind-specific wire shapes preserve decisions and all original semantic guards."""
from copy import deepcopy
import importlib
import importlib.util
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations import own_responsibility_managed_contract as own
from test_own_responsibility_managed_contract import inputs as own_inputs, requirement, gaps
from test_three_stage_view_selection import INV, SALES


def api():
    assert importlib.util.find_spec('evaluations.kind_mapping_managed_contract'), 'kind mapping contract missing'
    return importlib.import_module('evaluations.kind_mapping_managed_contract')


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def inputs(catalog):
    # Only synthetic fixtures are encoded in the new wire. Never transform model raw.
    request, rec, maps, sel = own_inputs(catalog)
    kinds = {r['requirement_id']: r['kind'] for r in rec['requirements']}
    for data in maps:
        for rid, row in data['entries'].items():
            kind = kinds[rid]
            if kind == 'grain': row.pop('contract_path')
            for m in row['mappings']:
                for key in ('role', 'aggregation', 'operator', 'value', 'conditions'):
                    if key == 'aggregation' and kind == 'metric': continue
                    if key == 'conditions' and kind == 'metric': continue
                    if key in ('operator', 'value') and kind == 'filter': continue
                    m.pop(key)
    return request, rec, maps, sel


def recall(catalog, request, requirements):
    return api().materialize_recall(api().RecallWire.model_validate(dict(requirements=requirements)), request, catalog)


def entry(kind, status='unsupported', mappings=(), path=None, own_gap=True):
    row = dict(status=status, mappings=list(mappings), own_gap=own_gap)
    if kind != 'grain': row['contract_path'] = path
    return row


def apply(catalog, request, rec, view, rows):
    schema = api().coverage_schema(rec)
    wire = api().parse_wire(AIMessage(content=json.dumps(dict(entries=rows), ensure_ascii=False)), schema)
    policy = next(v.policy for v in catalog.views() if v.name == view)
    return api().materialize_coverage(wire, rec, request, catalog, policy)


KINDS = ['metric', 'filter', 'key', 'grain', 'population', 'attribute', 'metadata']


@pytest.mark.parametrize('kind', KINDS)
def test_compilation_preserves_every_business_field_and_only_adds_kind_invariants(catalog, kind):
    request = '需求'
    rec = recall(catalog, request, [requirement(request, 'model_dump/🧾', request, kind,
        binding='independent' if kind == 'metric' else None)])
    mapping = dict(column='chosen')
    if kind == 'metric': mapping.update(aggregation='sum', conditions=[dict(column='time', operator='>=', value='2031-02-01')])
    if kind == 'filter': mapping.update(operator='IS NULL', value=None)
    row = entry(kind, 'partial', [mapping], '/some/chosen/path')
    wire = api().coverage_schema(rec).model_validate(dict(entries={'model_dump/🧾': row}))
    before = wire.model_dump(by_alias=True)
    compiled = api().compile_coverage(wire, rec).model_dump(by_alias=True)['entries']['model_dump/🧾']
    assert compiled == dict(status='partial', own_gap=True,
        contract_path='/grain/description' if kind == 'grain' else '/some/chosen/path',
        mappings=[dict(column='chosen', role='key' if kind in ('grain','population') else kind,
            aggregation='sum' if kind == 'metric' else None,
            operator='IS NULL' if kind == 'filter' else None, value=None,
            conditions=[dict(column='time', operator='>=', value='2031-02-01')] if kind == 'metric' else [])])
    assert wire.model_dump(by_alias=True) == before


@pytest.mark.parametrize('kind,extra', [(k,e) for k in KINDS for e in ['role','aggregation','operator','value','conditions']
    if not (k=='metric' and e in ('aggregation','conditions')) and not (k=='filter' and e in ('operator','value'))])
def test_kind_schema_rejects_every_inapplicable_mapping_field(catalog, kind, extra):
    rec = recall(catalog, '需求', [requirement('需求','X','需求',kind,binding='independent' if kind=='metric' else None)])
    mapping = dict(column='x')
    if kind == 'metric': mapping.update(aggregation='sum',conditions=[])
    if kind == 'filter': mapping.update(operator='=',value=1)
    mapping[extra] = dict(role='key',aggregation=None,operator=None,value=None,conditions=[])[extra]
    with pytest.raises(ValueError): api().coverage_schema(rec).model_validate(dict(entries={'X':entry(kind,'partial',[mapping])}))


@pytest.mark.parametrize('kind,missing', [('metric','column'),('metric','aggregation'),('metric','conditions'),
    ('filter','column'),('filter','operator'),('filter','value'),('grain','column'),('key','column'),
    ('attribute','column'),('metadata','column'),('population','column')])
def test_kind_schema_requires_genuine_mapping_decisions(catalog,kind,missing):
    rec=recall(catalog,'需求',[requirement('需求','X','需求',kind,binding='independent' if kind=='metric' else None)])
    m=dict(column='x')
    if kind=='metric': m.update(aggregation='sum',conditions=[])
    if kind=='filter': m.update(operator='IS NULL',value=None)
    m.pop(missing)
    with pytest.raises(ValueError): api().coverage_schema(rec).model_validate(dict(entries={'X':entry(kind,'partial',[m])}))


@pytest.mark.parametrize('mutation',['null_aggregation','missing_condition_value','missing_own','coerced_own','missing_path','grain_path','duplicate','nan','old_wire'])
def test_parser_rejects_missing_decisions_ambiguous_json_and_old_wire(catalog,mutation):
    request, rd, maps, _=inputs(catalog); rec=recall(catalog,request,rd['requirements']); data=maps[5]
    if mutation=='null_aggregation': data['entries']['sales']['mappings'][0]['aggregation']=None
    if mutation=='missing_condition_value': data['entries']['sales']['mappings'][0]['conditions']=[dict(column='channel',operator='=')]
    if mutation=='missing_own': data['entries']['stock'].pop('own_gap')
    if mutation=='coerced_own': data['entries']['stock']['own_gap']=1
    if mutation=='missing_path': data['entries']['stock'].pop('contract_path')
    if mutation=='grain_path': data['entries']['grain']['contract_path']='/grain/description'
    if mutation=='old_wire': data=own_inputs(catalog)[2][5]
    raw=json.dumps(data)
    if mutation=='duplicate': raw=raw.replace('"own_gap": true','"own_gap":true,"own_gap":false',1)
    if mutation=='nan': raw=raw.replace('"own_gap": true','"own_gap":NaN',1)
    with pytest.raises(ValueError): api().parse_wire(AIMessage(content=raw),api().coverage_schema(rec))


def test_same_id_different_kind_has_distinct_schema_identity_and_cannot_compile_cross_kind(catalog):
    f=recall(catalog,'需求',[requirement('需求','same','需求','filter')])
    g=recall(catalog,'需求',[requirement('需求','same','需求','grain')])
    assert api().coverage_schema(f).__name__ != api().coverage_schema(g).__name__
    wire=api().coverage_schema(f).model_validate(dict(entries={'same':entry('filter')}))
    with pytest.raises(ValueError): api().compile_coverage(wire,g)


@pytest.mark.parametrize('kind',KINDS)
def test_exported_schema_matches_required_parser_shape_at_every_layer(catalog,kind):
    rec=recall(catalog,'需求',[requirement('需求','model_dump/🧾','需求',kind,binding='independent' if kind=='metric' else None)])
    schema=api().coverage_schema(rec).model_json_schema()
    def resolve(node): return schema['$defs'][node['$ref'].rsplit('/',1)[1]]
    slots=resolve(schema['properties']['entries']); decision=resolve(slots['properties']['model_dump/🧾'])
    mapping=resolve(decision['properties']['mappings']['items'])
    assert schema['required']==['entries'] and schema['additionalProperties'] is False
    assert slots['required']==['model_dump/🧾'] and slots['additionalProperties'] is False
    assert set(decision['required'])==({'status','own_gap','mappings'} if kind=='grain' else {'status','own_gap','mappings','contract_path'})
    assert decision['additionalProperties'] is False
    assert set(mapping['required'])==({'column','aggregation','conditions'} if kind=='metric' else {'column','operator','value'} if kind=='filter' else {'column'})
    assert mapping['additionalProperties'] is False
    if kind=='metric':
        assert mapping['properties']['aggregation']['type']=='string'
        condition=resolve(mapping['properties']['conditions']['items'])
        assert set(condition['required'])=={'column','operator','value'} and condition['additionalProperties'] is False


@pytest.mark.parametrize('end_operator,end',[('<','2031-03-01'),('<=','2031-02-28')])
def test_month_two_predicates_are_preserved_in_order_without_output_grain_dependency(catalog,end_operator,end):
    request='各店各商品2031年2月'
    rec=recall(catalog,request,[requirement(request,'G','各店各商品','grain'),requirement(request,'F','2031年2月','filter')])
    rows={'G':entry('grain','partial',[dict(column='store_id')]),'F':entry('filter','supported',[
        dict(column='sales_date',operator='>=',value='2031-02-01'),dict(column='sales_date',operator=end_operator,value=end)],'/columns/sales_date/description',False)}
    row=apply(catalog,request,rec,'demo_retail.v_daily_sales',rows).entries[1]
    assert row.status=='supported' and row.missing_requirements==[]
    assert [(m.column,m.operator,m.value) for m in row.mappings]==[('sales_date','>=','2031-02-01'),('sales_date',end_operator,end)]


@pytest.mark.parametrize('mutation',[None,'missing_independent_filter','missing_condition_column','bad_aggregation','bad_type','bad_operator'])
def test_conditional_metric_keeps_independent_filter_and_all_original_guards(catalog,mutation):
    request='線上淨銷售額'
    rec=recall(catalog,request,[requirement(request,'F','線上','filter'),requirement(request,'M','淨銷售額','metric',scopes=['F'],binding='independent')])
    condition=dict(column='sales_channel',operator='=',value='online')
    rows={'F':entry('filter','supported',[dict(condition)],'/columns/sales_channel/description',False),
        'M':entry('metric','supported',[dict(column='net_sales',aggregation='sum',conditions=[dict(condition)])],'/columns/net_sales/description',False)}
    if mutation=='missing_independent_filter': rows['F']=entry('filter'); rows['M']['status']='partial'
    if mutation=='missing_condition_column': rows['M']['mappings'][0]['conditions'][0]['column']='missing'
    if mutation=='bad_aggregation': rows['M']['mappings'][0]['column']='unit_price'
    if mutation=='bad_type': rows['M']['mappings'][0]['conditions'][0]['value']=123
    if mutation=='bad_operator': rows['M']['mappings'][0]['conditions'][0]['operator']='BETWEEN'
    if mutation:
        with pytest.raises(ValueError): apply(catalog,request,rec,SALES,rows)
    else:
        row=apply(catalog,request,rec,SALES,rows).entries[1]
        assert row.mappings[0].conditions[0].model_dump()==condition


def test_valid_operator_disallowed_by_contract_still_fails_original_guard(catalog,monkeypatch):
    request='線上淨銷售額'
    rec=recall(catalog,request,[requirement(request,'F','線上','filter'),requirement(request,'M','淨銷售額','metric',scopes=['F'],binding='independent')])
    condition=dict(column='sales_channel',operator='=',value='online')
    rows={'F':entry('filter','supported',[dict(condition)],'/columns/sales_channel/description',False),
        'M':entry('metric','supported',[dict(column='net_sales',aggregation='sum',conditions=[dict(condition)])],'/columns/net_sales/description',False)}
    original=catalog.field_contract
    monkeypatch.setattr(catalog,'field_contract',lambda view,col:dict(original(view,col),disallowed_operators=['=']) if col=='sales_channel' else original(view,col))
    with pytest.raises(ValueError,match='operator'): apply(catalog,request,rec,SALES,rows)


@pytest.mark.parametrize('view,key,quote,rid',[('demo_retail.v_daily_sales','store_id','各店各商品','a/b~店🧾'),
    ('demo_retail.v_customer_value','customer_id','各會員各商品','model_dump')])
def test_useful_partial_grain_is_expressible_across_sources_and_arbitrary_ids(catalog,view,key,quote,rid):
    rec=recall(catalog,quote,[requirement(quote,rid,quote,'grain')])
    row=apply(catalog,quote,rec,view,{rid:entry('grain','partial',[dict(column=key)])}).entries[0]
    assert row.status=='partial' and [(m.column,m.role) for m in row.mappings]==[(key,'key')]
    assert gaps(row)[0]['requirements']==[dict(requirement_id=rid,quote=quote,status='partial')]


def test_renamed_contract_does_not_depend_on_fixed_business_ids_or_columns(catalog,monkeypatch):
    source=deepcopy(next(v.policy for v in catalog.views() if v.name.endswith('v_daily_sales')))
    source['view']='other.rows'; source['grain']['keys']=['shop_key','sales_date']
    source['columns']['shop_key']=source['columns'].pop('store_id')
    monkeypatch.setattr(catalog,'views',lambda:[SimpleNamespace(name='other.rows',policy=source)])
    rec=recall(catalog,'各店各商品',[requirement('各店各商品','slot_0/🧾','各店各商品','grain')])
    row=apply(catalog,'各店各商品',rec,'other.rows',{'slot_0/🧾':entry('grain','partial',[dict(column='shop_key')])}).entries[0]
    assert row.mappings[0].column=='shop_key' and row.contract_evidence[0].path=='/grain/description'


@pytest.mark.parametrize('kind,column',[('metric','stock_qty'),('attribute','stock_status'),('metadata','snapshot_date'),
    ('filter','snapshot_date'),('key','store_id'),('population','store_id'),('grain','store_id')])
def test_all_kinds_reuse_hard_grain_dependencies_and_own_gap_rules(catalog,kind,column):
    request='各店各商品顯示資料'
    rec=recall(catalog,request,[requirement(request,'G','各店各商品','grain'),requirement(request,'X','顯示資料',kind,
        grains=['G'],binding='linked' if kind=='metric' else None)])
    m=dict(column=column)
    if kind=='metric': m.update(aggregation='sum',conditions=[])
    if kind=='filter': m.update(operator='>=',value='2031-02-01')
    rows={'G':entry('grain'),'X':entry(kind,'supported',[m],'/columns/'+column+'/description',False)}
    with pytest.raises(ValueError,match='grain'): apply(catalog,request,rec,INV,rows)
    rows['X']['status']='partial'
    row=apply(catalog,request,rec,INV,rows).entries[1]
    assert [g['aspect'] for g in gaps(row)]==['grain']
    rows['X']['own_gap']=True
    assert [g['aspect'] for g in gaps(apply(catalog,request,rec,INV,rows).entries[1])]==['self','grain']
    rows['X']['status']='supported'
    with pytest.raises(ValueError,match='own_gap'): apply(catalog,request,rec,INV,rows)
    rows['G']=entry('grain','supported',[dict(column='store_id'),dict(column='product_id')],own_gap=False)
    rows['X']['own_gap']=False
    assert apply(catalog,request,rec,INV,rows).entries[1].missing_requirements==[]


@pytest.mark.parametrize('mutation',['unknown_column','wrong_path','not_selectable','bad_date'])
def test_kind_compiler_cannot_bypass_reference_or_mapping_guards(catalog,mutation,monkeypatch):
    request,rd,maps,_=inputs(catalog); rec=recall(catalog,request,rd['requirements']); rows=maps[5]['entries']
    if mutation=='unknown_column': rows['sales']['mappings'][0]['column']='missing'
    if mutation=='wrong_path': rows['sales']['contract_path']='/missing'
    if mutation=='bad_date': rows['period']['mappings'][0]['value']='not-date'
    if mutation=='not_selectable':
        original=catalog.field_contract
        monkeypatch.setattr(catalog,'field_contract',lambda view,col:dict(original(view,col),capabilities=[]) if col=='store_id' else original(view,col))
    with pytest.raises(ValueError): apply(catalog,request,rec,SALES,rows)


# These expectations are predeclared semantic judgments, not parser capabilities.
SEMANTIC_CASES=[
    ('omit_useful_store_key','grain','各店各商品','demo_retail.v_daily_sales',entry('grain'),'SEMANTIC_REJECT'),
    ('only_store_claims_full_grain','grain','各店各商品','demo_retail.v_daily_sales',entry('grain','supported',[dict(column='store_id')],own_gap=False),'SEMANTIC_REJECT'),
    ('unrelated_customer_key','grain','各店各商品','demo_retail.v_customer_value',entry('grain','partial',[dict(column='customer_id')]),'SEMANTIC_REJECT'),
    ('store_key_claims_inventory_population','population','保留所有庫存商品','demo_retail.v_daily_sales',entry('population','supported',[dict(column='store_id')],'/summary',False),'SEMANTIC_REJECT'),
    ('sold_is_not_stock','metric','庫存件數','demo_retail.v_inventory_status',entry('metric','supported',[dict(column='sold_qty_30d',aggregation='sum',conditions=[])],'/columns/sold_qty_30d/description',False),'SEMANTIC_REJECT'),
    ('wrong_month','filter','2031年2月','demo_retail.v_daily_sales',entry('filter','supported',[dict(column='sales_date',operator='>=',value='2031-03-01')],'/columns/sales_date/description',False),'SEMANTIC_REJECT'),
    ('missing_online','metric','線上淨銷售額','demo_retail.v_sales_detail',entry('metric','supported',[dict(column='net_sales',aggregation='sum',conditions=[])],'/columns/net_sales/description',False),'SEMANTIC_REJECT'),
    ('false_independent','metric','各店各商品銷售額','demo_retail.v_daily_sales',entry('metric','supported',[dict(column='revenue',aggregation='sum',conditions=[])],'/columns/revenue/description',False),'SEMANTIC_REJECT'),
    ('unrelated_key_not_forced','grain','各店各商品','demo_retail.v_customer_value',entry('grain'),'SEMANTIC_ACCEPT'),
    ('store_not_inventory_universe','population','保留所有庫存商品','demo_retail.v_daily_sales',entry('population'),'SEMANTIC_ACCEPT'),
]


@pytest.mark.parametrize('name,kind,quote,view,row,semantic_verdict',SEMANTIC_CASES,ids=[c[0] for c in SEMANTIC_CASES])
def test_semantic_controls_are_distinct_from_structural_acceptance(catalog,name,kind,quote,view,row,semantic_verdict,record_property):
    rec=recall(catalog,quote,[requirement(quote,'arbitrary',quote,kind,binding='independent' if kind=='metric' else None)])
    result=apply(catalog,quote,rec,view,{'arbitrary':deepcopy(row)})
    assert result.entries[0].status==row['status']
    record_property('predeclared_semantic_verdict',semantic_verdict)
    # Parser acceptance is deliberately not a claim that the business answer is correct.
