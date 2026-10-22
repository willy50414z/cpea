"""Text leaf constraints never replace source or business evidence validation."""
from copy import deepcopy
import json
import sys
from pathlib import Path
import pytest
from langchain_core.messages import AIMessage


def api():
    from evaluations.diagnostics import managed_text_leaf_evidence as m
    return m


def test_pointer_values_escape_unicode_list_and_nontext():
    m=api()
    value={'名/~':{'🧾':['text','  ',None,False,1,{},[]]},'empty':'','summary':'來源'}
    assert m.text_leaf_paths(value)==('/名~1~0/🧾/0','/summary')
    from evaluations.referenced_view_coverage import contract_text
    assert contract_text(value,'/名~1~0/🧾/0')=='text'
    for path in ['/名~1~0/🧾','/名~1~0/🧾/1','/名~1~0/🧾/2','/名~1~0/🧾/3','/empty','/bad']:
        with pytest.raises(ValueError):contract_text(value,path)


def test_manifest_27_cells_and_consistent_provider_human_parse():
    m=api();p=m.load_package()
    assert len(m.cells())==27
    assert p['manifest']['cells']==m.cells()
    assert m.bindings(p)==p['manifest']['bindings']
    for cell in m.cells():
        c=m.prepare(p,cell['sample_id'],cell['seed'])
        assert c['schema_json']==c['schema'].model_json_schema()==c['body']['format']==json.loads(c['messages'][1].content)['response_schema']
        assert c['body']['options']==dict(m.base.MODEL_OPTIONS,seed=cell['seed'])
        assert c['input_tokens']<32768
        assert len(c['cards'])==(1 if cell['sample_id']=='COV-ISO-v1-02' else 8)
        original=m.capability.prepare(p['capability_package'],next(s['base'] for s in p['manifest']['samples'] if s['id']==cell['sample_id']))
        assert c['messages'][0]==original['messages'][0]
        if cell['sample_id'] in m.capability.SAMPLE_IDS:
            assert c['upstream']==original['upstream'] and c['cards']==original['cards']
            old=json.loads(original['messages'][1].content);new=json.loads(c['messages'][1].content)
            old.pop('response_schema');new.pop('response_schema');assert old==new
    assert m.base.MODEL_OPTIONS['seed']==42


@pytest.mark.parametrize('sid',tuple(f'COV-LEAF-v1-{i:02}' for i in range(6,10)))
def test_new_all_rows_and_derived_gaps(sid):
    m=api();p=m.load_package();c=m.prepare(p,sid)
    value=p['oracle']['positive_outputs'][sid]
    assert m.evaluate(c,json.dumps(value,ensure_ascii=False))['status']=='PASS'
    parsed=c['schema'].model_validate(value)
    view=next(v.policy for v in c['catalog'].views() if v.name==c['sample']['view'])
    normalized=c['bound_contract'].materialize_coverage(parsed,c['recall'],c['request'],c['catalog'],view)
    assert len(normalized.entries)==8
    if sid.endswith('06'):
        row=value['entries']['amount/net'];assert row['own_gap'] is True and row['status']=='partial'
        assert row['mappings']==[dict(column='value_total',aggregation='sum',conditions=[])]
    if sid.endswith('07'):
        assert 'stock_status' not in view['columns'] and 'stock_status' not in view['summary']
        assert value['entries']['POP-001']['status']=='supported'
    if sid.endswith('08'):
        assert value['entries']['POP-001']['status']=='partial' and value['entries']['POP-001']['own_gap'] is True
        assert any(json.loads(g)['aspect']=='self' for g in next(e for e in normalized.entries if e.requirement_id=='POP-001').missing_requirements)
    if sid.endswith('09'):assert value['entries']['amount/net']['mappings']==[]


@pytest.mark.parametrize('case',['object','whitespace','missing','number','null','cross_view'])
def test_nontext_and_cross_view_cannot_pass(case):
    m=api();p=m.load_package();c=m.prepare(p,'COV-ISO-v1-01');value=deepcopy(p['oracle']['positive_outputs']['COV-ISO-v1-01'])
    paths=dict(object='/columns/revenue',whitespace='/none',missing='/bogus',number='/version',null=None,cross_view='/columns/lifetime_spend/description')
    value['entries']['MET-003']['contract_path']=paths[case]
    with pytest.raises(ValueError):m.evaluate(c,json.dumps(value,ensure_ascii=False))


@pytest.mark.parametrize('sid',api().capability.SAMPLE_IDS)
def test_original_five_positive_outputs_unchanged(sid):
    m=api();p=m.load_package();c=m.prepare(p,sid)
    assert m.evaluate(c,json.dumps(p['oracle']['positive_outputs'][sid],ensure_ascii=False))['status']=='PASS'


