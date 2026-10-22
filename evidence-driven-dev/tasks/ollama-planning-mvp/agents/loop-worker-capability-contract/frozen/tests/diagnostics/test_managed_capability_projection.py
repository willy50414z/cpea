"""Lossless capability cards and narrowly bounded scope AND equivalence."""
from copy import deepcopy
import importlib
import json
import pytest


def api():
    return importlib.import_module('evaluations.diagnostics.managed_capability_projection')


def test_lossless_dynamic_cards_all_kinds_unknown_values():
    m=api()
    rows=[dict(requirement_id='動態/'+str(i), kind=k, quote='原文', business_object='對象', grain='粒度',
        population='會員自身限制',scope_ids=['任意scope'], grain_requirement_ids=['任意grain'],
        grain_binding='linked', extension={'unknown':[None,False,{'原':'值'}]})
        for i,k in enumerate(['grain','population','metric','filter','key','attribute','metadata'])]
    before=deepcopy(rows);cards=m.project_cards(rows)
    assert m.restore_cards(cards,rows)==rows==before
    for row,card in zip(rows,cards):
        assert card['identity']=={'requirement_id':row['requirement_id']}
        assert ('grain' in card['own_target'])==(row['kind']=='grain')
        assert ('population' in card['own_target'])==(row['kind']=='population')
        assert set(card)=={'identity','own_target','binding_context'}


@pytest.mark.parametrize('mutation',['duplicate','missing','invented'])
def test_restore_rejects_loss_or_invention(mutation):
    m=api();rows=[dict(requirement_id='X',kind='metric',quote='q',business_object='b')];cards=m.project_cards(rows)
    if mutation=='duplicate':cards[0]['own_target']['requirement_id']='X'
    if mutation=='missing':cards[0]['own_target'].pop('quote')
    if mutation=='invented':cards[0]['binding_context']['answer']='supported'
    with pytest.raises(ValueError):m.restore_cards(cards,rows)


def package():
    m=api();return m,m.load_package()


def positive(m,p,sid='COV-ISO-v1-01'):
    return deepcopy(p['oracle']['positive_outputs'][sid])


def test_inputs_only_project_coverage_and_keep_noncoverage_policy():
    m,p=package()
    assert [s['id'] for s in p['manifest']['samples']]==m.SAMPLE_IDS
    assert m.bindings(p)==p['manifest']['bindings']
    for sid in m.SAMPLE_IDS:
        c=m.prepare(p,sid);payload=json.loads(c['messages'][1].content)
        rows=[r.model_dump() for r in c['recall'].requirements]
        assert m.restore_cards(payload['requirement_cards'],rows)==rows
        assert 'requirements' not in payload
        old=m.rebound.prepare(p['legacy'],sid if sid.startswith('COV-ISO') else 'COV-ISO-v1-01')
        op=json.loads(old['messages'][1].content)
        assert payload['request']==op['request']
        assert payload['response_schema']==op['response_schema']==c['schema_json']
        assert {k:v for k,v in c['body'].items() if k!='messages'}=={k:v for k,v in old['body'].items() if k!='messages'}
        assert c['upstream']==old['upstream']
        assert len(c['cards'])==(1 if sid=='COV-ISO-v1-02' else 8)
    for phase,context in [('recall',dict(views=[])),('selection',dict(requirements=[],coverages=[],views=[],missing_policy_options=[]))]:
        schema=m.RecallWire if phase=='recall' else m.SelectionWire
        assert m.messages(phase,schema,'dynamic',**context)==m.policy.messages(phase,schema,'dynamic',**context)
    assert m.materialize_selection is m.policy.materialize_selection
    assert m.rebound.bindings(p['legacy'])==p['legacy']['manifest']['bindings']


@pytest.mark.parametrize('sid',api().SAMPLE_IDS)
def test_five_independent_positive_controls_preserve_semantics(sid):
    m,p=package();c=m.prepare(p,sid);raw=json.dumps(positive(m,p,sid),ensure_ascii=False)
    result=m.evaluate(c,raw)
    assert result['status']=='PASS' and result['legacy_findings']==[]
    rows=positive(m,p,sid)['entries']
    if sid=='COV-ISO-v1-01':
        assert rows['GRN-001']['mappings']==[{'column':'store_id'}]
        assert rows['GRN-001']['own_gap'] is True
        assert rows['MET-003']['own_gap'] is False
    if sid=='COV-CAP-v1-04':
        assert rows['GRN-001']['mappings']==[]
        assert rows['MET-003']['mappings'][0]['column']=='lifetime_spend'
        assert rows['MET-003']['own_gap'] is True
    if sid=='COV-CAP-v1-05':
        assert rows['GRN-001']['status']=='supported'
        assert rows['MET-001']['status']=='supported'
        assert rows['META-001']['status']=='supported'
        assert rows['POP-001']['status']=='supported'


