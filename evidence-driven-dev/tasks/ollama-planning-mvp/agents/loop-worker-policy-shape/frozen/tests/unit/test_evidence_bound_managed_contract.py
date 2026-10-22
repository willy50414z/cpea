"""Evidence-bound managed wire: semantic decisions remain explicit model inputs."""
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.three_stage_view_selection import finish_selection
from test_managed_three_stage_runner import fixture
from test_three_stage_view_selection import INV, SALES, MONTH


def api():
    assert importlib.util.find_spec('evaluations.evidence_bound_managed_contract'), 'managed evidence-bound wire missing'
    return importlib.import_module('evaluations.evidence_bound_managed_contract')


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def inputs(catalog):
    request, oldrec, maps, oldsel = fixture(catalog)
    rec = oldrec.model_dump(exclude={'candidate_views'})
    for r in rec['requirements']:
        r['grain_binding'] = 'linked' if r['kind'] == 'metric' else None
        r['grain_requirement_ids'] = ['grain'] if r['kind'] == 'metric' else []
    coverages = []
    for old in maps:
        entries = {}
        for e in old.model_dump()['entries']:
            rid = e.pop('requirement_id')
            e.pop('missing_requirements')
            e['gaps'] = [] if e['status'] == 'supported' else [dict(aspect='scope', requirement_ids=['channel'])] if e['status'] == 'partial' else [dict(aspect='population' if rid == 'population' else 'mapping', requirement_ids=[rid])]
            entries[rid] = e
        coverages.append(dict(entries=entries))
    sel = oldsel.model_dump()
    for a in sel['assignments']:
        a.pop('reason')
    for e in sel['exclusions']:
        e.pop('reason')
        e['refs'] = [dict(kind='gap', requirement_ids=['stock'], selected_view=None)]
    return request, rec, coverages, sel


def recalled(catalog, data=None):
    request, rec, _, _ = inputs(catalog)
    return api().materialize_recall(api().RecallWire.model_validate(data or rec), request, catalog)


def mapped(catalog, data=None, index=None, rec=None):
    if index is None: index = next(i for i,v in enumerate(catalog.views()) if v.name == INV)
    request, _, maps, _ = inputs(catalog)
    rec = rec or recalled(catalog)
    policy = list(catalog.views())[index].policy
    schema = api().coverage_schema(rec)
    wire = api().parse_wire(AIMessage(content=json.dumps(data or maps[index])), schema)
    return api().materialize_coverage(wire, rec, request, catalog, policy)


def selected(catalog, data=None):
    request, _, _, sel = inputs(catalog)
    rec = recalled(catalog)
    cov = [mapped(catalog, index=i, rec=rec) for i in range(7)]
    return api().materialize_selection(api().SelectionWire.model_validate(data or sel), rec, cov, request, catalog)


def test_recall_keeps_exact_policy_facts_and_explicit_dependencies(catalog):
    rec = recalled(catalog)
    assert rec.requirements[0].grain_requirement_ids == ['grain']
    assert rec.requirements[-1].kind == 'metadata'
    assert rec.requirements[0].scope_ids == [] and rec.requirements[1].scope_ids == ['channel', 'period']
    for candidate, view in zip(rec.candidate_views, catalog.views()):
        reason = json.loads(candidate.reason)
        assert reason == {'policy': '本MVP保留全部admitted候選', 'evidence': [
            {'path':'/summary','quote':view.policy['summary']},
            {'path':'/grain/description','quote':view.policy['grain']['description']}]}


@pytest.mark.parametrize('mutation', ['empty','unknown','wrong_kind','duplicate','self','independent_refs','no_binding','injected_candidates'])
def test_recall_rejects_wrong_exact_grain_references(catalog, mutation):
    _, rec, _, _ = inputs(catalog)
    r = rec['requirements'][0]
    if mutation == 'empty': r['grain_requirement_ids'] = []
    if mutation == 'unknown': r['grain_requirement_ids'] = ['unknown']
    if mutation == 'wrong_kind': r['grain_requirement_ids'] = ['channel']
    if mutation == 'duplicate': r['grain_requirement_ids'] = ['grain','grain']
    if mutation == 'self': r['grain_requirement_ids'] = ['stock']
    if mutation == 'independent_refs': r['grain_binding'] = 'independent'
    if mutation == 'no_binding': r.pop('grain_binding')
    if mutation == 'injected_candidates': rec['candidate_views'] = []
    with pytest.raises(ValueError): recalled(catalog, rec)


