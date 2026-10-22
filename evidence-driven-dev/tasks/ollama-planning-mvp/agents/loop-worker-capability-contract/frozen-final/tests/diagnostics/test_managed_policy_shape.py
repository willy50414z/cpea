"""Policy shape controls use immutable raw and the original strict engines."""
from copy import deepcopy
import importlib
import importlib.util
import json
import sys
from pathlib import Path

from langchain_core.messages import AIMessage
import pytest

from evaluations import managed_node_diagnostics as base
from evaluations.diagnostics import managed_node_diagnostics_rebound as rebound
from evaluations.three_stage_view_selection import MISSING_POLICIES

sys.path.insert(0,str(base.ROOT / 'tests/unit'))

RAW = base.ROOT / 'evidence-driven-dev/tasks/ollama-planning-mvp/.local/kind-isolation-v2-rebind-1-20261021T215758Z-5bbdea/SEL-ISO-v1-01/node-call.json'


def api():
    assert importlib.util.find_spec('evaluations.diagnostics.managed_policy_shape'), 'policy shape candidate missing'
    return importlib.import_module('evaluations.diagnostics.managed_policy_shape')


def original():
    return json.loads(base.read_json(RAW)['response'])


@pytest.mark.parametrize('case,want', [('default', True), ('null', True), ('empty', False),
    ('nested', True), ('aggregate', False), ('wrong_child', False), ('wrong_keys', False),
    ('zero', False), ('metadata', False), ('renamed', True), ('second_child', False)])
def test_policy_shape_requires_actual_nest_for_every_child(case, want):
    mod = api(); value = original(); integration = value['draft']['integration']
    integration['missing_data_policy'] = MISSING_POLICIES[0 if case == 'default' else 1 if case == 'null' else 2]
    nest = dict(task_id='task_sales', kind='nest', keys=['store_id','product_id'], description='collect child rows')
    if case in ['nested','wrong_child','wrong_keys','renamed','second_child']:
        integration['preparation'].append(nest)
    if case == 'wrong_child': nest['task_id'] = 'task_inv'
    if case == 'wrong_keys': nest['keys'] = ['store_id']
    if case == 'zero': integration['missing_data_policy'] = '未匹配的折扣金額與淨銷售額補零。'
    if case == 'metadata': value['draft']['tasks'][1]['metadata_collections'] = ['net_sales']
    if case == 'renamed':
        integration['edges'][0].update(left_task='母',right_task='子',preserve_task='母',left_keys=['店','貨'],right_keys=['店','貨'])
        nest.update(task_id='子',keys=['店','貨'])
    if case == 'second_child': integration['edges'].append(dict(integration['edges'][0],right_task='other'))
    before = deepcopy(value)
    assert (not mod.policy_findings(value['draft'])) == want
    assert value == before


@pytest.mark.parametrize('policy_index,want', [(0,'PASS'),(1,'PASS'),(2,'FAIL')])
def test_literal_migration_keeps_original_findings_and_new_shape(policy_index,want):
    mod=api(); context=mod.prepare(mod.load_package()); value=original()
    value['draft']['integration']['missing_data_policy']=MISSING_POLICIES[policy_index]
    result=mod.evaluate(context,json.dumps(value,ensure_ascii=False))
    assert result['status']==want
    assert result['legacy_findings']==([] if policy_index==0 else [dict(aspect='no unproven zero fill',actual=MISSING_POLICIES[policy_index])])
    assert len(result['response']['prepared_requests'])==2
    if policy_index==2: assert result['policy_findings']


@pytest.mark.parametrize('failure',['typed','inner','zero','business','semantic'])
def test_original_guards_and_other_semantic_failures_remain_fatal(failure):
    mod=api(); context=mod.prepare(mod.load_package()); value=original()
    value['draft']['integration']['missing_data_policy']=MISSING_POLICIES[1]
    if failure=='typed': value['draft']['tasks'][0].pop('filters')
    if failure=='inner': value['draft']['integration']['edges'][0].update(mode='inner',preserve_task=None)
    if failure=='zero': value['draft']['integration']['missing_data_policy']='補零'
    if failure=='business': value['draft']['tasks'][1]['metrics']['discount_amount']='max'
    if failure=='semantic': value['draft']['integration']['edges'][0]['cardinality']='many_to_one'
    if failure=='semantic': assert mod.evaluate(context,json.dumps(value,ensure_ascii=False))['status']=='FAIL'
    else:
        with pytest.raises(ValueError): mod.evaluate(context,json.dumps(value,ensure_ascii=False))