def scope_data(m,p):
    c=m.prepare(p,'COV-ISO-v1-01');value=positive(m,p)
    value['entries']['MET-003']['mappings'][0]['conditions']=deepcopy(value['entries']['FILT-001']['mappings'])
    return c,value


@pytest.mark.parametrize('case,want',[(s,True) for s in ['empty','full','reverse','duplicate','inclusive']]+
    [(s,False) for s in ['half','month','column','operator','sum','extra','undeclared','cross_view','missing','unsupported','wrong_filter','expected_required']])
def test_bounded_scope_AND_delta_controls(case,want):
    m,p=package();c,value=scope_data(m,p);rows=value['entries'];metric=rows['MET-003']['mappings'][0]
    if case=='empty':metric['conditions']=[]
    if case=='reverse':metric['conditions'].reverse()
    if case=='duplicate':metric['conditions']*=2
    if case=='inclusive':
        rows['FILT-001']['mappings'][1].update(operator='<=',value='2026-09-30')
        metric['conditions']=deepcopy(rows['FILT-001']['mappings'])
    if case=='half':metric['conditions'].pop()
    if case=='month':metric['conditions'][0]['value']='2026-08-01'
    if case=='column':metric['conditions'][0]['column']='store_id'
    if case=='operator':metric['conditions'][0]['operator']='>'
    if case=='sum':metric['aggregation']='max'
    if case=='extra':metric['conditions'].append(dict(column='store_id',operator='=',value='north'))
    if case=='undeclared':
        c['recall']=deepcopy(c['recall'])
        next(r for r in c['recall'].requirements if r.requirement_id=='MET-003').scope_ids=['FILT-002']
    if case=='cross_view':
        # These predicates belong to daily_sales; inventory has no such standalone scope.
        c=m.prepare(p,'COV-CAP-v1-05');value=positive(m,p,'COV-CAP-v1-05')
        value['entries']['MET-001']['mappings'][0]['conditions']=deepcopy(metric['conditions'])
    if case=='missing':rows['FILT-001'].update(status='unsupported',own_gap=True,mappings=[],contract_path=None)
    if case=='unsupported':rows['FILT-001'].update(status='partial',own_gap=True)
    if case=='wrong_filter':rows['FILT-001']['mappings'][0]['value']='2026-08-01'
    if case=='expected_required':
        c['package']=deepcopy(c['package'])
        c['package']['oracle']['positive_outputs'][c['sample']['id']]['entries']['MET-003']['mappings'][0]['conditions']=[dict(column='store_id',operator='=',value='required')]
    before=deepcopy(value)
    try:result=m.evaluate(c,json.dumps(value,ensure_ascii=False));got=result['status']=='PASS'
    except ValueError:got=False
    assert got==want
    assert value==before
    if want and case!='empty':
        assert result['legacy_findings'] and result['accepted_scope_AND_equivalences']
        assert not result['other_findings']


@pytest.mark.parametrize('case',['daily_key','daily_own','unrelated_key','membership','inventory_stock','metadata','population'])
def test_business_negative_controls_never_rescued_by_AND(case):
    m,p=package();sid='COV-CAP-v1-04' if case in ['unrelated_key','membership'] else 'COV-CAP-v1-05' if case in ['inventory_stock','metadata','population'] else 'COV-ISO-v1-01'
    c=m.prepare(p,sid);v=positive(m,p,sid);rows=v['entries']
    if case=='daily_key':rows['GRN-001'].update(status='unsupported',mappings=[])
    if case=='daily_own':rows['MET-003']['own_gap']=True
    if case=='unrelated_key':rows['GRN-001'].update(status='partial',mappings=[dict(column='customer_id')])
    if case=='membership':rows['MET-003']['own_gap']=False
    if case=='inventory_stock':rows['MET-001']['mappings'][0]['column']='inventory_cost_value'
    if case=='metadata':rows['META-001']['mappings'][0]['column']='stock_qty'
    if case=='population':rows['POP-001'].update(status='unsupported',own_gap=True,mappings=[],contract_path=None)
    try:assert m.evaluate(c,json.dumps(v,ensure_ascii=False))['status']=='FAIL'
    except ValueError:pass


