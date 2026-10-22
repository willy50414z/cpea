"""Own responsibility and exact same-view dependencies, without inferred answers."""
from copy import deepcopy
import importlib
import importlib.util
import json
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from test_evidence_bound_managed_contract import inputs as previous_inputs
from test_three_stage_view_selection import INV, MONTH, SALES


def api():
    assert importlib.util.find_spec('evaluations.own_responsibility_managed_contract'), 'own responsibility wire missing'
    return importlib.import_module('evaluations.own_responsibility_managed_contract')


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def inputs(catalog):
    request, rec, maps, sel = previous_inputs(catalog)
    for data in maps:
        for entry in data['entries'].values():
            entry.pop('gaps')
            entry['own_gap'] = entry['status'] in ('unsupported', 'uncertain')
    return request, rec, maps, sel


def requirement(request, rid, quote, kind, *, scopes=(), grains=(), binding=None):
    return dict(requirement_id=rid, start=request.index(quote), end=request.index(quote)+len(quote),
                business_object=quote, kind=kind, scope_ids=list(scopes), grain=quote,
                population='契約母體', grain_binding=binding, grain_requirement_ids=list(grains))


def entry(status='unsupported', mappings=(), path=None, own=True):
    return dict(status=status, mappings=list(mappings), contract_path=path, own_gap=own)


def recall(catalog, request, requirements):
    return api().materialize_recall(api().RecallWire.model_validate(dict(requirements=requirements)), request, catalog)


def apply(catalog, request, rec, view, entries):
    policy = next(v.policy for v in catalog.views() if v.name == view)
    schema = api().coverage_schema(rec)
    wire = api().parse_wire(AIMessage(content=json.dumps(dict(entries=entries), ensure_ascii=False)), schema)
    return api().materialize_coverage(wire, rec, request, catalog, policy)


def gaps(row):
    return [json.loads(text) for text in row.missing_requirements]


@pytest.mark.parametrize('view,key,quote,rid', [
    ('demo_retail.v_daily_sales', 'store_id', '各店各商品', 'a/b~店🧾'),
    ('demo_retail.v_customer_value', 'customer_id', '各會員各商品', 'model_dump'),
])
def test_self_partial_grain_keeps_available_key_without_inventing_self_dependency(catalog, view, key, quote, rid):
    rec = recall(catalog, quote, [requirement(quote, rid, quote, 'grain')])
    row = apply(catalog, quote, rec, view, {rid: entry('partial', [dict(column=key, role='key')], '/grain/description')}).entries[0]
    assert row.status == 'partial' and [(m.column, m.role) for m in row.mappings] == [(key, 'key')]
    assert rec.requirements[0].grain_requirement_ids == []
    assert gaps(row) == [dict(statement='契約未證明以下責任完整可用', aspect='self',
                             requirements=[dict(requirement_id=rid, quote=quote, status='partial')])]


@pytest.mark.parametrize('status,own,mapped,valid', [
    ('partial', True, True, True), ('partial', False, True, False), ('partial', True, False, False),
    ('supported', True, True, False), ('supported', False, True, True),
    ('supported', False, False, False), ('unsupported', True, False, True),
    ('uncertain', True, False, True), ('unsupported', False, False, False),
    ('uncertain', False, False, False), ('unsupported', True, True, False),
])
def test_status_and_own_decision_are_never_repaired(catalog, status, own, mapped, valid):
    request = '各店各商品'
    rec = recall(catalog, request, [requirement(request, 'G', request, 'grain')])
    data = {'G': entry(status, [dict(column=c, role='key') for c in ('store_id', 'product_id')] if mapped else [], '/grain/description', own)}
    original = deepcopy(data)
    if valid:
        row = apply(catalog, request, rec, INV, data).entries[0]
        assert row.status == status and len(row.mappings) == (2 if mapped else 0)
    else:
        with pytest.raises(ValueError): apply(catalog, request, rec, INV, data)
    assert data == original


@pytest.mark.parametrize('bad', [None, 0, 1, 'true', 'false', [], {}])
def test_own_gap_is_required_strict_boolean(catalog, bad):
    request, data, maps, _ = inputs(catalog)
    rec = recall(catalog, request, data['requirements'])
    maps[0]['entries']['stock']['own_gap'] = bad
    with pytest.raises(ValueError):
        apply(catalog, request, rec, list(catalog.views())[0].name, maps[0]['entries'])