def test_new_input_changes_only_selection_system_suffix():
    mod=api(); package=mod.load_package(); context=mod.prepare(package)
    old=rebound.prepare(rebound.load_package(),'SEL-ISO-v1-01')
    assert context['body']['messages'][1:]==old['body']['messages'][1:]
    assert context['body']['messages'][0]['content']==old['body']['messages'][0]['content']+mod.SELECTION_SUFFIX
    assert {k:v for k,v in context['body'].items() if k!='messages'}=={k:v for k,v in old['body'].items() if k!='messages'}
    assert context['upstream']==old['upstream']
    assert rebound.bindings(rebound.load_package())==rebound.load_package()['manifest']['bindings']
    assert mod.bindings(package)==package['manifest']['bindings']


@pytest.mark.parametrize('failure',[None,'null','shape','typed','semantic','parse','provider','provider_semantic','context'])
def test_thin_record_keeps_legacy_and_new_first_errors_and_replays(tmp_path,failure):
    mod=api(); package=mod.load_package(); context=mod.prepare(package); value=original()
    value['draft']['integration']['missing_data_policy']=MISSING_POLICIES[1 if failure=='null' else 0]
    if failure=='shape': value['draft']['integration']['missing_data_policy']=MISSING_POLICIES[2]
    if failure=='typed': value['draft']['tasks'][0].pop('filters')
    if failure=='semantic': value['draft']['integration']['edges'][0]['cardinality']='many_to_one'
    raw='not json' if failure=='parse' else json.dumps(value,ensure_ascii=False)
    calls=[]
    def invoke(*args):
        calls.append(args)
        if failure=='provider': raise OSError('offline transport lost')
        if failure=='provider_semantic': raise ValueError('fixed diagnostic semantic checks failed')
        return AIMessage(content=raw)
    folder=tmp_path/'sample'
    receipt=mod.record_sample(folder,context,invoke,context_window=1 if failure=='context' else 32768)
    assert receipt['status']==('PASS' if failure in [None,'null'] else 'FAIL')
    assert len(calls)==(0 if failure=='context' else 1)
    if failure=='null':
        assert base.read_json(folder/'run.json')['stopped']['error']=='fixed diagnostic semantic checks failed'
        assert receipt['decision']['legacy_findings'] and not receipt['decision']['policy_findings']
    result=mod.replay(folder,package)
    assert result['result']==receipt['status'] and result['replay_verification']=='PASS'
    assert (folder/'node-call.json').exists()==(failure not in ['provider','provider_semantic','context'])
    with pytest.raises(ValueError,match='empty'): mod.record_sample(folder,context,invoke)


def test_interruption_and_outer_drift_never_promote_inner_pass(tmp_path):
    mod=api();package=mod.load_package();context=mod.prepare(package)
    def interrupt(*args): raise KeyboardInterrupt('offline interruption')
    folder=tmp_path/'interrupted'
    with pytest.raises(KeyboardInterrupt): mod.record_sample(folder,context,interrupt)
    with pytest.raises(ValueError,match='interrupted'): mod.replay(folder,package)
    folder=tmp_path/'drift';value=original();value['draft']['integration']['missing_data_policy']=MISSING_POLICIES[0]
    def drift(*args):
        receipt=base.read_json(mod.receipt_path(folder));receipt['version']='forged'
        base.write_json(mod.receipt_path(folder),receipt)
        return AIMessage(content=json.dumps(value,ensure_ascii=False))
    receipt=mod.record_sample(folder,context,drift)
    assert receipt['status']=='FAIL' and base.read_json(folder/'run.json')['stopped'] is None
    assert (folder/'node-call.json').exists()
    assert mod.replay(folder,package)['result']=='FAIL'