@pytest.mark.parametrize('ids', [['🧾'], ['model_dump','a/b~c','中文','slot_0']])
def test_arbitrary_requirement_ids_and_catalog_order_are_preserved(catalog, ids, monkeypatch):
    request, rec, _, _ = inputs(catalog)
    one = dict(rec['requirements'][2], grain_requirement_ids=[])
    rec['requirements'] = [dict(one, requirement_id=i) for i in ids]
    views = list(catalog.views())[::-1]
    monkeypatch.setattr(catalog, 'views', lambda: views)
    result = recalled(catalog,rec)
    assert [v.view for v in result.candidate_views] == [v.name for v in views]
    schema = api().coverage_schema(result)
    raw = {'entries': {i:dict(status='unsupported',mappings=[],contract_path=None,gaps=[dict(aspect='mapping',requirement_ids=[i])]) for i in ids}}
    cov = api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(raw)),schema),result,request,catalog,views[0].policy)
    assert [e.requirement_id for e in cov.entries] == ids


def test_linked_metric_cannot_be_supported_when_grain_is_unsupported(catalog):
    _, _, maps, _ = inputs(catalog)
    data = maps[5]
    data['entries']['grain'].update(status='unsupported',mappings=[],gaps=[dict(aspect='mapping',requirement_ids=['grain'])])
    with pytest.raises(ValueError, match='grain'): mapped(catalog,data,index=5)
    data['entries']['sales'].update(status='partial',gaps=[dict(aspect='grain',requirement_ids=['grain'])])
    result = mapped(catalog,data,index=5)
    assert result.entries[1].status == 'partial'
    assert {m.column for m in result.entries[1].mappings} == {'discount_amount','net_sales'}
    request, _, _, sel = inputs(catalog)
    rec = recalled(catalog)
    cov = [mapped(catalog,index=i,rec=rec) if i != 5 else result for i in range(7)]
    with pytest.raises(ValueError, match='supported'): api().materialize_selection(api().SelectionWire.model_validate(sel),rec,cov,request,catalog)


@pytest.mark.parametrize('mutation', ['wrong_ref','supported_scope','unlinked_grain','empty_partial','false_no_mapping','extra_fact','wrong_population','unknown_aspect'])
def test_gap_references_cannot_invent_source_facts_or_contradict_coverage(catalog,mutation):
    _, _, maps, _ = inputs(catalog)
    data = maps[4]
    target = data['entries']['sales']
    if mutation == 'wrong_ref': target['gaps'] = [dict(aspect='scope',requirement_ids=['not-real'])]
    if mutation == 'supported_scope': target['gaps'] = [dict(aspect='scope',requirement_ids=['period'])]
    if mutation == 'unlinked_grain': target['gaps'] = [dict(aspect='grain',requirement_ids=['population'])]
    if mutation == 'empty_partial': target['gaps'] = []
    if mutation == 'false_no_mapping': target['gaps'] = [dict(aspect='mapping',requirement_ids=['sales'])]
    if mutation == 'extra_fact': target['gaps'][0]['reason'] = '來源僅含銷售'
    if mutation == 'wrong_population': target['gaps'] = [dict(aspect='population',requirement_ids=['stock'])]
    if mutation == 'unknown_aspect': target['gaps'] = [dict(aspect='made_up',requirement_ids=['sales'])]
    with pytest.raises(ValueError): mapped(catalog,data,index=4)


def test_population_gap_says_unproven_without_asserting_sales_only(catalog):
    _, _, maps, _ = inputs(catalog)
    maps[4]['entries']['population'].update(status='unsupported',mappings=[],gaps=[dict(aspect='population',requirement_ids=['population'])])
    result=mapped(catalog,maps[4],index=4)
    text=next(e for e in result.entries if e.requirement_id=='population').missing_requirements[0]
    assert '保留所有庫存商品' in text and '契約未證明' in text
    assert '僅含' not in text and '退貨' not in text and '狀態欄位' not in text