@pytest.mark.parametrize('mutation', ['missing_own', 'old_gaps', 'reason', 'missing_slot', 'unknown_slot', 'duplicate', 'nan'])
def test_new_slots_reject_omissions_old_output_and_ambiguous_json(catalog, mutation):
    request, data, maps, _ = inputs(catalog)
    rec = recall(catalog, request, data['requirements'])
    raw = maps[0]
    if mutation == 'missing_own': raw['entries']['stock'].pop('own_gap')
    if mutation == 'old_gaps': raw['entries']['stock']['gaps'] = []
    if mutation == 'reason': raw['entries']['stock']['reason'] = '來源僅有銷售'
    if mutation == 'missing_slot': raw['entries'].pop('stock')
    if mutation == 'unknown_slot': raw['entries']['extra'] = deepcopy(raw['entries']['stock'])
    text = json.dumps(raw)
    if mutation == 'duplicate': text = text.replace('"own_gap": true', '"own_gap":true,"own_gap":false', 1)
    if mutation == 'nan': text = text.replace('"own_gap": true', '"own_gap":NaN', 1)
    with pytest.raises(ValueError): api().parse_wire(AIMessage(content=text), api().coverage_schema(rec))


def graph(catalog, *, scope_status='unsupported', grain_status='partial', own=False):
    request = '各店各商品2026年9月線上通路的淨銷售額'
    reqs = [requirement(request, '粒/🧾', '各店各商品', 'grain'),
            requirement(request, '月', '2026年9月', 'filter'),
            requirement(request, '通路', '線上通路', 'filter'),
            requirement(request, '額', '淨銷售額', 'metric', scopes=['通路', '月'], grains=['粒/🧾'], binding='linked')]
    rec = recall(catalog, request, reqs)
    rows = {'粒/🧾': entry(grain_status, [dict(column='store_id', role='key')] if grain_status == 'partial' else [], '/grain/description'),
            '月': entry(scope_status), '通路': entry(scope_status),
            '額': entry('partial', [dict(column='revenue', role='metric', aggregation='sum')], '/columns/revenue/description', own)}
    return request, rec, rows


@pytest.mark.parametrize('scope_status', ['partial', 'unsupported', 'uncertain'])
@pytest.mark.parametrize('grain_status', ['partial', 'unsupported', 'uncertain'])
def test_all_unfinished_scope_and_grain_dependencies_are_derived_in_exact_order(catalog, scope_status, grain_status):
    request, rec, rows = graph(catalog, scope_status=scope_status, grain_status=grain_status)
    if scope_status == 'partial':
        rows['月']['mappings'] = [dict(column='sales_date', role='filter', operator='>=', value='2026-09-01')]
        rows['月']['contract_path'] = '/columns/sales_date/description'
        rows['通路']['mappings'] = [dict(column='store_id', role='filter', operator='=', value=1)]
        rows['通路']['contract_path'] = '/columns/store_id/description'
    row = apply(catalog, request, rec, 'demo_retail.v_daily_sales', rows).entries[-1]
    assert [(g['aspect'], [(r['requirement_id'], r['quote'], r['status']) for r in g['requirements']]) for g in gaps(row)] == [
        ('scope', [('通路', '線上通路', scope_status), ('月', '2026年9月', scope_status)]),
        ('grain', [('粒/🧾', '各店各商品', grain_status)])]
    assert row.status == 'partial' and row.mappings[0].column == 'revenue'
    assert '僅有' not in ''.join(row.missing_requirements)


def test_own_gap_and_both_dependency_sets_remain_distinct(catalog):
    request, rec, rows = graph(catalog, own=True)
    row = apply(catalog, request, rec, 'demo_retail.v_daily_sales', rows).entries[-1]
    assert [g['aspect'] for g in gaps(row)] == ['self', 'scope', 'grain']
    assert gaps(row)[0]['requirements'] == [dict(requirement_id='額', quote='淨銷售額', status='partial')]


@pytest.mark.parametrize('kind,column,role', [
    ('metric','stock_qty','metric'), ('attribute','stock_status','attribute'),
    ('metadata','snapshot_date','metadata'), ('filter','snapshot_date','filter'),
    ('key','store_id','key'), ('population','store_id','key'), ('grain','store_id','key')])