@pytest.mark.parametrize('failure',[None,'shape','typed'])
def test_full_natural_runner_contract_reuses_nine_stages_and_prepared(tmp_path,failure):
    from evaluations import managed_three_stage_runner as runner
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    from test_kind_mapping_managed_contract import inputs
    mod=api();catalog=SchemaCatalog('projects/retail');request,rec,maps,sel=inputs(catalog)
    if failure=='shape':sel['draft']['integration']['missing_data_policy']=MISSING_POLICIES[2]
    if failure=='typed':sel['draft']['tasks'][0].pop('filters')
    responses=iter([rec,*maps,sel]);calls=[]
    def invoke(name,messages,schema):
        calls.append(name)
        return AIMessage(content=json.dumps(next(responses),ensure_ascii=False))
    case=runner.diagnostic_case(catalog,request)
    meta=runner.record_run(tmp_path,catalog,case,invoke,contract=mod)
    assert bool(meta['stopped'])==bool(failure)
    assert calls==['recall',*[f'map-{i:02}' for i in range(1,8)],'selection']
    assert runner.replay(tmp_path,catalog,case,contract=mod)['stopped']==meta['stopped']
    if failure is None: assert len(base.read_json(tmp_path/'response.json')['prepared_requests'])==2
    else: assert not (tmp_path/'response.json').exists() and (tmp_path/'selection-call.json').exists()


def synthetic_authorization(mod,package,tmp_path):
    # A temporary Task models provenance; the actual Task is never modified.
    actual=json.loads((base.ROOT/base.TASK/'task.md').read_text(encoding='utf-8').split('---',2)[1])['plan']['edd_loop']
    loop=deepcopy(actual)
    review=dict(schema_version=1,verdict='ACCEPT',reviewer_role='fresh_policy_shape_semantics',
        ticket='synthetic-policy-reviewer',author_ticket=mod.AUTHOR_TICKET,
        manifest_sha256=base.digest(package['manifest_path']),bindings=deepcopy(package['manifest']['bindings']))
    for ticket,node,number,platform in [(mod.AUTHOR_TICKET,'kind_policy_shape_contract',16,'/policy-author'),
            (review['ticket'],'kind_policy_shape_semantics',17,'/fresh-policy-reviewer')]:
        loop['tickets'][ticket]=dict(role='worker',node=node,round=number,platform_id=platform,closed=True)
        loop['rounds']=[r for r in loop['rounds'] if r.get('round')!=number]
        loop['rounds'].append(dict(round=number,node=node,producer=platform,result='PASS',evidence=[dict(
            path=mod.DEFAULT_MANIFEST.relative_to(base.ROOT).as_posix(),sha256=base.digest(package['manifest_path']))]))
    proof=tmp_path/'review.json';base.write_json(proof,review)
    loop['rounds'][-1]['evidence']=[dict(path=str(proof),sha256=base.digest(proof))]
    path=tmp_path/'task.md';save_task(path,loop)
    return review,loop,path


def save_task(path,loop):
    path.write_text('---\n'+json.dumps(dict(plan=dict(edd_loop=loop)),ensure_ascii=False)+'\n---\n',encoding='utf-8')


@pytest.mark.parametrize('who',['author','reviewer'])
@pytest.mark.parametrize('mutation',['open','missing','node','round','producer','fail','same_platform','evidence'])
def test_author_and_fresh_reviewer_must_really_complete(tmp_path,who,mutation):
    mod=api();package=mod.load_package();context=mod.prepare(package)
    review,loop,path=synthetic_authorization(mod,package,tmp_path)
    assert mod.preflight(package,context,review,task_path=path)['result']=='PASS'
    ticket=mod.AUTHOR_TICKET if who=='author' else review['ticket'];item=loop['tickets'][ticket]
    completion=next(r for r in loop['rounds'] if r['round']==item['round'])
    if mutation=='open':item['closed']=False
    if mutation=='missing':del loop['tickets'][ticket]
    if mutation=='node':item['node']='root'
    if mutation=='round':item['round']+=1
    if mutation=='producer':completion['producer']='/forged'
    if mutation=='fail':completion['result']='FAIL'
    if mutation=='evidence':completion['evidence']=[]
    if mutation=='same_platform':
        item['platform_id']='/same';completion['producer']='/same'
        other=loop['tickets'][review['ticket'] if who=='author' else mod.AUTHOR_TICKET]
        old=other['platform_id'];other['platform_id']='/same'
        for r in loop['rounds']:
            if r['producer']==old:r['producer']='/same'
    save_task(path,loop)
    with pytest.raises(ValueError,match='provenance|completion'):mod.preflight(package,context,review,task_path=path)