@pytest.mark.parametrize('case',['customer_omit','profit_net','subset_supported','product_only','irrelevant_leaf','bool_own','extra_slot','missing_slot','mapping','unsupported'])
def test_leaf_validity_does_not_rescue_business_or_original_guards(case):
    m=api();p=m.load_package();sid={'customer_omit':'COV-LEAF-v1-06','profit_net':'COV-LEAF-v1-09','subset_supported':'COV-LEAF-v1-08'}.get(case,'COV-CAP-v1-05')
    c=m.prepare(p,sid);value=deepcopy(p['oracle']['positive_outputs'][sid]);rows=value['entries']
    if case=='customer_omit':rows['amount/net'].update(status='unsupported',mappings=[],contract_path=None)
    if case=='profit_net':rows['amount/net'].update(status='partial',mappings=[dict(column='value_total',aggregation='sum',conditions=[])],contract_path='/columns/value_total/description')
    if case=='subset_supported':rows['POP-001'].update(status='supported',own_gap=False)
    if case=='product_only':rows['POP-001']['mappings']=[dict(column='product_id')]
    if case=='irrelevant_leaf':rows['POP-001']['contract_path']='/columns/product_id/description'
    if case=='bool_own':rows['POP-001']['own_gap']=1
    if case=='extra_slot':rows['invented']=deepcopy(rows['POP-001'])
    if case=='missing_slot':rows.pop('POP-001')
    if case=='mapping':rows['MET-001']['mappings'][0]['column']='fake'
    if case=='unsupported':rows['MET-001']['status']='unsupported'
    try:assert m.evaluate(c,json.dumps(value,ensure_ascii=False))['status']=='FAIL'
    except ValueError:pass


@pytest.mark.parametrize('failure',[None,'object','parse','provider','semantic'])
def test_first_errors_replay_and_seed_body(tmp_path,failure):
    m=api();p=m.load_package();c=m.prepare(p,'COV-ISO-v1-01',43)
    value=deepcopy(p['oracle']['positive_outputs'][c['sample']['id']])
    if failure=='object':value['entries']['MET-003']['contract_path']='/columns/revenue'
    if failure=='semantic':value['entries']['MET-003']['own_gap']=True
    def invoke(*args):
        if failure=='provider':raise RuntimeError('offline provider failure')
        return AIMessage(content='{' if failure=='parse' else json.dumps(value,ensure_ascii=False))
    receipt=m.record_sample(tmp_path,c,invoke)
    assert receipt['status']==('FAIL' if failure else 'PASS')
    assert m.replay(tmp_path,p)['result']==receipt['status']
    assert m.base.read_json(tmp_path/'node-body.json')['options']['seed']==43
    assert receipt['seed']==43 and receipt['body_sha256']==m.base.json_digest(c['body'])


@pytest.mark.parametrize('mutation',['body','schema','cards','upstream','tokens','seed'])
def test_context_drift_before_invoke(tmp_path,mutation):
    m=api();p=m.load_package();c=m.prepare(p,'COV-ISO-v1-01');calls=[]
    if mutation=='body':c['body']['options']['seed']=43
    if mutation=='schema':c['schema_json']={}
    if mutation=='cards':c['cards']=[]
    if mutation=='upstream':c['upstream']={}
    if mutation=='tokens':c['input_tokens']=32768
    if mutation=='seed':c['seed']=43
    with pytest.raises(ValueError):m.record_sample(tmp_path,c,lambda *a:calls.append(a))
    assert calls==[]


@pytest.mark.parametrize('seed',[42,43,44])
def test_actual_controller_body_explicit_seed_without_POST(tmp_path,monkeypatch,seed):
    m=api();p=m.load_package();c=m.prepare(p,'COV-ISO-v1-01',seed)
    response=tmp_path/'response.json';m.base.write_json(response,dict(model=m.base.MODEL,done=True,done_reason='stop',message=dict(content='{}'),prompt_eval_count=3,eval_count=2))
    captures=[];saved={}
    class Completed:
        returncode=0
        stdout=json.dumps(dict(result='ok',request_id='fake',response_path=str(response),calls_charged=1,automatic_retries=0))
    def fake(command,**kwargs):
        payload=m.base.read_json(Path(command[command.index('--file')+1]));m.base.write_json(tmp_path/'fake.request.json',payload)
        captures.append((command,kwargs,payload))
        return Completed()
    monkeypatch.setattr(m.subprocess,'run',fake)
    invoke=m.SeedManagedInvoke(tmp_path,'ticket','case',saved.__setitem__,seed=seed)
    output=invoke('node',c['messages'],c['schema'])
    assert len(captures)==1 and captures[0][2]==c['body']
    assert 'timeout' not in captures[0][1] and '--retry-of' not in captures[0][0]
    assert output.response_metadata['text_leaf_transport']==dict(seed=seed,body_sha256=m.base.json_digest(c['body']))
    assert saved['node-managed.json']['result']=='ok' and m.base.MODEL_OPTIONS['seed']==42