def test_complete_typed_selection_reuses_original_finish_and_keeps_metadata(catalog):
    result=selected(catalog)
    request,_,_,_=inputs(catalog)
    rec=recalled(catalog)
    response=finish_selection(result,rec,[mapped(catalog,index=i,rec=rec) for i in range(7)],request,catalog)
    assert response.status=='ready' and len(response.prepared_requests)==2
    assert result.draft.tasks[0].metadata_collections==['snapshot_date']
    assert result.draft.integration.edges[0].mode=='left'


@pytest.mark.parametrize('location', ['task','draft','integration','edge','preparation','filter'])
def test_every_typed_field_is_required_in_parser_and_schema(catalog,location):
    _,_,_,sel=inputs(catalog)
    sel['draft']['integration']['preparation']=[dict(task_id='sales',kind='aggregate',keys=['store_id','product_id'],description='先彙總')]
    target={'task':sel['draft']['tasks'][0],'draft':sel['draft'],'integration':sel['draft']['integration'],
            'edge':sel['draft']['integration']['edges'][0], 'preparation':sel['draft']['integration']['preparation'][0],
            'filter':sel['draft']['tasks'][1]['filters'][0]}[location]
    for key in list(target):
        value=target.pop(key)
        with pytest.raises(ValueError): api().SelectionWire.model_validate(sel)
        target[key]=value
    spec=api().SelectionWire.model_json_schema()
    for model in spec['$defs'].values():
        if model.get('type')=='object': assert set(model['properties'])==set(model.get('required',[]))


@pytest.mark.parametrize('mutation',['null_integration','empty_filters','empty_metrics','empty_metadata','gap_wrong_view','redundant_unselected','redundant_unsupported','extra_reason'])
def test_selection_cannot_hide_typed_responsibility_in_request_or_borrow_reasons(catalog,mutation):
    _,_,_,sel=inputs(catalog)
    if mutation=='null_integration': sel['draft']['integration']=None
    if mutation=='empty_filters': sel['draft']['tasks'][1]['filters']=[]
    if mutation=='empty_metrics': sel['draft']['tasks'][1]['metrics']={}
    if mutation=='empty_metadata': sel['draft']['tasks'][0]['metadata_collections']=[]
    if mutation=='gap_wrong_view': sel['exclusions'][3]['refs']=[dict(kind='gap',requirement_ids=['grain'],selected_view=None)]
    if mutation=='redundant_unselected': sel['exclusions'][0]['refs']=[dict(kind='redundant',requirement_ids=['grain'],selected_view=MONTH)]
    if mutation=='redundant_unsupported': sel['exclusions'][0]['refs']=[dict(kind='redundant',requirement_ids=['stock'],selected_view=INV)]
    if mutation=='extra_reason': sel['assignments'][0]['reason']='臆測能力'
    with pytest.raises(ValueError): selected(catalog,sel)


@pytest.mark.parametrize('raw', ['{"requirements":[],"requirements":[]}', '{"requirements":NaN}', '{"draft":{"status":"ready","status":"error"}}'])
def test_all_wire_parsers_reject_duplicate_keys_and_non_json_constants(raw):
    with pytest.raises(ValueError): api().parse_wire(AIMessage(content=raw),api().RecallWire)