def test_every_kind_treats_explicit_grain_refs_as_hard_dependencies(catalog, kind, column, role):
    request = '各店各商品顯示資料'
    rec = recall(catalog, request, [requirement(request,'G','各店各商品','grain'),
        requirement(request,'X','顯示資料',kind,grains=['G'],binding='linked' if kind=='metric' else None)])
    mapping = dict(column=column, role=role)
    if kind == 'metric': mapping['aggregation'] = 'sum'
    if kind == 'filter': mapping.update(operator='>=', value='2026-09-01')
    rows = {'G': entry(path='/grain/description'),
            'X': entry('supported', [mapping], '/grain/description' if kind=='grain' else '/columns/'+column+'/description', False)}
    with pytest.raises(ValueError, match='grain'): apply(catalog, request, rec, INV, rows)
    rows['X']['status'] = 'partial'
    row = apply(catalog, request, rec, INV, rows).entries[1]
    assert [g['aspect'] for g in gaps(row)] == ['grain'] and len(row.mappings) == 1
    rows['G'] = entry('supported', [dict(column=c, role='key') for c in ('store_id','product_id')], '/grain/description', False)
    rows['X']['status'] = 'supported'
    assert apply(catalog, request, rec, INV, rows).entries[1].missing_requirements == []


def test_month_predicate_is_independent_of_unavailable_output_grain_until_explicitly_linked(catalog):
    request = '各店各商品2026年9月'
    reqs = [requirement(request,'G','各店各商品','grain'),requirement(request,'F','2026年9月','filter')]
    rec = recall(catalog, request, reqs)
    rows = {'G': entry('partial',[dict(column='store_id',role='key')],'/grain/description'),
            'F': entry('supported',[dict(column='sales_date',role='filter',operator=o,value=v) for o,v in [('>=','2026-09-01'),('<','2026-10-01')]],'/columns/sales_date/description',False)}
    assert apply(catalog,request,rec,'demo_retail.v_daily_sales',rows).entries[1].status == 'supported'
    reqs[1]['grain_requirement_ids'] = ['G']
    linked = recall(catalog, request, reqs)
    with pytest.raises(ValueError,match='grain'): apply(catalog,request,linked,'demo_retail.v_daily_sales',rows)
    rows['F']['status'] = 'partial'
    assert gaps(apply(catalog,request,linked,'demo_retail.v_daily_sales',rows).entries[1])[0]['requirements'][0]['requirement_id'] == 'G'


def test_supported_dependencies_emit_no_phantom_gaps_and_partial_without_gap_is_rejected(catalog):
    request, recdata, maps, _ = inputs(catalog)
    rec = recall(catalog, request, recdata['requirements'])
    index = next(i for i,v in enumerate(catalog.views()) if v.name == SALES)
    result = apply(catalog,request,rec,SALES,maps[index]['entries'])
    assert next(e for e in result.entries if e.requirement_id=='sales').missing_requirements == []
    maps[index]['entries']['sales']['status'] = 'partial'
    with pytest.raises(ValueError,match='partial'): apply(catalog,request,rec,SALES,maps[index]['entries'])


@pytest.mark.parametrize('mutation',['unknown','wrong_kind','self','duplicate','empty_link','independent_refs','unspecified'])
def test_reused_recall_and_metric_binding_guards(catalog,mutation):
    request,recdata,maps,_ = inputs(catalog)
    item = recdata['requirements'][1]
    if mutation=='unknown': item['grain_requirement_ids']=['?']
    if mutation=='wrong_kind': item['grain_requirement_ids']=['period']
    if mutation=='self': item['grain_requirement_ids']=['sales']
    if mutation=='duplicate': item['grain_requirement_ids']=['grain','grain']
    if mutation=='empty_link': item['grain_requirement_ids']=[]
    if mutation=='independent_refs': item['grain_binding']='independent'
    if mutation=='unspecified': item.update(grain_binding='unspecified',grain_requirement_ids=[])
    with pytest.raises(ValueError):
        rec=recall(catalog,request,recdata['requirements'])
        apply(catalog,request,rec,SALES,maps[5]['entries'])


@pytest.mark.parametrize('mutation',['column','path','role','aggregation','date','channel','grain_path','null_own'])
def test_own_gap_does_not_exempt_partial_mappings_or_evidence_from_original_guards(catalog,mutation):
    request,recdata,maps,_=inputs(catalog)
    rec=recall(catalog,request,recdata['requirements']); rows=maps[5]['entries']
    target=rows['sales']; target.update(status='partial',own_gap=True)
    if mutation=='column': target['mappings'][0]['column']='missing'
    if mutation=='path': target['contract_path']='/missing'
    if mutation=='role': target['mappings'][0]['role']='attribute'
    if mutation=='aggregation': target['mappings'][0]['aggregation']='median'
    if mutation=='date': rows['period']['mappings'][0]['value']='not-date'
    if mutation=='channel': rows['channel']['mappings'][0]['value']=17
    if mutation=='grain_path': rows['grain']['contract_path']='/summary'
    if mutation=='null_own': target.update(contract_path=None,own_gap=False)
    with pytest.raises(ValueError): apply(catalog,request,rec,SALES,rows)


