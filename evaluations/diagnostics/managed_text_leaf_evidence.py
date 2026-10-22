"""Bound catalog text leaves, with unchanged capability and policy semantics."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Literal

from langchain_core.messages import AIMessage
from pydantic import Field, create_model
from cpea.application.models.decomposition import PlanningModel

from evaluations.diagnostics import managed_capability_projection as capability
from evaluations import managed_three_stage_runner as runner

base, policy, rebound = capability.base, capability.policy, capability.rebound
ROOT = base.ROOT
VERSION = 'managed-text-leaf-evidence-1'
CONTENT_VERSION = 'kind-text-leaf-evidence-1'
AUTHOR_TICKET = '8ef15624ec38441da20ff256197a6af6'
DEFAULT_MANIFEST = ROOT/'evaluations/fixtures/kind_diagnostics_text_leaf/manifest.json'
FIXTURES = DEFAULT_MANIFEST.parent
SAMPLE_IDS = (*capability.SAMPLE_IDS, *(f'COV-LEAF-v1-{i:02}' for i in range(6,10)))
SEEDS = (42,43,44)
CAPABILITY_REVIEW = 'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-capability-semantics/review.json'
REFERENCE_PATHS = (capability.DEFAULT_MANIFEST.relative_to(ROOT).as_posix(),CAPABILITY_REVIEW,
    'docs/next_enhance_advice.md', *('evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-research-23/'+n+'.json'
    for n in ['plan','handoff','research','advice-evaluation','raw-and-leaf-probe']))
ADDITIONAL_SOURCES = ('evaluations/diagnostics/managed_text_leaf_evidence.py',
    'tests/diagnostics/test_managed_text_leaf_evidence.py')
# Explicit nested additions preserve the old top-level source closure.
SOURCES = (*capability.SOURCES,*map(Path,ADDITIONAL_SOURCES),*map(Path,REFERENCE_PATHS),
    *(p for p in sorted(FIXTURES.rglob('*')) if p.is_file()))
RecallWire, SelectionWire = policy.RecallWire, policy.SelectionWire
materialize_recall, materialize_selection = policy.materialize_recall, policy.materialize_selection
parse_wire, compile_coverage, messages = policy.parse_wire, policy.compile_coverage, capability.messages


def text_leaf_paths(value, path=''):
    if isinstance(value,str): return (path,) if value.strip() and path else ()
    if isinstance(value,dict):
        return tuple(p for key,item in value.items() for p in text_leaf_paths(item,
            path+'/'+str(key).replace('~','~0').replace('/','~1')))
    if isinstance(value,list):
        return tuple(p for i,item in enumerate(value) for p in text_leaf_paths(item,path+'/'+str(i)))
    return ()


@dataclass(frozen=True)
class BoundContract:
    """Immutable snapshot; the runner schema API has no current-view argument."""
    fingerprint: str
    policies_json: tuple[str,...]
    VERSION = VERSION
    SOURCES = SOURCES
    RecallWire, SelectionWire = RecallWire, SelectionWire
    materialize_recall = staticmethod(materialize_recall)
    materialize_selection = staticmethod(materialize_selection)
    parse_wire = staticmethod(parse_wire)
    compile_coverage = staticmethod(compile_coverage)
    messages = staticmethod(messages)

    @property
    def paths(self):
        return tuple(sorted({p for raw in self.policies_json for p in text_leaf_paths(json.loads(raw))}))

    def coverage_schema(self,recall):
        old=policy.coverage_schema(recall)
        old_entries=old.model_fields['entries'].annotation
        fields={}
        path_type=Literal[self.paths] | None if self.paths else type(None)
        for name,field in old_entries.model_fields.items():
            decision=field.annotation
            if 'contract_path' in decision.model_fields:
                decision=create_model(decision.__name__,__base__=decision,contract_path=(path_type,...))
            fields[name]=(decision,Field(alias=field.alias))
        entries=create_model(old_entries.__name__,__base__=PlanningModel,**fields)
        return create_model(old.__name__,__base__=PlanningModel,entries=(entries,...))

    def materialize_coverage(self,wire,recall,request,catalog,view):
        if (not any(view==v.policy for v in catalog.views()) or catalog.fingerprint!=self.fingerprint or tuple(base.json_digest(v.policy) for v in catalog.views())!=
                tuple(base.json_digest(json.loads(raw)) for raw in self.policies_json)):
            raise ValueError('bound catalog changed')
        self.coverage_schema(recall).model_validate(wire.model_dump(by_alias=True))
        # Current-view nonempty-text validation and all semantic guards remain original.
        return policy.materialize_coverage(wire,recall,request,catalog,view)


def bind_catalog(catalog):
    return BoundContract(catalog.fingerprint,tuple(json.dumps(v.policy,ensure_ascii=False,sort_keys=True) for v in catalog.views()))


def body(messages,schema,seed=42):
    if type(seed) is not int or seed not in SEEDS:raise ValueError('seed outside fixed panel')
    value=base._body(messages,schema);value['options']['seed']=seed
    return value


class SeedManagedInvoke:
    """Explicit immutable body transport through the original controller only."""
    def __init__(self,folder,ticket,case_id,save,*,seed):
        if type(seed) is not int or seed not in SEEDS:raise ValueError('unplanned seed')
        self.folder,self.ticket,self.case_id,self.save,self.seed=Path(folder),ticket,case_id,save,seed

    def __call__(self,name,messages,schema):
        payload=body(messages,schema,self.seed);path=self.folder/(name+'-body.json')
        if path.exists() and base.read_json(path)!=payload:raise ValueError('actual managed body differs from frozen body')
        base.write_json(path,payload)
        command=[sys.executable,str(base.LOOPCTL),'--root',str(ROOT),'--id','ollama-planning-mvp','request',
            '--ticket',self.ticket,'--provider','local','--case',self.case_id+':'+name,
            '--url-env','EDD_LOCAL_ENDPOINT','--file',str(path.resolve())]
        completed=subprocess.run(command,cwd=ROOT,text=True,encoding='utf-8',capture_output=True)
        try:receipt=json.loads(completed.stdout)
        except ValueError:raise RuntimeError('controller receipt unavailable; inspect inflight before resuming') from None
        self.save(name+'-managed.json',receipt)
        if receipt.get('response_path'):
            request_path=Path(receipt['response_path']).with_name(receipt['request_id']+'.request.json')
            actual_body=base.read_json(request_path)
            if actual_body!=payload or receipt.get('calls_charged')!=1 or receipt.get('automatic_retries')!=0:
                raise ValueError('controller actual request/body/receipt differs')
            self.save(name+'-controller-request.json',actual_body)
        response=base.read_json(Path(receipt['response_path'])) if receipt.get('response_path') else None
        if response is not None:self.save(name+'-provider-response.json',response)
        if completed.returncode or receipt.get('result')!='ok':raise RuntimeError('managed request failed: '+str(receipt.get('result')))
        if (not isinstance(response,dict) or response.get('model')!=base.MODEL or response.get('done') is not True
                or response.get('done_reason') not in [None,'stop'] or not isinstance(response.get('message',{}).get('content'),str)):
            raise ValueError('managed response model/completion/content differs')
        usage=None
        if all(type(response.get(k)) is int for k in ['prompt_eval_count','eval_count']):
            usage=dict(input_tokens=response['prompt_eval_count'],output_tokens=response['eval_count'],
                total_tokens=response['prompt_eval_count']+response['eval_count'])
        return AIMessage(content=response['message']['content'],usage_metadata=usage,
            response_metadata={**{k:v for k,v in response.items() if k!='message'},
                'text_leaf_transport':dict(seed=self.seed,body_sha256=base.json_digest(payload))})


def cells():
    return [dict(sample_id=sid,seed=seed,request_case=f'{CONTENT_VERSION}:ISOLATION:A1:{sid}:seed{seed}:node')
        for seed in SEEDS for sid in SAMPLE_IDS]


def manifest_design(references,bindings=None):
    return dict(schema_version=1,version=CONTENT_VERSION,candidate=VERSION,
        author=dict(ticket=AUTHOR_TICKET,node='text_leaf_evidence_contract',round=24,platform='/root/loop_worker_text_leaf_contract'),
        upstream_injected=True,approval='PENDING_FRESH_TEXT_LEAF_REVIEW',
        enum_scope='catalog-wide nonempty text pointer union; current View materialize still validates',
        samples=base.read_json(FIXTURES/'panel.json'),cells=cells(),
        block_policy=dict(order=list(SEEDS),cases=list(SAMPLE_IDS),continue_only='all nine full semantic PASS in previous block',
            any_fail='candidate FAIL; do not start next block',not_retries=True,full_natural_seed=42),
        references=references,bindings=bindings)


def load_package():
    data=base.read_json(DEFAULT_MANIFEST)
    if data!=manifest_design(data.get('references'),data.get('bindings')) or not isinstance(data.get('bindings'),dict):
        raise ValueError('fixed text leaf manifest differs')
    if set(data['references'])!=set(REFERENCE_PATHS) or any(base.digest(ROOT/k)!=v for k,v in data['references'].items()):
        raise ValueError('immutable text leaf references drift')
    previous=capability.load_package();engine=deepcopy(previous['engine'])
    expected=base.read_json(FIXTURES/'expected-new.json')
    engine['oracle']['positive_outputs'].update(expected)
    return dict(manifest=data,manifest_path=DEFAULT_MANIFEST,capability_package=previous,
        legacy=previous['legacy'],engine=engine,oracle=engine['oracle'])


def prepare(package,sample_id,seed=42):
    if sample_id not in SAMPLE_IDS:raise ValueError('unplanned sample')
    spec=next(s for s in package['manifest']['samples'] if s['id']==sample_id)
    c=capability.prepare(package['capability_package'],spec['base'])
    if spec.get('profile'):
        c['catalog']=base.SchemaCatalog(FIXTURES/spec['profile'])
        recall_data=base.read_json(FIXTURES/spec['recall_transformed'])
        c['recall']=materialize_recall(RecallWire.model_validate(recall_data),c['request'],c['catalog'])
    bound=bind_catalog(c['catalog']);schema=bound.coverage_schema(c['recall'])
    view=next(v.policy for v in c['catalog'].views() if v.name==spec['view'])
    requirements=[r.model_dump() for r in c['recall'].requirements]
    c.update(package=package['engine'],leaf_package=package,bound_contract=bound,seed=seed,
        schema=schema,schema_json=schema.model_json_schema(),cards=capability.project_cards(requirements),
        sample=dict(c['sample'],id=sample_id,view=spec['view'],
            request_case=next(x['request_case'] for x in cells() if x['sample_id']==sample_id and x['seed']==seed)),
        upstream=dict(recall=c['recall'].model_dump(),coverages=[],profile_id=c['catalog'].profile_id,
            catalog_fingerprint=c['catalog'].fingerprint))
    c['messages']=messages('coverage',schema,c['request'],requirements=requirements,view=view)
    c['body']=body(c['messages'],schema,seed)
    c['input_tokens']=base.TiktokenCounter('cl100k_base').count_messages([(m.type,m.content) for m in c['messages']])
    if c['input_tokens']>=32768:raise ValueError('leaf enum cannot fit model context')
    for part,value in inputs(c).items():
        path=FIXTURES/'inputs'/f'{sample_id}-seed{seed}-{part}.json'
        if path.exists() and base.read_json(path)!=value:raise ValueError('fixed leaf input differs: '+part)
    return c


def inputs(context):
    return dict(messages=[dict(role=m.type,content=m.content) for m in context['messages']],body=context['body'],
        schema=context['schema_json'],upstream=context['upstream'],cards=context['cards'])


def bindings(package):
    contexts=[prepare(package,c['sample_id'],c['seed']) for c in cells()]
    return dict(capability=capability.bindings(package['capability_package']),
        sources={k:base.digest(ROOT/k) for k in ADDITIONAL_SOURCES},references=package['manifest']['references'],
        fixtures={p.relative_to(FIXTURES).as_posix():base.digest(p) for p in sorted(FIXTURES.rglob('*'))
            if p.is_file() and p!=DEFAULT_MANIFEST},
        model_by_seed={str(seed):dict(name=base.MODEL,digest=base.MODEL_DIGEST,think=True,
            options=dict(base.MODEL_OPTIONS,seed=seed),HTTP_timeout_seconds=None,outer_timeout_seconds=None) for seed in SEEDS},
        samples={f'{c["sample"]["id"]}:seed{c["seed"]}':dict(**{k:base.json_digest(v) for k,v in inputs(c).items()},
            input_tokens=c['input_tokens'],catalog=c['catalog'].fingerprint) for c in contexts})


def version_guard(package):
    if load_package()!=package or bindings(package)!=package['manifest']['bindings']:raise ValueError('complete leaf version/input drift')
    capability._version_guard(package['capability_package'],package['manifest']['bindings']['capability'],base.digest(capability.DEFAULT_MANIFEST))


def context_guard(package,c):
    fresh=prepare(package,c['sample']['id'],c['seed'])
    if (c['leaf_package']!=package or c['package']!=fresh['package'] or c['sample']!=fresh['sample']
            or inputs(c)!=inputs(fresh) or c['request']!=fresh['request'] or c['input_tokens']!=fresh['input_tokens']
            or c['schema'].model_json_schema()!=fresh['schema_json'] or c['bound_contract']!=fresh['bound_contract']
            or c['recall'].model_dump()!=fresh['recall'].model_dump() or c['coverages']!=fresh['coverages']
            or c['catalog'].fingerprint!=fresh['catalog'].fingerprint or body(c['messages'],c['schema'],c['seed'])!=c['body']):
        raise ValueError('leaf context/schema/seed/body/upstream drift')


def evaluate(context,raw):
    result=base.evaluate(context,raw)
    return capability._decision(context,result['parsed'],result['semantic']['findings'])


def review_guard(package,review):
    if (not isinstance(review,dict) or review.get('schema_version')!=1 or review.get('verdict')!='ACCEPT'
            or review.get('reviewer_role')!='fresh_text_leaf_evidence_semantics' or not review.get('ticket')
            or review.get('author_ticket')!=AUTHOR_TICKET or review.get('manifest_sha256')!=base.digest(DEFAULT_MANIFEST)
            or review.get('bindings')!=package['manifest']['bindings']):raise ValueError('fresh complete text leaf ACCEPT required')


def roles(package,review,loop):
    result={}
    for role,ticket,node in [('author',AUTHOR_TICKET,'text_leaf_evidence_contract'),
            ('reviewer',review['ticket'],'text_leaf_evidence_semantics')]:
        item=loop['tickets'].get(ticket)
        completed=[r for r in loop['rounds'] if item and r.get('round')==item.get('round') and r.get('node')==node
            and r.get('producer')==item.get('platform_id') and r.get('result')=='PASS']
        if (not item or item.get('role')!='worker' or item.get('node')!=node or item.get('closed') is not True
                or type(item.get('round')) is not int or not item.get('platform_id') or len(completed)!=1):
            raise ValueError('text leaf provenance must be true closed PASS')
        if role=='author' and (item['round']!=24 or item['platform_id']!='/root/loop_worker_text_leaf_contract'
                or not any(e.get('path')==DEFAULT_MANIFEST.relative_to(ROOT).as_posix() and e.get('sha256')==base.digest(DEFAULT_MANIFEST)
                    for e in completed[0]['evidence'])):raise ValueError('leaf author completion differs')
        if role=='reviewer' and not any(policy._review_proof(e,review) for e in completed[0]['evidence']):
            raise ValueError('leaf reviewer completion lacks exact immutable review')
        result[role]=dict(ticket=ticket,**item,completion=completed[0])
    if len({v['platform_id'] for v in result.values()})!=2 or review['ticket']==AUTHOR_TICKET:raise ValueError('distinct leaf roles required')
    return result


def audit_guard(loop):
    if not any(r.get('verdict')=='CONTINUE' and {22,23,24}<=set(r.get('reviewed_rounds',[])) for r in loop.get('reviews',[])):
        raise ValueError('fresh audit 22–24 CONTINUE required')


def preflight(package,contexts,review,*,task_path=None):
    review_guard(package,review);version_guard(package)
    for c in contexts:context_guard(package,c)
    loop=capability._loop(task_path);audit_guard(loop);new=roles(package,review,loop)
    old=capability.preflight(package['capability_package'],
        [capability.prepare(package['capability_package'],sid) for sid in capability.SAMPLE_IDS],
        base.read_json(ROOT/CAPABILITY_REVIEW),task_path=task_path)
    old_platforms={r['platform_id'] for section in [old,old['policy_authorization'],old['policy_authorization']['legacy_authorization']]
        for r in section['roles'].values()}
    if old_platforms & {r['platform_id'] for r in new.values()}:raise ValueError('leaf roles must be fresh from all old authors/reviewers')
    return dict(result='PASS',manifest_sha256=base.digest(DEFAULT_MANIFEST),bindings_sha256=base.json_digest(package['manifest']['bindings']),
        review_sha256=base.json_digest(review),roles=new,capability_authorization=old)


def execution_guard(ticket,task_path=None):
    loop=capability._loop(task_path);item=loop['tickets'].get(ticket);active=loop.get('active') or {}
    audit_guard(loop)
    if (loop.get('status')!='RUNNING' or loop.get('audit_due') or loop.get('needs_research') or not item
            or item.get('role')!='worker' or item.get('closed') is not False or not item.get('platform_id')
            or item.get('node')!='natural_text_leaf_evidence_coverage' or active.get('node')!=item['node']
            or active.get('round')!=item.get('round')):raise ValueError('active natural leaf worker required')


def record_sample(folder,context,invoke,*,review=None,ticket=None,task_path=None,prior_blocks=()):
    """Thin outer receipt; original diagnostics own raw, first errors and artifacts."""
    folder=Path(folder);package=context['leaf_package']
    if folder.exists() and any(folder.iterdir()) or capability.receipt_path(folder).exists():raise ValueError('preserve first sample')
    managed=type(invoke) is SeedManagedInvoke
    if isinstance(invoke,(SeedManagedInvoke,base.ManagedInvoke)) and not managed:raise ValueError('fixed seed transport required')
    mode='MANAGED_LOCAL_ISOLATION' if managed else 'OFFLINE_CONTROL'
    if not managed and (review is not None or ticket is not None):raise ValueError('offline cannot claim managed authorization')
    auth=preflight(package,[context],review,task_path=task_path) if managed else dict(mode=mode,independent_semantic_approval='PENDING')
    def check():
        version_guard(package);context_guard(package,context)
        if managed:
            execution_guard(ticket,task_path);block_gate(package,context['seed'],prior_blocks)
            if (invoke.ticket!=ticket or invoke.folder.resolve()!=folder.resolve() or invoke.seed!=context['seed']
                    or invoke.case_id!=context['sample']['request_case'].removesuffix(':node')
                    or preflight(package,[context],review,task_path=task_path)!=auth):raise ValueError('fixed managed identity/body authorization differs')
    check()
    receipt=dict(version=VERSION,manifest_sha256=base.digest(DEFAULT_MANIFEST),bindings=package['manifest']['bindings'],
        sample=context['sample'],seed=context['seed'],prior_blocks=list(prior_blocks),body_sha256=base.json_digest(context['body']),mode=mode,
        review=review,authorization=auth,status='INTERRUPTED',stopped=dict(error_type='InterruptedRun',error='outer incomplete'))
    folder.parent.mkdir(parents=True,exist_ok=True);capability._save_receipt(folder,receipt)
    def guarded(*args):
        if capability._read_receipt(folder)!=receipt:raise ValueError('outer receipt drift')
        check();return invoke(*args)
    try:
        inner=base.record_sample(folder,context,guarded,mode=mode,authorization=auth)
        if capability._read_receipt(folder)!=receipt:raise ValueError('outer receipt drift after raw')
        check();base._verify_artifacts(folder,inner)
        receipt.update(capability._outcome(folder,context,inner))
    except Exception as exc:receipt.update(status='FAIL',stopped=base.error_record(exc),decision=None)
    receipt['inner_hashes']={p.name:base.digest(p) for p in folder.iterdir() if p.is_file()}
    capability._save_receipt(folder,receipt);return receipt


def replay(folder,package=None):
    folder=Path(folder);package=package or load_package();receipt=capability._read_receipt(folder)
    version_guard(package);context=prepare(package,receipt['sample']['id'],receipt['seed'])
    if (receipt['version']!=VERSION or receipt['manifest_sha256']!=base.digest(DEFAULT_MANIFEST)
            or receipt['bindings']!=package['manifest']['bindings'] or receipt['sample']!=context['sample']
            or receipt['body_sha256']!=base.json_digest(context['body']) or receipt['status'] not in ['PASS','FAIL']
            or (receipt['status']=='PASS')!=(receipt['stopped'] is None)
            or receipt['inner_hashes']!={p.name:base.digest(p) for p in folder.iterdir() if p.is_file()}):raise ValueError('leaf receipt drift/incomplete')
    if receipt['mode']=='MANAGED_LOCAL_ISOLATION':
        review_guard(package,receipt['review']);auth=receipt['authorization']
        chain=[auth,auth['capability_authorization'],auth['capability_authorization']['policy_authorization'],
            auth['capability_authorization']['policy_authorization']['legacy_authorization']]
        allroles=[r for section in chain for r in section['roles'].values()]
        loop=dict(tickets={r['ticket']:{k:v for k,v in r.items() if k not in ['ticket','completion']} for r in allroles},
            rounds=[r['completion'] for r in allroles])
        if (roles(package,receipt['review'],loop)!=auth['roles'] or auth['manifest_sha256']!=receipt['manifest_sha256']
                or auth['bindings_sha256']!=base.json_digest(receipt['bindings'])
                or auth['review_sha256']!=base.json_digest(receipt['review'])):raise ValueError('leaf frozen provenance mismatch')
        capability._roles(package['capability_package'],base.read_json(ROOT/CAPABILITY_REVIEW),loop)
        policy._roles(package['capability_package']['policy_package'],base.read_json(ROOT/capability.POLICY_REVIEW),loop)
        rebound._roles(package['legacy'],base.read_json(ROOT/policy.OLD_REVIEW),loop)
    elif receipt['mode']!='OFFLINE_CONTROL' or receipt['review'] is not None or receipt['authorization']!=dict(mode='OFFLINE_CONTROL',independent_semantic_approval='PENDING'):
        raise ValueError('leaf replay mode/auth mismatch')
    inner=base.read_json(folder/'run.json');base._verify_artifacts(folder,inner)
    if (inner['frozen']!=base.bindings(package['engine']) or inner['sample']!=context['sample']
            or inner['authorization']!=receipt['authorization'] or inner['manifest_sha256']!=base.digest(package['legacy']['manifest_path'])):
        raise ValueError('leaf inner binding/auth mismatch')
    saved={}
    def invoke(name,messages,schema):
        if base.read_json(folder/'node-body.json')!=body(messages,schema,context['seed']):raise ValueError('replay seed/body drift')
        if (folder/'node-provider-error.json').exists():raise base.RecordedProviderError(base.read_json(folder/'node-provider-error.json'))
        call=base.read_json(folder/'node-call.json')
        return AIMessage(content=call['response'],usage_metadata=call['usage'],response_metadata=call['response_metadata'] or {})
    stopped=None
    try:base._run(context,invoke,saved.__setitem__,lambda:None,inner['context_window'])
    except Exception as exc:stopped=base.error_record(exc)
    if stopped!=inner['stopped']:raise ValueError('leaf first error differs')
    for name,value in saved.items():
        original=base.read_json(folder/name)
        if name.endswith(('-call.json','-provider-error.json')):original.pop('elapsed_seconds',None);value.pop('elapsed_seconds',None)
        if original!=value:raise ValueError('leaf replay artifact differs: '+name)
    if set(inner['artifact_hashes'])-{'node-managed.json','node-provider-response.json','node-controller-request.json'}!=set(saved):raise ValueError('leaf artifact set differs')
    outcome=capability._outcome(folder,context,inner)
    if outcome['decision']!=receipt.get('decision') or (receipt['status']=='PASS' and outcome['status']!='PASS'):raise ValueError('leaf outcome differs')
    return dict(result=receipt['status'],replay_verification='PASS',raw_replays=int('node-call.json' in saved),provider_calls=0)


def block_gate(package,seed,prior_blocks=()):
    """Only immutable full-semantic evidence unlocks a subsequent fixed block."""
    if seed not in SEEDS or len(prior_blocks)!=SEEDS.index(seed):raise ValueError('all earlier blocks must be approved')
    for expected_seed,proof_name in zip(SEEDS,prior_blocks):
        proof_path=Path(proof_name)
        proof=base.read_json(proof_path)
        if (proof.get('version')!=VERSION or proof.get('manifest_sha256')!=base.digest(DEFAULT_MANIFEST)
                or proof.get('seed')!=expected_seed or proof.get('verdict')!='ACCEPT'
                or [r.get('sample_id') for r in proof.get('cases',[])]!=list(SAMPLE_IDS)):
            raise ValueError('fixed complete full-semantic block approval required')
        for row in proof['cases']:
            folder=Path(row['folder']);receipt=capability._read_receipt(folder)
            review_path=Path(row['semantic_review'])
            semantic=base.read_json(review_path)
            if (base.digest(capability.receipt_path(folder))!=row['receipt_sha256']
                    or base.digest(review_path)!=row['semantic_review_sha256']
                    or receipt.get('mode')!='MANAGED_LOCAL_ISOLATION' or receipt.get('status')!='PASS'
                    or receipt.get('seed')!=expected_seed or receipt.get('sample',{}).get('id')!=row['sample_id']
                    or semantic.get('verdict')!='ACCEPT' or semantic.get('full_raw_and_thinking_review') is not True
                    or semantic.get('all_rows_and_derived_gaps') is not True or semantic.get('safe_false_accepts')!=0
                    or semantic.get('manifest_sha256')!=base.digest(DEFAULT_MANIFEST)
                    or semantic.get('raw_call_sha256')!=base.digest(folder/'node-call.json')
                    or semantic.get('body_sha256')!=base.digest(folder/'node-body.json')
                    or semantic.get('sample_id')!=row['sample_id'] or semantic.get('seed')!=expected_seed):
                raise ValueError('block lacks exact first raw and complete semantic approval')
            if replay(folder,package)['result']!='PASS':raise ValueError('earlier block replay failed')
    return dict(seed=seed,prior_block_proofs={str(p):base.digest(p) for p in prior_blocks})


def freeze_sources(destination,package=None,review=None):
    package=package or load_package();version_guard(package)
    destination=capability.freeze_sources(destination,package['capability_package'],review=base.read_json(ROOT/CAPABILITY_REVIEW))
    names={**package['manifest']['references'],**package['manifest']['bindings']['sources'],
        DEFAULT_MANIFEST.relative_to(ROOT).as_posix():base.digest(DEFAULT_MANIFEST)}
    names.update({(FIXTURES/n).relative_to(ROOT).as_posix():v for n,v in package['manifest']['bindings']['fixtures'].items()})
    if review is not None:
        auth=preflight(package,[prepare(package,sid) for sid in SAMPLE_IDS],review)
        names.update({e['path']:e['sha256'] for e in auth['roles']['reviewer']['completion']['evidence'] if policy._review_proof(e,review)})
    for name,expected in names.items():
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(ROOT/name,target)
        if base.digest(target)!=expected:raise ValueError('leaf frozen bytes differ')
    base.write_json(destination/'text-leaf-freeze.json',dict(version=VERSION,files=names,bindings=bindings(package),manifest_sha256=base.digest(DEFAULT_MANIFEST)))
    return destination