def test_original_round4_order_amount_requires_product_grain_but_order_grain_is_legal(catalog):
    folder=Path('evidence-driven-dev/tasks/ollama-planning-mvp/.local/qwen-managed-20261021T171721Z-fa4587')
    old=json.loads((folder/'recall-parsed.json').read_text(encoding='utf-8'))
    request=json.loads((folder/'run.json').read_text(encoding='utf-8'))['case']['request']
    old.pop('candidate_views')
    for r in old['requirements']:
        r['grain_binding']='linked' if r['kind']=='metric' else None
        r['grain_requirement_ids']=['grain_store_product'] if r['kind']=='metric' else []
    rec=api().materialize_recall(api().RecallWire.model_validate(old),request,catalog)
    data=json.loads((folder/'map-04-parsed.json').read_text(encoding='utf-8'))
    for rid,e in data['entries'].items():
        e.pop('missing_requirements')
        e['gaps']=[] if e['status']=='supported' else [dict(aspect='mapping',requirement_ids=[rid])]
    source=next(v.policy for v in catalog.views() if v.name.endswith('v_order_summary'))
    schema=api().coverage_schema(rec)
    def apply():
        return api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(data)),schema),rec,request,catalog,source)
    with pytest.raises(ValueError,match='grain'): apply()
    data['entries']['metric_net_sales'].update(status='partial',gaps=[dict(aspect='grain',requirement_ids=['grain_store_product'])])
    partial=apply()
    row=next(e for e in partial.entries if e.requirement_id=='metric_net_sales')
    assert row.status=='partial' and row.mappings[0].column=='order_amount' and row.mappings[0].aggregation=='sum'
    # A distinct order-level question is a positive control, not a repaired natural answer.
    request2='各訂單的淨銷售額'
    rec2={'requirements':[
        dict(requirement_id='訂單粒度',start=0,end=3,business_object='訂單',kind='grain',scope_ids=[],grain='每訂單',population='已完成訂單',grain_binding=None,grain_requirement_ids=[]),
        dict(requirement_id='金額🧾',start=4,end=8,business_object='淨銷售額',kind='metric',scope_ids=[],grain='每訂單',population='已完成訂單',grain_binding='linked',grain_requirement_ids=['訂單粒度'])]}
    rec2=api().materialize_recall(api().RecallWire.model_validate(rec2),request2,catalog)
    data2={'entries':{'訂單粒度':dict(status='supported',mappings=[dict(column='order_id',role='key')],contract_path='/grain/description',gaps=[]),
                      '金額🧾':dict(status='supported',mappings=[dict(column='order_amount',role='metric',aggregation='sum')],contract_path='/columns/order_amount/description',gaps=[])}}
    result=api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(data2)),api().coverage_schema(rec2)),rec2,request2,catalog,source)
    assert [e.status for e in result.entries]==['supported','supported']


def test_fixed_month_allows_month_dimension_reduction_and_rejects_borrowed_channel(catalog):
    _, rec, maps, _=inputs(catalog)
    rec['requirements'][1]['scope_ids']=['period']
    data=maps[4]
    data['entries']['sales'].update(status='supported',gaps=[])
    result=mapped(catalog,data,index=4,rec=recalled(catalog,rec))
    assert result.entries[1].status=='supported'
    assert result.keys==['store_id','sales_month','product_id']
    # The exact same schema still enforces the channel dependency when actually required.
    with pytest.raises(ValueError,match='scope'): mapped(catalog,data,index=4)


def test_renamed_contract_columns_do_not_change_exact_grain_dependency(catalog,monkeypatch):
    request,rec,maps,_=inputs(catalog)
    original=list(catalog.views())
    source=deepcopy(next(v.policy for v in original if v.name==SALES))
    source['view']='renamed.amount_rows'
    source['grain']['keys']=['shop_key' if c=='store_id' else 'item_key' if c=='product_id' else c for c in source['grain']['keys']]
    source['columns']={('shop_key' if c=='store_id' else 'item_key' if c=='product_id' else 'cash_total' if c=='net_sales' else c):v for c,v in source['columns'].items()}
    from types import SimpleNamespace
    monkeypatch.setattr(catalog,'views',lambda:[SimpleNamespace(name=source['view'],policy=source)])
    # Catalog uses the same admitted contract; the old catalog method itself handles renamed columns.
    data=maps[5]
    for e in data['entries'].values():
        for m in e['mappings']: m['column']={'store_id':'shop_key','product_id':'item_key','net_sales':'cash_total'}.get(m['column'],m['column'])
        if e['contract_path']:
            e['contract_path']=e['contract_path'].replace('/store_id/','/shop_key/').replace('/product_id/','/item_key/').replace('/net_sales/','/cash_total/')
    r=recalled(catalog,rec)
    schema=api().coverage_schema(r)
    result=api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(data)),schema),r,request,catalog,source)
    assert result.entries[1].status=='supported' and any(m.column=='cash_total' for m in result.entries[1].mappings)
    data['entries']['grain'].update(status='unsupported',mappings=[],gaps=[dict(aspect='mapping',requirement_ids=['grain'])])
    with pytest.raises(ValueError,match='grain'):
        api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(data)),schema),r,request,catalog,source)


