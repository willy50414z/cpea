"""Lossless responsibility projection with a bounded scope-AND diagnostic delta."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from evaluations import managed_node_diagnostics as base
from evaluations.diagnostics import managed_node_diagnostics_rebound as rebound
from evaluations.diagnostics import managed_policy_shape as policy

ROOT = base.ROOT
VERSION = 'managed-capability-projection-1'
CONTENT_VERSION = 'kind-capability-projection-1'
AUTHOR_TICKET = 'c3b66ba5cf4c4d549e846203bb29b5e7'
DEFAULT_MANIFEST = ROOT/'evaluations/fixtures/kind_diagnostics_capability_projection/manifest.json'
POLICY_REVIEW = 'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-policy-semantics/review.json'
ADDITIONAL_SOURCES = ('evaluations/diagnostics/managed_capability_projection.py',
    'tests/diagnostics/test_managed_capability_projection.py')
REFERENCE_PATHS = (policy.DEFAULT_MANIFEST.relative_to(ROOT).as_posix(), POLICY_REVIEW,
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-research-20/plan.json',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-research-20/research.json',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-research-20/handoff.json',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-coverage-isolation/handoff.json')
SAMPLE_IDS = ['COV-ISO-v1-01','COV-ISO-v1-02','COV-ISO-v1-03','COV-CAP-v1-04','COV-CAP-v1-05']
COVERAGE_SUFFIX = '''\n\n本版本使用無損 requirement_cards：identity 保留身分；own_target 是本項 kind 的自身責任；binding_context 完整保留原文其他資訊與明示關聯，並非可忽略資訊。所有卡片共同構成原 requirements，ID 關聯不變。
請依序處理每項：
1. 依本項 kind 的責任與真實 View 契約，辨認並保留全部獨立有用的能力分量。部分 grain 的有用鍵不等於能完成完整 grain 或整題；無關 identifier 不能湊成有用分量。不可因整題不可實現而刪掉本項有用 mapping。
2. 判自身是否完整，只有明示 scope_ids、grain_requirement_ids 等依賴的未完成可以排除於自身缺口。自身能力或自身母體限制仍須驗證，縱使原文位於 binding_context；不能只因有聚合就忽略本項母體限制。依賴未完成不等於自身缺口。
3. 再依全體同 View 卡片的明示依賴決定原 status；自行明填原 wire 的 own_gap、status 及全部 mappings/conditions/證據。請勿新增輸出欄位或將 context 當答案。先前全部來源、scope、grain、母體與 typed 守門均適用。
'''
RecallWire, SelectionWire = policy.RecallWire, policy.SelectionWire
materialize_recall, materialize_coverage = policy.materialize_recall, policy.materialize_coverage
materialize_selection = policy.materialize_selection
coverage_schema, compile_coverage, parse_wire = policy.coverage_schema, policy.compile_coverage, policy.parse_wire
receipt_path, _save_receipt, _read_receipt = rebound.receipt_path, rebound._save_receipt, rebound._read_receipt
SOURCES = [*policy.SOURCES, *map(Path,ADDITIONAL_SOURCES), *map(Path,REFERENCE_PATHS), DEFAULT_MANIFEST,
    *[DEFAULT_MANIFEST.parent/'inputs'/f'{sid}-{part}.json' for sid in SAMPLE_IDS
      for part in ['messages','body','schema','upstream','cards']]]


def project_cards(requirements):
    cards=[]
    for row in requirements:
        if not isinstance(row,dict) or not {'requirement_id','kind','quote','business_object'} <= row.keys():
            raise ValueError('card requires original identity and own fields')
        own={'kind','quote','business_object'}
        if row['kind']=='grain': own.add('grain')
        if row['kind']=='population': own.add('population')
        cards.append(dict(identity={'requirement_id':deepcopy(row['requirement_id'])},
            own_target={k:deepcopy(v) for k,v in row.items() if k in own},
            binding_context={k:deepcopy(v) for k,v in row.items() if k not in own|{'requirement_id'}}))
    if len({c['identity']['requirement_id'] for c in cards})!=len(cards):
        raise ValueError('duplicate card identity')
    restore_cards(cards,requirements)
    return cards


def restore_cards(cards,original):
    restored=[]
    for card in cards:
        if set(card)!= {'identity','own_target','binding_context'} or any(not isinstance(v,dict) for v in card.values()):
            raise ValueError('invalid card sections')
        row={}
        for section in ['identity','own_target','binding_context']:
            if row.keys() & card[section].keys(): raise ValueError('overlapping card keys')
            row.update(deepcopy(card[section]))
        own={'kind','quote','business_object'}
        if row.get('kind')=='grain':own.add('grain')
        if row.get('kind')=='population':own.add('population')
        if (set(card['identity'])!={'requirement_id'} or set(card['own_target'])!=own & row.keys()
                or set(card['binding_context'])!=row.keys()-own-{'requirement_id'}):
            raise ValueError('card sections differ from original responsibility partition')
        restored.append(row)
    if restored!=original: raise ValueError('card projection loses or invents original fields')
    return restored


def messages(phase,schema,request,**context):
    result=policy.messages(phase,schema,request,**context)
    if phase!='coverage': return result
    payload=json.loads(result[1].content)
    payload['requirement_cards']=project_cards(payload.pop('requirements'))
    return [SystemMessage(content=result[0].content+COVERAGE_SUFFIX),
            HumanMessage(content=json.dumps(payload,ensure_ascii=False))]


def sample_design(legacy):
    samples=[deepcopy(s) for s in legacy['manifest']['samples'] if s['stage']=='coverage']
    for sid,view in [('COV-CAP-v1-04','demo_retail.v_customer_value'),('COV-CAP-v1-05','demo_retail.v_inventory_status')]:
        samples.append(dict(samples[0],id=sid,view=view))
    for s in samples:
        s['request_case']=CONTENT_VERSION+':ISOLATION:'+s['id']+':node'
        s['lineage']=dict(sample_id=s['id'] if s['id'].startswith('COV-ISO') else 'SEL-ISO-v1-01',
            manifest=rebound.DEFAULT_MANIFEST.relative_to(ROOT).as_posix(),
            manifest_sha256=policy.REFERENCES[rebound.DEFAULT_MANIFEST.relative_to(ROOT).as_posix()])
        s['expected_reference']=dict(path='oracle.json',positive_output=s['id']) if s['id'].startswith('COV-ISO') else dict(
            path='coverage-selection.json',view=s['view'])
    return samples


def manifest_design(legacy,references,bindings=None):
    return dict(schema_version=1,version=CONTENT_VERSION,runner_version=VERSION,candidate=VERSION,
        author=dict(ticket=AUTHOR_TICKET,node='capability_projection_contract',round=21,
            platform='/root/loop_worker_capability_contract'),fixture_root=legacy['manifest']['fixture_root'],
        upstream_injected=True,approval='PENDING_FRESH_CAPABILITY_PROJECTION_REVIEW',
        samples=sample_design(legacy),references=references,bindings=bindings)


def load_package(manifest=DEFAULT_MANIFEST):
    if Path(manifest).resolve()!=DEFAULT_MANIFEST.resolve(): raise ValueError('only fixed capability manifest admitted')
    legacy=rebound.load_package(); pp=policy.load_package(); data=base.read_json(manifest)
    if data!=manifest_design(legacy,data.get('references'),data.get('bindings')) or not isinstance(data.get('bindings'),dict):
        raise ValueError('fixed capability design differs')
    if set(data['references'])!=set(REFERENCE_PATHS) or any(base.digest(ROOT/k)!=v for k,v in data['references'].items()):
        raise ValueError('capability immutable references differ')
    engine=deepcopy(legacy)
    selected=base.read_json(legacy['root']/'coverage-selection.json')
    for s in data['samples'][3:]: engine['oracle']['positive_outputs'][s['id']]=deepcopy(selected[s['view']])
    return dict(manifest=data,manifest_path=Path(manifest).resolve(),legacy=legacy,policy_package=pp,
        root=legacy['root'],oracle=engine['oracle'],engine=engine)


def prepare(package,sample_id):
    sample=next((s for s in package['manifest']['samples'] if s['id']==sample_id),None)
    if sample is None: raise ValueError('sample not in fixed capability manifest')
    context=rebound.prepare(package['legacy'],sample_id if sample_id.startswith('COV-ISO') else 'COV-ISO-v1-01')
    view=next(v.policy for v in context['catalog'].views() if v.name==sample['view'])
    requirements=[r.model_dump() for r in context['recall'].requirements]
    context.update(sample=deepcopy(sample),package=package['engine'],capability_package=package,
        messages=messages('coverage',context['schema'],context['request'],requirements=requirements,view=view),
        cards=project_cards(requirements))
    context['body']=base._body(context['messages'],context['schema'])
    context['input_tokens']=base.TiktokenCounter('cl100k_base').count_messages([(m.type,m.content) for m in context['messages']])
    for part,value in _inputs(context).items():
        path=DEFAULT_MANIFEST.parent/'inputs'/f'{sample_id}-{part}.json'
        if path.exists() and base.read_json(path)!=value: raise ValueError('fixed capability input differs: '+part)
    return context


def _inputs(context):
    return dict(messages=[dict(role=m.type,content=m.content) for m in context['messages']],body=context['body'],
        schema=context['schema_json'],upstream=context['upstream'],cards=context['cards'])


def bindings(package):
    contexts=[prepare(package,sid) for sid in SAMPLE_IDS]
    return dict(legacy=rebound.bindings(package['legacy']),policy=policy.bindings(package['policy_package']),
        sources={k:base.digest(ROOT/k) for k in ADDITIONAL_SOURCES},references=package['manifest']['references'],
        suffix=base.json_digest(COVERAGE_SUFFIX),candidate=VERSION,
        inputs={f'inputs/{sid}-{part}.json':base.digest(DEFAULT_MANIFEST.parent/'inputs'/f'{sid}-{part}.json')
            for sid in SAMPLE_IDS for part in _inputs(contexts[SAMPLE_IDS.index(sid)])},
        samples={c['sample']['id']:dict(**{k:base.json_digest(v) for k,v in _inputs(c).items()},
            input_tokens=c['input_tokens'],catalog=c['catalog'].fingerprint) for c in contexts})


def _version_guard(package,frozen,manifest_hash):
    if (load_package()!=package or base.digest(package['manifest_path'])!=manifest_hash
            or bindings(package)!=frozen or frozen!=package['manifest']['bindings']):
        raise ValueError('complete capability source/version/input drift')
    policy._version_guard(package['policy_package'],frozen['policy'],base.digest(policy.DEFAULT_MANIFEST))
    rebound._version_guard(package['legacy'],frozen['legacy'],policy.REFERENCES[rebound.DEFAULT_MANIFEST.relative_to(ROOT).as_posix()])


def _context_guard(package,context):
    fresh=prepare(package,context['sample']['id'])
    if (context['capability_package']!=package or context['package']!=fresh['package']
            or context['sample']!=fresh['sample'] or context['request']!=fresh['request']
            or _inputs(context)!=_inputs(fresh) or context['input_tokens']!=fresh['input_tokens']
            or context['input_tokens']>=32768 or base._body(context['messages'],context['schema'])!=fresh['body']
            or context['schema'].model_json_schema()!=fresh['schema_json']
            or context['recall'].model_dump()!=fresh['recall'].model_dump()
            or context['catalog'].fingerprint!=fresh['catalog'].fingerprint or context['coverages']!=fresh['coverages']):
        raise ValueError('capability context/schema/body/upstream drift')


def _scope_metric_equivalent(context,parsed,rid,expected,actual,legacy_findings):
    requirements={r.requirement_id:r for r in context['recall'].requirements}
    req=requirements[rid]
    if req.kind!='metric' or not actual or len(actual)!=len(expected): return False
    groups=[]
    for scope_id in req.scope_ids:
        scope=requirements.get(scope_id);row=parsed['entries'].get(scope_id)
        if (scope is None or scope.kind!='filter' or row is None or row['status']!='supported' or row['own_gap']
                or any(f.get('requirement_id')==scope_id for f in legacy_findings)):
            continue
        if row['mappings']: groups.append(set(map(base.json_digest,row['mappings'])))
    unmatched=list(expected)
    changed=False
    for mapping in actual:
        same=next((target for target in unmatched if {k:v for k,v in mapping.items() if k!='conditions'}==
            {k:v for k,v in target.items() if k!='conditions'}),None)
        if same is None: return False
        unmatched.remove(same)
        if mapping==same: continue
        if same.get('conditions')!=[] or not mapping.get('conditions'): return False
        values=set(map(base.json_digest,mapping['conditions']))
        complete=[group for group in groups if group<=values]
        if not complete or set().union(*complete)!=values: return False
        changed=True
    return changed and not unmatched


def _decision(context,parsed,findings):
    others=deepcopy(findings);equivalences=[]
    for finding in findings:
        if (finding.get('aspect')=='necessary mappings/predicates' and _scope_metric_equivalent(context,parsed,
                finding['requirement_id'],finding['expected'],finding['actual'],findings)):
            others.remove(finding);equivalences.append(deepcopy(finding))
    return dict(status='FAIL' if others else 'PASS',legacy_findings=findings,
        accepted_scope_AND_equivalences=equivalences,other_findings=others,
        independent_semantic_approval='PENDING',free_text_review='PENDING')


def evaluate(context,raw):
    result=base.evaluate(context,raw)
    return _decision(context,result['parsed'],result['semantic']['findings'])


def _loop(task_path=None):
    path=Path(task_path) if task_path else ROOT/base.TASK/'task.md'
    return json.loads(path.read_text(encoding='utf-8').split('---',2)[1])['plan']['edd_loop']


def _roles(package,review,loop):
    roles={}
    for role,ticket,node in [('author',AUTHOR_TICKET,'capability_projection_contract'),
            ('reviewer',review['ticket'],'capability_projection_semantics')]:
        item=loop['tickets'].get(ticket)
        completed=[r for r in loop['rounds'] if item and r.get('round')==item.get('round') and r.get('node')==node
            and r.get('producer')==item.get('platform_id') and r.get('result')=='PASS']
        if (not item or item.get('role')!='worker' or item.get('node')!=node or item.get('closed') is not True
                or type(item.get('round')) is not int or not item.get('platform_id') or len(completed)!=1):
            raise ValueError('capability review lacks closed provenance')
        if role=='author' and (item['round']!=21 or item['platform_id']!='/root/loop_worker_capability_contract'
                or not any(e.get('path')==DEFAULT_MANIFEST.relative_to(ROOT).as_posix()
                    and e.get('sha256')==base.digest(DEFAULT_MANIFEST) for e in completed[0]['evidence'])):
            raise ValueError('capability author completion differs')
        if role=='reviewer' and not any(policy._review_proof(e,review) for e in completed[0]['evidence']):
            raise ValueError('capability reviewer completion lacks immutable review')
        roles[role]=dict(ticket=ticket,**item,completion=completed[0])
    if len({r['platform_id'] for r in roles.values()})!=2 or review['ticket']==AUTHOR_TICKET:
        raise ValueError('capability provenance must be distinct')
    return roles


def _review_guard(package,review):
    if (not isinstance(review,dict) or review.get('schema_version')!=1 or review.get('verdict')!='ACCEPT'
            or review.get('reviewer_role')!='fresh_capability_projection_semantics' or not review.get('ticket')
            or review.get('author_ticket')!=AUTHOR_TICKET or review.get('manifest_sha256')!=base.digest(DEFAULT_MANIFEST)
            or review.get('bindings')!=package['manifest']['bindings']):
        raise ValueError('execute requires complete fresh capability ACCEPT review')


def preflight(package,contexts,review,*,task_path=None):
    _review_guard(package,review);_version_guard(package,package['manifest']['bindings'],base.digest(DEFAULT_MANIFEST))
    for context in contexts:_context_guard(package,context)
    loop=_loop(task_path);roles=_roles(package,review,loop)
    old=policy.preflight(package['policy_package'],policy.prepare(package['policy_package']),
        base.read_json(ROOT/POLICY_REVIEW),task_path=task_path)
    if {r['platform_id'] for r in roles.values()} & {r['platform_id'] for r in
            [*old['roles'].values(),*old['legacy_authorization']['roles'].values()]}:
        raise ValueError('capability roles must be fresh from legacy provenance')
    return dict(result='PASS',manifest_sha256=base.digest(DEFAULT_MANIFEST),
        bindings_sha256=base.json_digest(package['manifest']['bindings']),review_sha256=base.json_digest(review),
        roles=roles,policy_authorization=old)


def _execution_guard(ticket,*,task_path=None):
    loop=_loop(task_path);item=loop['tickets'].get(ticket);active=loop.get('active') or {}
    node='natural_capability_projection_coverage'
    if (loop.get('status')!='RUNNING' or loop.get('audit_due') or loop.get('needs_research')
            or not item or item.get('role')!='worker' or item.get('closed') is not False
            or item.get('node')!=node or not item.get('platform_id') or active.get('node')!=node
            or item.get('round')!=active.get('round')
            or not any(a.get('verdict')=='CONTINUE' and {19,20,21}<=set(a.get('reviewed_rounds',[]))
                for a in loop.get('reviews',[]))):
        raise ValueError('execute requires active capability worker and approved 19–21 audit')


def _authorization(package,context,review,authorization,mode,task_path):
    if mode=='OFFLINE_CONTROL' and review is None and authorization is None:
        return dict(mode=mode,manifest_sha256=base.digest(DEFAULT_MANIFEST),
            bindings_sha256=base.json_digest(package['manifest']['bindings']),independent_semantic_approval='PENDING')
    fresh=preflight(package,[context],review,task_path=task_path)
    if mode!='MANAGED_LOCAL_ISOLATION' or authorization!=fresh: raise ValueError('capability authorization mismatch')
    return fresh


def _outcome(folder,context,inner):
    semantic_error=dict(error_type='ValueError',error='fixed diagnostic semantic checks failed')
    if inner['stopped'] not in [None,semantic_error] or (folder/'node-provider-error.json').exists() or not (folder/'semantic-review.json').is_file():
        return dict(status='FAIL',stopped=inner['stopped'],decision=None)
    decision=_decision(context,base.read_json(folder/'node-parsed.json'),base.read_json(folder/'semantic-review.json')['findings'])
    return dict(status=decision['status'],decision=decision,
        stopped=None if decision['status']=='PASS' else dict(error_type='ValueError',error='capability or other diagnostic semantic checks failed'))


def record_sample(folder,context,invoke,*,mode='OFFLINE_CONTROL',identity=None,authorization=None,
        context_window=32768,review=None,task_path=None,ticket=None):
    folder=Path(folder);package=context['capability_package']
    if (folder.exists() and any(folder.iterdir())) or receipt_path(folder).exists(): raise ValueError('sample and receipt must be empty')
    frozen=bindings(package);manifest_hash=base.digest(DEFAULT_MANIFEST)
    auth=_authorization(package,context,review,authorization,mode,task_path)
    def check():
        _version_guard(package,frozen,manifest_hash);_context_guard(package,context)
        if _authorization(package,context,review,authorization,mode,task_path)!=auth: raise ValueError('authorization changed')
        if mode=='MANAGED_LOCAL_ISOLATION':_execution_guard(ticket,task_path=task_path)
    check()
    receipt=dict(version=VERSION,content_version=CONTENT_VERSION,engine_version=base.VERSION,sample_folder=folder.name,
        sample=context['sample'],mode=mode,bindings=frozen,manifest_sha256=manifest_hash,review=review,authorization=auth,
        status='INTERRUPTED',stopped=dict(error_type='InterruptedRun',error='outer run did not reach completion'),decision=None)
    folder.parent.mkdir(parents=True,exist_ok=True);_save_receipt(folder,receipt)
    def guarded(*args):
        if _read_receipt(folder)!=receipt:raise ValueError('receipt changed before HTTP')
        check();return invoke(*args)
    try:
        inner=base.record_sample(folder,context,guarded,mode=mode,identity=identity,authorization=auth,context_window=context_window)
        if _read_receipt(folder)!=receipt:raise ValueError('receipt changed after raw')
        check();base._verify_artifacts(folder,inner)
        if inner['authorization']!=auth:raise ValueError('inner authorization mismatch')
        receipt.update(_outcome(folder,context,inner))
    except Exception as exc:receipt.update(status='FAIL',stopped=base.error_record(exc))
    receipt['inner_hashes']={p.name:base.digest(p) for p in folder.iterdir() if p.is_file()} if folder.exists() else {}
    _save_receipt(folder,receipt);return receipt


def replay(folder,package=None):
    folder=Path(folder);package=package or load_package();receipt=_read_receipt(folder)
    if receipt['status']=='INTERRUPTED':raise ValueError('capability receipt interrupted')
    if (receipt['version']!=VERSION or receipt['content_version']!=CONTENT_VERSION or receipt['engine_version']!=base.VERSION
            or receipt['sample_folder']!=folder.name or receipt['status'] not in ['PASS','FAIL']
            or (receipt['status']=='PASS')!=(receipt['stopped'] is None)):raise ValueError('receipt identity/result mismatch')
    _version_guard(package,receipt['bindings'],receipt['manifest_sha256']);context=prepare(package,receipt['sample']['id'])
    if context['sample']!=receipt['sample']:raise ValueError('replay sample mismatch')
    if receipt['mode']=='OFFLINE_CONTROL':
        expected=_authorization(package,context,None,None,'OFFLINE_CONTROL',None)
        if receipt['review'] is not None or receipt['authorization']!=expected:raise ValueError('offline authorization mismatch')
    else:
        _review_guard(package,receipt['review']);auth=receipt['authorization'];old=auth['policy_authorization']
        roles=[*auth['roles'].values(),*old['roles'].values(),*old['legacy_authorization']['roles'].values()]
        loop=dict(tickets={r['ticket']:{k:v for k,v in r.items() if k not in ['ticket','completion']} for r in roles},
            rounds=[r['completion'] for r in roles])
        pp=package['policy_package'];pr=base.read_json(ROOT/POLICY_REVIEW)
        legacy_roles=rebound._roles(package['legacy'],base.read_json(ROOT/policy.OLD_REVIEW),loop)
        legacy_auth=dict(result='PASS',manifest_sha256=policy.REFERENCES[rebound.DEFAULT_MANIFEST.relative_to(ROOT).as_posix()],
            bindings_sha256=base.json_digest(receipt['bindings']['legacy']),
            review_sha256=base.json_digest(base.read_json(ROOT/policy.OLD_REVIEW)),roles=legacy_roles)
        policy_auth=dict(result='PASS',manifest_sha256=base.digest(policy.DEFAULT_MANIFEST),
            bindings_sha256=base.json_digest(receipt['bindings']['policy']),review_sha256=base.json_digest(pr),
            roles=policy._roles(pp,pr,loop),legacy_authorization=legacy_auth)
        expected_auth=dict(result='PASS',manifest_sha256=receipt['manifest_sha256'],
            bindings_sha256=base.json_digest(receipt['bindings']),review_sha256=base.json_digest(receipt['review']),
            roles=_roles(package,receipt['review'],loop),policy_authorization=policy_auth)
        if (receipt['mode']!='MANAGED_LOCAL_ISOLATION' or _roles(package,receipt['review'],loop)!=auth['roles']
                or policy._roles(pp,pr,loop)!=old['roles']
                or auth!=expected_auth
                or auth['manifest_sha256']!=receipt['manifest_sha256'] or auth['bindings_sha256']!=base.json_digest(receipt['bindings'])
                or auth['review_sha256']!=base.json_digest(receipt['review'])):raise ValueError('managed authorization provenance mismatch')
    if receipt['inner_hashes']!={p.name:base.digest(p) for p in folder.iterdir() if p.is_file()}:raise ValueError('inner artifact mismatch')
    inner=base.read_json(folder/'run.json');base._verify_artifacts(folder,inner)
    if (inner['authorization']!=receipt['authorization'] or inner['version']!=base.VERSION
            or inner['frozen']!=base.bindings(package['engine']) or inner['manifest_sha256']!=base.digest(package['legacy']['manifest_path'])
            or inner['sample']!=context['sample']):raise ValueError('inner version/auth mismatch')
    saved={}
    def invoke(name,messages,schema):
        if base.read_json(folder/'node-body.json')!=base._body(messages,schema):raise ValueError('replay body mismatch')
        if (folder/'node-provider-error.json').exists():raise base.RecordedProviderError(base.read_json(folder/'node-provider-error.json'))
        call=base.read_json(folder/'node-call.json')
        return AIMessage(content=call['response'],usage_metadata=call['usage'],response_metadata=call['response_metadata'] or {})
    stopped=None
    try:base._run(context,invoke,saved.__setitem__,lambda:None,inner['context_window'])
    except Exception as exc:stopped=base.error_record(exc)
    if stopped!=inner['stopped']:raise ValueError('legacy first error differs')
    for name,value in saved.items():
        original=base.read_json(folder/name)
        if name.endswith(('-call.json','-provider-error.json')):
            original.pop('elapsed_seconds',None);value.pop('elapsed_seconds',None)
        if original!=value:raise ValueError('replay artifact differs: '+name)
    if set(inner['artifact_hashes'])-{'node-managed.json','node-provider-response.json'}!=set(saved):raise ValueError('artifact set differs')
    outcome=_outcome(folder,context,inner)
    if receipt['decision'] is not None and receipt['decision']!=outcome['decision']:raise ValueError('decision differs')
    if receipt['status']=='PASS' and (outcome['status']!='PASS' or receipt['decision'] is None):raise ValueError('unproven PASS')
    return dict(result=receipt['status'],replay_verification='PASS',decision=outcome['decision'],stopped=receipt['stopped'],
        legacy_stopped=stopped,raw_replays=int('node-call.json' in saved),provider_calls=0)


def freeze_sources(destination,package=None,review=None):
    package=package or load_package();_version_guard(package,package['manifest']['bindings'],base.digest(DEFAULT_MANIFEST))
    destination=policy.freeze_sources(destination,package['policy_package'],review=base.read_json(ROOT/POLICY_REVIEW))
    names={**package['manifest']['references'],**package['manifest']['bindings']['sources'],
        DEFAULT_MANIFEST.relative_to(ROOT).as_posix():base.digest(DEFAULT_MANIFEST)}
    names.update({(DEFAULT_MANIFEST.parent/k).relative_to(ROOT).as_posix():v for k,v in package['manifest']['bindings']['inputs'].items()})
    if review is not None:
        auth=preflight(package,[prepare(package,sid) for sid in SAMPLE_IDS],review)
        names.update({e['path']:e['sha256'] for e in auth['roles']['reviewer']['completion']['evidence'] if policy._review_proof(e,review)})
    for name,expected in names.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        if base.digest(target)!=expected:raise ValueError('capability frozen source differs')
    base.write_json(destination/'capability-freeze.json',dict(version=VERSION,bindings=bindings(package),files=names,
        manifest_sha256=base.digest(DEFAULT_MANIFEST),replay_module=__name__))
    return destination


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__);group=parser.add_mutually_exclusive_group()
    group.add_argument('--execute',action='store_true');group.add_argument('--replay',type=Path)
    parser.add_argument('--review',type=Path);parser.add_argument('--ticket');args=parser.parse_args(argv)
    package=load_package()
    if args.replay:
        result=replay(args.replay,package);print(json.dumps(result,ensure_ascii=False));return int(result['result']!='PASS')
    contexts=[prepare(package,sid) for sid in SAMPLE_IDS]
    if not args.execute:
        print(json.dumps(dict(version=VERSION,execute=False,provider_calls=0,
            samples=[dict(id=c['sample']['id'],input_tokens=c['input_tokens']) for c in contexts],
            bindings_match=bindings(package)==package['manifest']['bindings']),ensure_ascii=False));return 0
    # Authorization precedes settings and model identity network access.
    review=base.read_json(args.review) if args.review else None
    auth=preflight(package,contexts,review);_execution_guard(args.ticket)
    settings=base.AssistantSettings.from_env(ROOT/'.env')
    if settings.llm_provider!='ollama':raise ValueError('only local Ollama is authorized')
    os.environ['EDD_LOCAL_ENDPOINT']=settings.llm_base_url.rstrip('/')+'/api/chat'
    identity=base.verify_model_identity(settings.llm_base_url)
    batch=ROOT/base.TASK/'.local'/(CONTENT_VERSION+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    batch.mkdir(mode=0o700);base.write_json(batch/'capability-review.json',review)
    freeze_sources(batch/'frozen',package,review);results=[]
    for context in contexts:
        preflight(package,[context],review);_execution_guard(args.ticket)
        folder=batch/context['sample']['id']
        invoke=base.ManagedInvoke(folder,args.ticket,context['sample']['request_case'].removesuffix(':node'),
            lambda name,value,folder=folder:base.write_json(folder/name,value))
        receipt=record_sample(folder,context,invoke,mode='MANAGED_LOCAL_ISOLATION',identity=identity,
            authorization=auth,review=review,ticket=args.ticket)
        results.append(dict(sample=context['sample']['id'],status=receipt['status'],stopped=receipt['stopped'],
            folder=str(folder),outer_receipt_sha256=base.digest(receipt_path(folder))))
        base.write_json(batch/'outer-receipts.json',results)
        if ((folder/'node-provider-error.json').exists() or not (folder/'node-call.json').exists()
                or (receipt['decision'] is None and receipt['stopped']!=base.read_json(folder/'run.json')['stopped'])):
            break
    print(json.dumps(dict(batch=str(batch),results=results,independent_semantic_approval='PENDING'),ensure_ascii=False))
    return int(len(results)!=len(contexts) or any(r['status']!='PASS' for r in results))


if __name__=='__main__':raise SystemExit(main())