@pytest.mark.parametrize('mutation',['review','manifest','binding','body','schema','messages','upstream','context','oracle'])
def test_full_binding_and_context_drift_rejected_before_invoke(tmp_path,mutation):
    mod=api();package=mod.load_package();context=mod.prepare(package);review,loop,path=synthetic_authorization(mod,package,tmp_path)
    if mutation=='review':review['verdict']='REJECT'
    if mutation=='manifest':review['manifest_sha256']='0'*64
    if mutation=='binding':review['bindings']['sources'].clear()
    if mutation=='body':context['body']['think']=False
    if mutation=='schema':context['schema_json']['additionalProperties']=True
    if mutation=='messages':context['messages'][0]=type(context['messages'][0])(content='Oracle answer')
    if mutation=='upstream':context['upstream']['coverages'].pop()
    if mutation=='context':context['input_tokens']=32768
    if mutation=='oracle':package['oracle']['approval']='forged'
    with pytest.raises(ValueError):mod.preflight(package,context,review,task_path=path)


def test_live_execution_rejects_open_author_and_missing_review_without_network(tmp_path,capsys):
    mod=api();package=mod.load_package();review,_,_=synthetic_authorization(mod,package,tmp_path)
    with pytest.raises(ValueError,match='provenance'):mod.preflight(package,mod.prepare(package),review)
    assert mod.main([])==0 and json.loads(capsys.readouterr().out)['provider_calls']==0
    with pytest.raises(ValueError,match='review'):mod.main(['--execute','--ticket','unused'])


@pytest.mark.parametrize('mutation',['none','node','closed','audit','status','round'])
def test_active_selection_ticket_and_audit_gate(tmp_path,mutation):
    mod=api();loop=dict(status='RUNNING',audit_due=False,needs_research=False,
        active=dict(node='natural_kind_policy_shape_selection',round=18),tickets={'active':dict(
            node='natural_kind_policy_shape_selection',round=18,role='worker',closed=False,platform_id='/active')})
    item=loop['tickets']['active']
    if mutation=='node':item['node']='root'
    if mutation=='closed':item['closed']=True
    if mutation=='audit':loop['audit_due']=True
    if mutation=='status':loop['status']='NEEDS_USER'
    if mutation=='round':item['round']=17
    path=tmp_path/'task.md';save_task(path,loop)
    if mutation=='none':mod._execution_guard('active',task_path=path)
    else:
        with pytest.raises(ValueError,match='active'):mod._execution_guard('active',task_path=path)