def test_inventory_without_status_is_valid_until_status_is_actually_requested(catalog,monkeypatch):
    views=list(catalog.views())
    source=deepcopy(next(v.policy for v in views if v.name==INV));source['columns'].pop('stock_status')
    from types import SimpleNamespace
    monkeypatch.setattr(catalog,'views',lambda:[SimpleNamespace(name=v.name,policy=source if v.name==INV else v.policy) for v in views])
    assert selected(catalog).draft.status=='ready'
    request,rec,maps,_=inputs(catalog)
    request+='顯示庫存狀態'
    item=dict(rec['requirements'][-1],requirement_id='真狀態',start=len(request)-4,end=len(request),kind='attribute')
    rec['requirements'].append(item)
    bound=api().materialize_recall(api().RecallWire.model_validate(rec),request,catalog)
    data=maps[2]
    data['entries']['真狀態']=dict(status='supported',mappings=[dict(column='stock_status',role='attribute')],contract_path='/summary',gaps=[])
    with pytest.raises(ValueError,match='column'):
        api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(data)),api().coverage_schema(bound)),bound,request,catalog,source)


def test_explicit_source_exclusion_summary_is_preserved_but_never_inferred(catalog,monkeypatch):
    views=list(catalog.views());source=deepcopy(next(v.policy for v in views if v.name==SALES))
    source['summary']='明示排除退貨，僅含已完成訂單。'
    from types import SimpleNamespace
    monkeypatch.setattr(catalog,'views',lambda:[SimpleNamespace(name=v.name,policy=source if v.name==SALES else v.policy) for v in views])
    candidate=next(v for v in recalled(catalog).candidate_views if v.view==SALES)
    assert json.loads(candidate.reason)['evidence'][0]['quote']=='明示排除退貨，僅含已完成訂單。'
    assert mapped(catalog,index=5).population=='明示排除退貨，僅含已完成訂單。'


def test_original_round4_typed_omission_is_rejected_without_defaults(catalog):
    path=Path('evidence-driven-dev/tasks/ollama-planning-mvp/.local/qwen-managed-20261021T171721Z-fa4587/selection-call.json')
    raw=json.loads(path.read_text(encoding='utf-8'))['response']
    with pytest.raises(ValueError): api().parse_wire(AIMessage(content=raw),api().SelectionWire)


@pytest.mark.parametrize('mutation',['duplicate','missing','extra','population','column','path','role','aggregation','channel_value','date_value','empty_supported','unspecified'])
def test_bound_wire_retains_existing_mapping_guards(catalog,mutation):
    _,rec,maps,_=inputs(catalog)
    data=maps[5]
    if mutation=='duplicate':
        raw=json.dumps(data).replace('"entries": {','"entries":{"sales":{},',1)
        with pytest.raises(ValueError,match='duplicate'): api().parse_wire(AIMessage(content=raw),api().coverage_schema(recalled(catalog)))
        return
    if mutation=='missing': data['entries'].pop('stock')
    if mutation=='extra': data['entries']['unknown']=data['entries']['stock']
    if mutation=='population': data['population']='僅含銷售'
    if mutation=='column': data['entries']['sales']['mappings'][0]['column']='not_real'
    if mutation=='path': data['entries']['sales']['contract_path']='/not_real'
    if mutation=='role': data['entries']['sales']['mappings'][0]['role']='attribute'
    if mutation=='aggregation': data['entries']['sales']['mappings'][0]['aggregation']='median'
    if mutation=='channel_value': data['entries']['channel']['mappings'][0]['value']=123
    if mutation=='date_value': data['entries']['period']['mappings'][0]['value']='not-date'
    if mutation=='empty_supported': data['entries']['sales']['mappings']=[]
    if mutation=='unspecified': rec['requirements'][1].update(grain_binding='unspecified',grain_requirement_ids=[])
    with pytest.raises(ValueError): mapped(catalog,data,index=5,rec=recalled(catalog,rec))