@pytest.mark.parametrize('failure',[None,'scope','typed'])
def test_original_full_pipeline_bound_contract(tmp_path,failure):
    m=api();sys.path.insert(0,str(m.ROOT/'tests/unit'))
    from test_kind_mapping_managed_contract import inputs
    catalog=m.base.SchemaCatalog(m.ROOT/'projects/retail');request,rec,maps,sel=inputs(catalog)
    if failure=='scope':
        metric=next(r for r in rec['requirements'] if r['kind']=='metric' and r['scope_ids'])
        complete=next(v for v in maps if v['entries'][metric['requirement_id']]['status']=='supported')
        complete['entries'][metric['scope_ids'][0]].update(status='unsupported',own_gap=True,mappings=[],contract_path=None)
    if failure=='typed':sel['draft']['tasks'][0].pop('filters')
    values=iter([rec,*maps,sel]);calls=[]
    def invoke(name,*args):calls.append(name);return AIMessage(content=json.dumps(next(values),ensure_ascii=False))
    bound=m.bind_catalog(catalog);case=m.runner.diagnostic_case(catalog,request)
    result=m.runner.record_run(tmp_path,catalog,case,invoke,contract=bound)
    assert bool(result['stopped'])==bool(failure)
    replay=m.runner.replay(tmp_path,catalog,case,contract=bound)
    assert replay['stopped']==result['stopped'] and replay['raw_replays']==len(calls)
    if not failure:assert len(calls)==9 and len(m.base.read_json(tmp_path/'response.json')['prepared_requests'])==2


def test_missing_review_real_open_author_and_audit_rejected():
    m=api();p=m.load_package();c=m.prepare(p,'COV-ISO-v1-01')
    with pytest.raises(ValueError):m.preflight(p,[c],None)
    review=dict(schema_version=1,verdict='ACCEPT',reviewer_role='fresh_text_leaf_evidence_semantics',ticket='fake',author_ticket=m.AUTHOR_TICKET,manifest_sha256=m.base.digest(m.DEFAULT_MANIFEST),bindings=p['manifest']['bindings'])
    with pytest.raises(ValueError):m.preflight(p,[c],review)


@pytest.mark.parametrize('seed,proofs,want',[(42,(),True),(43,(),False),(44,(),False),(42,('fake',),False)])
def test_block_gates_never_draw_later_seed_after_failure(seed,proofs,want):
    m=api();p=m.load_package()
    if want:assert m.block_gate(p,seed,proofs)['seed']==seed
    else:
        with pytest.raises(ValueError):m.block_gate(p,seed,proofs)


@pytest.mark.parametrize('mutation',['open','missing','node','round','producer','fail','same_platform','evidence'])
@pytest.mark.parametrize('who',['author','reviewer'])
def test_new_provenance_cannot_be_forged(tmp_path,mutation,who):
    m=api();p=m.load_package();review=dict(ticket='synthetic-review-only')
    path=tmp_path/'review.json';m.base.write_json(path,review)
    loop=dict(tickets={},rounds=[])
    for role,ticket,node,n,platform in [('author',m.AUTHOR_TICKET,'text_leaf_evidence_contract',24,'/root/loop_worker_text_leaf_contract'),
            ('reviewer',review['ticket'],'text_leaf_evidence_semantics',25,'synthetic-distinct-reviewer')]:
        evidence=[dict(path=m.DEFAULT_MANIFEST.relative_to(m.ROOT).as_posix(),sha256=m.base.digest(m.DEFAULT_MANIFEST))] if role=='author' else [dict(path=str(path),sha256=m.base.digest(path))]
        loop['tickets'][ticket]=dict(role='worker',node=node,round=n,platform_id=platform,closed=True)
        loop['rounds'].append(dict(node=node,round=n,producer=platform,result='PASS',evidence=evidence))
    assert len(m.roles(p,review,loop))==2
    ticket=m.AUTHOR_TICKET if who=='author' else review['ticket'];item=loop['tickets'][ticket];completed=loop['rounds'][0 if who=='author' else 1]
    if mutation=='open':item['closed']=False
    if mutation=='missing':loop['tickets'].pop(ticket)
    if mutation=='node':item['node']='other'
    if mutation=='round':item['round']=99
    if mutation=='producer':completed['producer']='other'
    if mutation=='fail':completed['result']='FAIL'
    if mutation=='same_platform':item['platform_id']='same';completed['producer']='same'
    if mutation=='evidence':completed['evidence']=[]
    with pytest.raises(ValueError):m.roles(p,review,loop)


def test_pointer_duplicate_keys_and_readonly_bound_contract():
    from dataclasses import FrozenInstanceError
    m=api();p=m.load_package();c=m.prepare(p,'COV-ISO-v1-01')
    with pytest.raises(FrozenInstanceError):c['bound_contract'].fingerprint='changed'
    with pytest.raises(ValueError):m.parse_wire(AIMessage(content='{"entries":{},"entries":{}}'),c['schema'])