def test_full_frozen_sources_rebuild_new_body_and_all_prefixes(tmp_path):
    import os
    import subprocess
    mod=api();package=mod.load_package();frozen=mod.freeze_sources(tmp_path/'frozen',package)
    for name in ['messages','body','schema','upstream']:
        assert (frozen/'evaluations/fixtures/kind_diagnostics_policy_shape/inputs'/('SEL-ISO-v1-01-'+name+'.json')).is_file()
    script='''import json,sys
from pathlib import Path
from langchain_core.messages import AIMessage
from evaluations.diagnostics import managed_policy_shape as m
from evaluations import managed_three_stage_runner as runner
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
sys.path.insert(0,str(m.ROOT/'tests/unit'))
from test_kind_mapping_managed_contract import inputs
p=m.load_package();c=m.prepare(p);out=Path(sys.argv[1]);old=m.rebound.prepare(p['legacy'],'SEL-ISO-v1-01')
assert c['body']['messages'][0]['content']==old['body']['messages'][0]['content']+m.SELECTION_SUFFIX
for label,index in [('default',0),('null',1),('shape',2),('typed',0)]:
 value=json.loads((p['root']/'oracle.json').read_text(encoding='utf-8'))['positive_outputs']['SEL-ISO-v1-01']
 value['draft']['integration']['missing_data_policy']=m.MISSING_POLICIES[index]
 if label=='typed':value['draft']['tasks'][0].pop('filters')
 folder=out/label;r=m.record_sample(folder,c,lambda *a:AIMessage(content=json.dumps(value,ensure_ascii=False)))
 assert r['status']==('PASS' if label in ['default','null'] else 'FAIL')
 assert m.replay(folder,p)['result']==r['status']
for failure in [None,'shape','typed']:
 catalog=SchemaCatalog(m.ROOT/'projects/retail');request,rec,maps,sel=inputs(catalog)
 if failure=='shape':sel['draft']['integration']['missing_data_policy']=m.MISSING_POLICIES[2]
 if failure=='typed':sel['draft']['tasks'][0].pop('filters')
 values=iter([rec,*maps,sel]);folder=out/('full-'+str(failure));case=runner.diagnostic_case(catalog,request)
 meta=runner.record_run(folder,catalog,case,lambda *a:AIMessage(content=json.dumps(next(values),ensure_ascii=False)),contract=m)
 assert bool(meta['stopped'])==bool(failure)
 result=runner.replay(folder,catalog,case,contract=m);assert result['raw_replays']==9 and result['stopped']==meta['stopped']
source=Path(m.__file__);original=source.read_bytes();value=p['oracle']['positive_outputs']['SEL-ISO-v1-01']
def drift(*a):
 source.write_bytes(original+b'\\n');return AIMessage(content=json.dumps(value,ensure_ascii=False))
folder=out/'source-drift'
try:
 r=m.record_sample(folder,c,drift);assert r['status']=='FAIL' and m.base.read_json(folder/'run.json')['stopped'] is None
 assert (folder/'node-call.json').is_file()
finally:source.write_bytes(original)
assert m.replay(folder,p)['result']=='FAIL'
print(json.dumps(dict(frozen_selection_replays=4,frozen_full_nine_replays=3,provider_calls=0)))
'''
    env=dict(os.environ,PYTHONPATH=str(frozen/'src')+':'+str(frozen),PYTHONDONTWRITEBYTECODE='1')
    proc=subprocess.run([sys.executable,'-c',script,str(tmp_path/'runs')],cwd=frozen,env=env,
        capture_output=True,text=True,encoding='utf-8')
    assert proc.returncode==0,proc.stdout+proc.stderr
    assert json.loads(proc.stdout)['provider_calls']==0


def test_natural_fingerprint_binds_complete_policy_candidate_and_original_imports():
    from evaluations import managed_three_stage_runner as runner
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    mod=api();catalog=SchemaCatalog('projects/retail');case=runner.diagnostic_case(catalog)
    fingerprint=runner.fingerprint(catalog,case,contract=mod)
    names={Path(name).resolve() for name in fingerprint['managed_sources']}
    for name in [*rebound.source_paths(),*mod.ADDITIONAL_SOURCES,*mod.REFERENCES,
                 mod.DEFAULT_MANIFEST.relative_to(base.ROOT).as_posix()]:
        assert (base.ROOT/name).resolve() in names


def test_managed_authorization_rechecks_after_preserving_raw(tmp_path):
    mod=api();package=mod.load_package();context=mod.prepare(package)
    review,loop,path=synthetic_authorization(mod,package,tmp_path)
    node='natural_kind_policy_shape_selection'
    loop.update(status='RUNNING',audit_due=False,needs_research=False,active=dict(node=node,round=18))
    loop['tickets']['active']=dict(role='worker',node=node,round=18,platform_id='/active',closed=False)
    save_task(path,loop);authorization=mod.preflight(package,context,review,task_path=path)
    raw=json.dumps(package['oracle']['positive_outputs']['SEL-ISO-v1-01'],ensure_ascii=False)
    good=tmp_path/'good'
    receipt=mod.record_sample(good,context,lambda *a:AIMessage(content=raw),mode='MANAGED_LOCAL_ISOLATION',
        review=review,authorization=authorization,task_path=path,ticket='active')
    assert receipt['status']=='PASS' and mod.replay(good,package)['result']=='PASS'
    folder=tmp_path/'revoked'
    def revoke(*a):
        loop['tickets'][review['ticket']]['closed']=False;save_task(path,loop)
        return AIMessage(content=raw)
    receipt=mod.record_sample(folder,context,revoke,mode='MANAGED_LOCAL_ISOLATION',
        review=review,authorization=authorization,task_path=path,ticket='active')
    assert receipt['status']=='FAIL' and (folder/'node-call.json').is_file()
    assert base.read_json(folder/'run.json')['stopped'] is None
    assert mod.replay(folder,package)['result']=='FAIL'