def test_redundancy_requires_matching_capabilities_on_both_sources(catalog):
    request,_,_,sel=inputs(catalog);rec=recalled(catalog)
    cov=[mapped(catalog,index=i,rec=rec) for i in range(7)]
    monthly=next(e for e in sel['exclusions'] if e['view']==MONTH)
    monthly['refs']=[dict(kind='redundant',requirement_ids=['grain'],selected_view=INV)]
    result=api().materialize_selection(api().SelectionWire.model_validate(sel),rec,cov,request,catalog)
    assert 'redundant' in next(e.reason for e in result.exclusions if e.view==MONTH)
    # A scalar/key subset cannot substantiate the same two-key capability.
    row=next(e for c in cov if c.view==MONTH for e in c.entries if e.requirement_id=='grain')
    row.mappings=row.mappings[:1]
    with pytest.raises(ValueError,match='redundan'):
        api().materialize_selection(api().SelectionWire.model_validate(sel),rec,cov,request,catalog)


def test_nonready_requires_reasons_and_empty_executable_selection(catalog):
    _,_,_,sel=inputs(catalog)
    sel.update(selected_views=[],assignments=[],exclusions=[])
    sel['draft'].update(status='unsupported',strategy=None,tasks=[],integration=None,unsupported_reasons=['無法證明完整支持'])
    assert selected(catalog,sel).draft.status=='unsupported'
    sel['draft']['unsupported_reasons']=[]
    with pytest.raises(ValueError): selected(catalog,sel)


def test_two_distinct_business_grains_and_a_true_independent_scalar(catalog):
    request='各店各商品庫存件數；各訂單淨銷售額；另列全域庫存總件數'
    specs=[('店商品','各店各商品','grain',None,[]),('訂單','各訂單','grain',None,[]),
           ('庫存','庫存件數','metric','linked',['店商品']),('訂單金額','淨銷售額','metric','linked',['訂單']),
           ('全域總數','全域庫存總件數','metric','independent',[])]
    wire={'requirements':[dict(requirement_id=i,start=request.index(q),end=request.index(q)+len(q),kind=k,
        business_object=q,scope_ids=[],grain=q if k=='grain' else '責任明示grain refs',population='契約母體',
        grain_binding=b,grain_requirement_ids=refs) for i,q,k,b,refs in specs]}
    rec=api().materialize_recall(api().RecallWire.model_validate(wire),request,catalog)
    def entry(status='unsupported',column=None,role=None,aggregation=None,rid=None):
        return dict(status=status,mappings=[dict(column=column,role=role,aggregation=aggregation)] if column else [],
            contract_path='/grain/description' if rid in ('店商品','訂單') else '/columns/'+column+'/description' if column else None,
            gaps=[] if status=='supported' else [dict(aspect='mapping',requirement_ids=[rid])])
    for view,grain,metric,key,col in [(INV,'店商品','庫存','store_id','stock_qty'),
                                     ('demo_retail.v_order_summary','訂單','訂單金額','order_id','order_amount')]:
        data={'entries':{i:entry(rid=i) for i,_,_,_,_ in specs}}
        data['entries'][grain]=entry('supported',key,'key',rid=grain)
        if view==INV:
            data['entries'][grain]['mappings'].append(dict(column='product_id',role='key'))
            data['entries']['全域總數']=entry('supported','stock_qty','metric','sum',rid='全域總數')
        data['entries'][metric]=entry('supported',col,'metric','sum',rid=metric)
        policy=next(v.policy for v in catalog.views() if v.name==view)
        result=api().materialize_coverage(api().parse_wire(AIMessage(content=json.dumps(data)),api().coverage_schema(rec)),rec,request,catalog,policy)
        statuses={e.requirement_id:e.status for e in result.entries}
        assert statuses[metric]=='supported'
        assert statuses['訂單' if view==INV else '店商品']=='unsupported'
        if view==INV: assert statuses['全域總數']=='supported'