def test_renamed_contract_and_unicode_id_keep_self_partial_key(catalog,monkeypatch):
    source=deepcopy(next(v.policy for v in catalog.views() if v.name.endswith('v_daily_sales')))
    source['view']='other.rows'; source['grain']['keys']=['shop_key','sales_date']
    source['columns']['shop_key']=source['columns'].pop('store_id')
    monkeypatch.setattr(catalog,'views',lambda:[SimpleNamespace(name='other.rows',policy=source)])
    request='各店各商品'; rec=recall(catalog,request,[requirement(request,'slot_0/🧾',request,'grain')])
    row=apply(catalog,request,rec,'other.rows',{'slot_0/🧾':entry('partial',[dict(column='shop_key',role='key')],'/grain/description')}).entries[0]
    assert row.mappings[0].column=='shop_key' and gaps(row)[0]['requirements'][0]['requirement_id']=='slot_0/🧾'


def test_two_distinct_grains_and_true_scalar_do_not_inherit_other_business_dependencies(catalog):
    request='各店各商品庫存件數；各訂單淨銷售額；全域庫存總件數'
    specs=[('G1','各店各商品','grain',None,[]),('G2','各訂單','grain',None,[]),
           ('M1','庫存件數','metric','linked',['G1']),('M2','淨銷售額','metric','linked',['G2']),
           ('S','全域庫存總件數','metric','independent',[])]
    rec=recall(catalog,request,[requirement(request,i,q,k,grains=refs,binding=b) for i,q,k,b,refs in specs])
    for view,g,m,keys,col in [(INV,'G1','M1',['store_id','product_id'],'stock_qty'),
                             ('demo_retail.v_order_summary','G2','M2',['order_id'],'order_amount')]:
        rows={i:entry(path='/grain/description' if k=='grain' else None) for i,_,k,_,_ in specs}
        rows[g]=entry('supported',[dict(column=c,role='key') for c in keys],'/grain/description',False)
        rows[m]=entry('supported',[dict(column=col,role='metric',aggregation='sum')],'/columns/'+col+'/description',False)
        if view==INV: rows['S']=entry('supported',[dict(column='stock_qty',role='metric',aggregation='sum')],'/columns/stock_qty/description',False)
        result={e.requirement_id:e for e in apply(catalog,request,rec,view,rows).entries}
        assert result[m].status=='supported' and result[m].missing_requirements==[]
        if view==INV: assert result['S'].status=='supported' and result['S'].missing_requirements==[]


def test_fixed_month_dimension_reduction_and_unmet_channel_are_separate(catalog):
    request,recdata,maps,_=inputs(catalog)
    recdata['requirements'][1]['scope_ids']=['period']
    rec=recall(catalog,request,recdata['requirements']); rows=maps[4]['entries']
    rows['sales'].update(status='supported',own_gap=False)
    assert apply(catalog,request,rec,MONTH,rows).entries[1].status=='supported'
    recdata['requirements'][1]['scope_ids']=['channel','period']
    rec=recall(catalog,request,recdata['requirements'])
    with pytest.raises(ValueError,match='scope'): apply(catalog,request,rec,MONTH,rows)
    rows['sales']['status']='partial'
    assert [g['aspect'] for g in gaps(apply(catalog,request,rec,MONTH,rows).entries[1])]==['scope']


def test_partial_is_not_assignable_and_typed_selection_is_still_required(catalog):
    request,recdata,maps,sel=inputs(catalog); rec=recall(catalog,request,recdata['requirements'])
    coverages=[apply(catalog,request,rec,v.name,data['entries']) for v,data in zip(catalog.views(),maps)]
    from evaluations.three_stage_view_selection import finish_selection
    selected=api().materialize_selection(api().SelectionWire.model_validate(sel),rec,coverages,request,catalog)
    assert len(finish_selection(selected,rec,coverages,request,catalog).prepared_requests)==2
    for key in list(sel['draft']['tasks'][0]):
        omitted=deepcopy(sel); omitted['draft']['tasks'][0].pop(key)
        with pytest.raises(ValueError): api().SelectionWire.model_validate(omitted)
    maps[2]['entries']['stock'].update(status='partial',own_gap=True)
    coverages[2]=apply(catalog,request,rec,INV,maps[2]['entries'])
    with pytest.raises(ValueError,match='supported'):
        api().materialize_selection(api().SelectionWire.model_validate(sel),rec,coverages,request,catalog)