@pytest.mark.parametrize('failure',[None,'scope','typed','parse','provider','context'])
def test_record_and_replay_preserve_first_errors(tmp_path,failure):
    from langchain_core.messages import AIMessage
    m,p=package();c,v=scope_data(m,p)
    if failure=='scope':v['entries']['MET-003']['mappings'][0]['conditions'].pop()
    if failure=='typed':v['entries']['MET-003'].pop('own_gap')
    raw='not json' if failure=='parse' else json.dumps(v,ensure_ascii=False)
    calls=[]
    def invoke(*a):
        calls.append(a)
        if failure=='provider':raise OSError('offline failure')
        return AIMessage(content=raw)
    folder=tmp_path/'sample';r=m.record_sample(folder,c,invoke,context_window=1 if failure=='context' else 32768)
    assert r['status']==('PASS' if failure is None else 'FAIL')
    assert len(calls)==(0 if failure=='context' else 1)
    result=m.replay(folder,p)
    assert result['result']==r['status'] and result['replay_verification']=='PASS'
    if failure is None:
        assert m.base.read_json(folder/'run.json')['stopped']['error']=='fixed diagnostic semantic checks failed'
        assert r['decision']['legacy_findings'] and not r['decision']['other_findings']
    with pytest.raises(ValueError,match='empty'):m.record_sample(folder,c,invoke)


def test_interruption_receipt_cannot_promote(tmp_path):
    m,p=package();c=m.prepare(p,m.SAMPLE_IDS[0])
    def invoke(*a):raise KeyboardInterrupt('offline interruption')
    with pytest.raises(KeyboardInterrupt):m.record_sample(tmp_path/'sample',c,invoke)
    with pytest.raises(ValueError,match='interrupted'):m.replay(tmp_path/'sample',p)


@pytest.mark.parametrize('mutation',['body','schema','upstream','cards','tokens','oracle'])
def test_context_changes_reject_before_invoke(tmp_path,mutation):
    m,p=package();c=m.prepare(p,m.SAMPLE_IDS[0]);calls=[]
    if mutation=='body':c['body']['think']=False
    if mutation=='schema':c['schema_json']['additionalProperties']=True
    if mutation=='upstream':c['upstream']['recall']['requirements'].pop()
    if mutation=='cards':c['cards'][0]['identity']['requirement_id']='forged'
    if mutation=='tokens':c['input_tokens']+=1
    if mutation=='oracle':c['package']['oracle']['positive_outputs'][m.SAMPLE_IDS[0]]['entries'].clear()
    with pytest.raises(ValueError):m.record_sample(tmp_path/'sample',c,lambda *a:calls.append(a))
    assert calls==[]


def test_real_open_author_and_no_review_reject_before_network(tmp_path):
    m,p=package();c=m.prepare(p,m.SAMPLE_IDS[0])
    review=dict(schema_version=1,verdict='ACCEPT',reviewer_role='fresh_capability_projection_semantics',ticket='nonexistent',
        author_ticket=m.AUTHOR_TICKET,manifest_sha256=m.base.digest(m.DEFAULT_MANIFEST),bindings=p['manifest']['bindings'])
    with pytest.raises(ValueError,match='provenance'):m.preflight(p,[c],review)
    with pytest.raises(ValueError,match='review'):m.main(['--execute','--ticket','unused'])
    with pytest.raises(ValueError,match='active'):m._execution_guard(m.AUTHOR_TICKET)


@pytest.mark.parametrize('failure',[None,'scope','typed'])
def test_full_nine_contract_and_original_guards(tmp_path,failure):
    import sys
    from langchain_core.messages import AIMessage
    from evaluations import managed_three_stage_runner as runner
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    m,p=package();sys.path.insert(0,str(m.ROOT/'tests/unit'))
    from test_kind_mapping_managed_contract import inputs
    catalog=SchemaCatalog(m.ROOT/'projects/retail');request,rec,maps,sel=inputs(catalog)
    if failure=='scope':
        # A grain-bound metric cannot silently drop its declared grain mapping.
        metric=next(r for r in rec['requirements'] if r['kind']=='metric' and r['scope_ids'])
        complete=next(v for v in maps if v['entries'][metric['requirement_id']]['status']=='supported')
        scope=metric['scope_ids'][0];complete['entries'][scope].update(status='unsupported',own_gap=True,mappings=[],contract_path=None)
    if failure=='typed':sel['draft']['tasks'][0].pop('filters')
    values=iter([rec,*maps,sel]);calls=[]
    def invoke(name,*a):calls.append(name);return AIMessage(content=json.dumps(next(values),ensure_ascii=False))
    case=runner.diagnostic_case(catalog,request);meta=runner.record_run(tmp_path,catalog,case,invoke,contract=m)
    assert bool(meta['stopped'])==bool(failure)
    result=runner.replay(tmp_path,catalog,case,contract=m)
    assert result['stopped']==meta['stopped'] and result['raw_replays']==len(calls)
    if failure is None:
        assert len(calls)==9 and len(m.base.read_json(tmp_path/'response.json')['prepared_requests'])==2
    else:assert not (tmp_path/'response.json').exists()


@pytest.mark.parametrize('who',['author','reviewer'])
@pytest.mark.parametrize('mutation',['open','missing','node','round','producer','fail','same_platform','evidence'])
def test_new_roles_reject_incomplete_or_forged_closed_provenance(tmp_path,who,mutation):
    m,p=package();loop=deepcopy(m._loop());ticket='offline-control-review'
    review=dict(schema_version=1,verdict='ACCEPT',reviewer_role='fresh_capability_projection_semantics',ticket=ticket,
        author_ticket=m.AUTHOR_TICKET,manifest_sha256=m.base.digest(m.DEFAULT_MANIFEST),bindings=p['manifest']['bindings'])
    proof=tmp_path/'offline-review.json';m.base.write_json(proof,review)
    for t,node,number,platform in [(m.AUTHOR_TICKET,'capability_projection_contract',21,'/root/loop_worker_capability_contract'),
            (ticket,'capability_projection_semantics',22,'/offline-fresh-reviewer')]:
        loop['tickets'][t]=dict(role='worker',node=node,round=number,platform_id=platform,closed=True)
        loop['rounds'].append(dict(round=number,node=node,producer=platform,result='PASS',evidence=[dict(
            path=m.DEFAULT_MANIFEST.relative_to(m.ROOT).as_posix(),sha256=m.base.digest(m.DEFAULT_MANIFEST))] if number==21
            else [dict(path=str(proof),sha256=m.base.digest(proof))]))
    # Only the pure provenance checker uses this synthetic control; no HTTP authorization is issued.
    assert len(m._roles(p,review,loop))==2
    t=m.AUTHOR_TICKET if who=='author' else ticket;item=loop['tickets'][t]
    completion=next(r for r in loop['rounds'] if r['round']==item['round'])
    if mutation=='open':item['closed']=False
    if mutation=='missing':del loop['tickets'][t]
    if mutation=='node':item['node']='root'
    if mutation=='round':item['round']+=1
    if mutation=='producer':completion['producer']='/forged'
    if mutation=='fail':completion['result']='FAIL'
    if mutation=='same_platform':
        other=loop['tickets'][ticket if who=='author' else m.AUTHOR_TICKET]
        item['platform_id']=other['platform_id'];completion['producer']=other['platform_id']
    if mutation=='evidence':completion['evidence']=[]
    with pytest.raises(ValueError):m._roles(p,review,loop)


@pytest.mark.parametrize('mutation',['node','closed','audit_due','no_audit','incomplete_audit','status','round',None])
def test_execution_requires_true_active_node_and_19_21_audit(tmp_path,mutation):
    m=api();node='natural_capability_projection_coverage'
    loop=dict(status='RUNNING',audit_due=False,needs_research=False,active=dict(node=node,round=23),
        tickets={'control':dict(role='worker',node=node,round=23,platform_id='/offline',closed=False)},
        reviews=[dict(verdict='CONTINUE',reviewed_rounds=[19,20,21])])
    if mutation=='node':loop['tickets']['control']['node']='root'
    if mutation=='closed':loop['tickets']['control']['closed']=True
    if mutation=='audit_due':loop['audit_due']=True
    if mutation=='no_audit':loop['reviews']=[]
    if mutation=='incomplete_audit':loop['reviews'][0]['reviewed_rounds']=[21]
    if mutation=='status':loop['status']='NEEDS_USER'
    if mutation=='round':loop['tickets']['control']['round']=22
    path=tmp_path/'task.md';path.write_text('---\n'+json.dumps(dict(plan=dict(edd_loop=loop)))+'\n---\n',encoding='utf-8')
    if mutation is None:m._execution_guard('control',task_path=path)
    else:
        with pytest.raises(ValueError,match='active'):m._execution_guard('control',task_path=path)


def test_receipt_drift_after_raw_is_fatal_and_frozen_sources_are_complete(tmp_path):
    from langchain_core.messages import AIMessage
    m,p=package();c=m.prepare(p,m.SAMPLE_IDS[0]);value=positive(m,p)
    folder=tmp_path/'receipt-drift'
    def drift(*a):
        receipt=m._read_receipt(folder);receipt['version']='forged';m._save_receipt(folder,receipt)
        return AIMessage(content=json.dumps(value,ensure_ascii=False))
    receipt=m.record_sample(folder,c,drift)
    assert receipt['status']=='FAIL' and (folder/'node-call.json').is_file()
    assert m.base.read_json(folder/'run.json')['stopped'] is None
    assert m.replay(folder,p)['result']=='FAIL'
    frozen=m.freeze_sources(tmp_path/'frozen',p)
    for name in [*m.ADDITIONAL_SOURCES,*m.REFERENCE_PATHS,*m.rebound.source_paths(),
            m.DEFAULT_MANIFEST.relative_to(m.ROOT).as_posix()]:
        assert m.base.digest(frozen/name)==m.base.digest(m.ROOT/name)
    for name,value in p['manifest']['bindings']['inputs'].items():
        assert m.base.digest(frozen/m.DEFAULT_MANIFEST.parent.relative_to(m.ROOT)/name)==value
