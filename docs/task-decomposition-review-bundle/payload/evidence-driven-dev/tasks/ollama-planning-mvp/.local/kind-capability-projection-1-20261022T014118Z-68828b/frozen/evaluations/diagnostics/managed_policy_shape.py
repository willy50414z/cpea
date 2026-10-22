"""Versioned policy shape contract and thin selection diagnostic adapter."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
from uuid import uuid4

from langchain_core.messages import AIMessage, SystemMessage

from evaluations import kind_mapping_managed_contract as previous
from evaluations import managed_node_diagnostics as base
from evaluations.diagnostics import managed_node_diagnostics_rebound as rebound
from evaluations.three_stage_view_selection import MISSING_POLICIES

ROOT = base.ROOT
VERSION = 'managed-policy-shape-1'
CONTENT_VERSION = 'kind-policy-shape-1'
AUTHOR_TICKET = '34175c2580224eddb7061898d2af61ef'
DEFAULT_MANIFEST = ROOT / 'evaluations/fixtures/kind_diagnostics_policy_shape/manifest.json'
OLD_REVIEW = 'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-diagnostic-semantics-rebound/review.json'
REFERENCES = {
    'evaluations/fixtures/kind_diagnostics_rebound/manifest.json': '9efa86b883366ff1ef4edd555f59f08499fa123288c6ca1ffe98998d84156187',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-fixture-v2/handoff.json': '941eb3d28a538de71637172dd14b2e2e9fa7ef0c139201a205f5a57d2c66de73',
    'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-rebinding/handoff.json': '9a52891179e2dde4812069999c5408acb5357f746f8a5e98a8ca5d297b791c42',
    OLD_REVIEW: 'f986fd1f361948c4ea4ecc24d4c7e779956210488467533411908f440f07c135',
}
SELECTION_SUFFIX = '''\n\n缺值政策與輸出形狀的適用條件：
missing_policy_options 的第一與第二項皆適用於保留未匹配母體、以缺值表示未匹配的平面 scalar 輸出；兩者都禁止在無契約保證時補零。
第三項的「子集合為空集合」只適用於實際輸出 nested child collection：每條可能未匹配且保留左母體的 child edge，必須在 integration.preparation 明示 kind=nest，task_id 精確為該 edge.right_task，keys 精確對應該 edge.right_keys，且 edge.mode=left、preserve_task=edge.left_task。
aggregate 僅表示彙總，不表示 nested output；metadata_collections、來源沒有 right row 也不等於 typed nest。平面 scalar 缺值不能以不存在的子集合政策宣稱保證。請依實際需求選擇適用的既有政策並自行明填所有 typed 欄位；不可為使用某政策而新增需求未要求的集合形狀。以上條件不取代來源、scope、grain、assignment、母體或其他守門。
'''
ADDITIONAL_SOURCES = ('evaluations/diagnostics/managed_policy_shape.py',
                      'tests/diagnostics/test_managed_policy_shape.py')
SOURCES = [*previous.SOURCES, *map(Path, rebound.source_paths()),
    *map(Path, ADDITIONAL_SOURCES), *map(Path, REFERENCES), DEFAULT_MANIFEST,
    *[ROOT/name for name in rebound.LINEAGE],
    *[p for p in (ROOT/'evaluations/fixtures/kind_diagnostics_v2').rglob('*') if p.is_file()],
    *[DEFAULT_MANIFEST.parent/'inputs'/('SEL-ISO-v1-01-'+name+'.json') for name in ['messages','body','schema','upstream']]]
RecallWire, SelectionWire = previous.RecallWire, previous.SelectionWire
materialize_recall, materialize_coverage = previous.materialize_recall, previous.materialize_coverage
coverage_schema, compile_coverage, parse_wire = previous.coverage_schema, previous.compile_coverage, previous.parse_wire
receipt_path, _save_receipt, _read_receipt = rebound.receipt_path, rebound._save_receipt, rebound._read_receipt


def policy_findings(draft):
    integration = draft.get('integration') or {}
    policy = integration.get('missing_data_policy')
    if policy not in MISSING_POLICIES:
        return [dict(aspect='unadmitted missing policy', actual=policy)]
    if policy != MISSING_POLICIES[2]:
        return []
    edges = integration.get('edges', [])
    preparation = integration.get('preparation', [])
    if not edges or any(e['mode'] != 'left' or e['preserve_task'] != e['left_task']
            or not e['right_keys'] or not any(p['kind'] == 'nest' and p['task_id'] == e['right_task']
                and p['keys'] == e['right_keys'] for p in preparation) for e in edges):
        return [dict(aspect='empty collection policy lacks typed preserved nested child shape', actual=integration)]
    return []


def messages(phase, schema, request, **context):
    result = previous.messages(phase, schema, request, **context)
    if phase == 'selection':
        result[0] = SystemMessage(content=result[0].content + SELECTION_SUFFIX)
    return result


def materialize_selection(wire, *args):
    result = previous.materialize_selection(wire, *args)
    findings = policy_findings(wire.model_dump()['draft'])
    if findings:
        raise ValueError(findings[0]['aspect'])
    return result


def load_package(manifest=DEFAULT_MANIFEST):
    if Path(manifest).resolve() != DEFAULT_MANIFEST.resolve():
        raise ValueError('only the fixed policy shape manifest is supported')
    old = rebound.load_package()
    if any(base.digest(ROOT / name) != value for name, value in REFERENCES.items()):
        raise ValueError('policy immutable references differ')
    data = base.read_json(manifest)
    sample = dict(old['manifest']['samples'][0], request_case=CONTENT_VERSION + ':ISOLATION:SEL-ISO-v1-01:node')
    expected = dict(schema_version=1, version=CONTENT_VERSION, runner_version=VERSION,
        candidate=VERSION, author_ticket=AUTHOR_TICKET, fixture_root=old['manifest']['fixture_root'],
        upstream_injected=True, approval='PENDING_FRESH_POLICY_SHAPE_REVIEW', samples=[sample],
        references=REFERENCES, bindings=data.get('bindings'))
    if data != expected or not isinstance(data.get('bindings'), dict):
        raise ValueError('fixed policy shape design differs')
    return dict(manifest=data, manifest_path=Path(manifest).resolve(), root=old['root'], oracle=old['oracle'], legacy=old)


def prepare(package, sample_id='SEL-ISO-v1-01'):
    if sample_id != 'SEL-ISO-v1-01':
        raise ValueError('only the fixed selection sample is admitted')
    context = rebound.prepare(package['legacy'], sample_id)
    context['messages'] = deepcopy(context['messages'])
    context['messages'][0] = SystemMessage(content=context['messages'][0].content + SELECTION_SUFFIX)
    context.update(package=package['legacy'], sample=deepcopy(package['manifest']['samples'][0]))
    context['body'] = base._body(context['messages'], context['schema'])
    context['input_tokens'] = base.TiktokenCounter('cl100k_base').count_messages([(m.type,m.content) for m in context['messages']])
    context['policy_package'] = package
    for suffix,value in _inputs(context).items():
        path=DEFAULT_MANIFEST.parent/'inputs'/('SEL-ISO-v1-01-'+suffix+'.json')
        if path.exists() and base.read_json(path)!=value:
            raise ValueError('fixed policy input differs: '+suffix)
    return context


def _inputs(context):
    return dict(messages=[dict(role=m.type,content=m.content) for m in context['messages']],
        body=context['body'],schema=context['schema_json'],upstream=context['upstream'])


def bindings(package):
    context = prepare(package)
    return dict(legacy=rebound.bindings(package['legacy']),
        sources={name:base.digest(ROOT / name) for name in ADDITIONAL_SOURCES}, references=REFERENCES,
        candidate=VERSION, suffix=base.json_digest(SELECTION_SUFFIX),
        inputs={('inputs/SEL-ISO-v1-01-'+name+'.json'):base.digest(DEFAULT_MANIFEST.parent/'inputs'/('SEL-ISO-v1-01-'+name+'.json')) for name in _inputs(context)},
        sample=dict(body=base.json_digest(context['body']), schema=base.json_digest(context['schema_json']),
            upstream=base.json_digest(context['upstream']),
            messages=base.json_digest([dict(role=m.type,content=m.content) for m in context['messages']]),
            input_tokens=context['input_tokens']))


def _version_guard(package, frozen, manifest_hash):
    fresh = load_package(package['manifest_path'])
    if (fresh != package or base.digest(package['manifest_path']) != manifest_hash
            or bindings(package) != frozen or frozen != package['manifest']['bindings']):
        raise ValueError('complete policy source/version/input drift')
    rebound._version_guard(package['legacy'], frozen['legacy'], REFERENCES['evaluations/fixtures/kind_diagnostics_rebound/manifest.json'])


def _context_guard(package, context):
    fresh = prepare(package)
    if (context['policy_package'] != package or context['package'] != fresh['package']
            or context['sample'] != fresh['sample'] or context['input_tokens'] >= 32768
            or context['input_tokens'] != fresh['input_tokens'] or context['body'] != fresh['body']
            or context['schema_json'] != fresh['schema_json']
            or context['schema'].model_json_schema() != fresh['schema_json']
            or base._body(context['messages'],context['schema']) != fresh['body']
            or context['request'] != fresh['request'] or context['upstream'] != fresh['upstream']
            or context['catalog'].fingerprint != fresh['catalog'].fingerprint
            or context['recall'].model_dump() != fresh['recall'].model_dump()
            or [c.model_dump() for c in context['coverages']] != [c.model_dump() for c in fresh['coverages']]):
        raise ValueError('policy context/schema/body/upstream drift')


def _decision(context, parsed, legacy_findings, response):
    # Replace exactly the located literal clause, retain every other finding.
    literal = dict(aspect='no unproven zero fill', actual=parsed['draft']['integration']['missing_data_policy'])
    others = deepcopy(legacy_findings)
    if literal in others:
        others.remove(literal)
    policy = policy_findings(parsed['draft'])
    return dict(status='FAIL' if others or policy else 'PASS', legacy_findings=legacy_findings,
        policy_findings=policy, other_findings=others, response=response,
        independent_semantic_approval='PENDING', free_text_review='PENDING')


def evaluate(context, raw):
    result = base.evaluate(context,raw)
    return _decision(context,result['parsed'],result['semantic']['findings'],result['response'])


def _roles(package, review, loop):
    roles = {}
    for role,ticket,node in [('author',AUTHOR_TICKET,'kind_policy_shape_contract'),
                            ('reviewer',review['ticket'],'kind_policy_shape_semantics')]:
        item = loop['tickets'].get(ticket)
        matches = [r for r in loop['rounds'] if item and r.get('round')==item.get('round')
            and r.get('node')==node and r.get('producer')==item.get('platform_id') and r.get('result')=='PASS']
        if (not item or item.get('role')!='worker' or item.get('node')!=node or item.get('closed') is not True
                or not item.get('platform_id') or type(item.get('round')) is not int or len(matches)!=1):
            raise ValueError('policy review lacks completed provenance')
        evidence = matches[0].get('evidence',[])
        if not any(e.get('sha256')==base.digest(package['manifest_path'])
                   and e.get('path')==DEFAULT_MANIFEST.relative_to(ROOT).as_posix() for e in evidence) and role=='author':
            raise ValueError('policy author completion does not bind manifest')
        if role=='reviewer' and not any(_review_proof(e,review) for e in evidence):
            raise ValueError('policy reviewer completion lacks immutable review provenance')
        roles[role] = dict(ticket=ticket,**item,completion=matches[0])
    if len({r['platform_id'] for r in roles.values()})!=2 or roles['author']['ticket']==roles['reviewer']['ticket']:
        raise ValueError('policy review lacks distinct provenance')
    return roles


def _review_proof(evidence,review):
    try:
        path=ROOT/evidence['path']
        return path.is_file() and base.digest(path)==evidence['sha256'] and base.read_json(path)==review
    except (KeyError,ValueError,OSError):
        return False


def _review_guard(package,review):
    if (not isinstance(review,dict) or review.get('schema_version')!=1 or review.get('verdict')!='ACCEPT'
            or review.get('reviewer_role')!='fresh_policy_shape_semantics'
            or not review.get('ticket') or review.get('author_ticket')!=AUTHOR_TICKET
            or review.get('manifest_sha256')!=base.digest(package['manifest_path'])
            or review.get('bindings')!=package['manifest']['bindings']):
        raise ValueError('execute requires complete fresh policy ACCEPT review')


def preflight(package,context,review,*,task_path=None):
    _review_guard(package,review)
    _version_guard(package,package['manifest']['bindings'],base.digest(package['manifest_path']))
    _context_guard(package,context)
    old_auth = rebound.preflight(package['legacy'],[rebound.prepare(package['legacy'],'SEL-ISO-v1-01')],base.read_json(ROOT/OLD_REVIEW),task_path=task_path)
    path = Path(task_path) if task_path else ROOT / base.TASK / 'task.md'
    loop = json.loads(path.read_text(encoding='utf-8').split('---',2)[1])['plan']['edd_loop']
    roles = _roles(package,review,loop)
    if {r['platform_id'] for r in roles.values()} & {r['platform_id'] for r in old_auth['roles'].values()}:
        raise ValueError('policy reviewer/author must be fresh distinct from fixture roles')
    return dict(result='PASS',manifest_sha256=base.digest(package['manifest_path']),
        bindings_sha256=base.json_digest(package['manifest']['bindings']),review_sha256=base.json_digest(review),
        roles=roles,legacy_authorization=old_auth)


def _execution_guard(ticket,*,task_path=None):
    path = Path(task_path) if task_path else ROOT / base.TASK / 'task.md'
    loop = json.loads(path.read_text(encoding='utf-8').split('---',2)[1])['plan']['edd_loop']
    item = loop['tickets'].get(ticket); active = loop.get('active') or {}; node='natural_kind_policy_shape_selection'
    if (loop.get('status')!='RUNNING' or loop.get('audit_due') or loop.get('needs_research')
            or not item or item.get('role')!='worker' or item.get('node')!=node or item.get('closed') is not False
            or not item.get('platform_id') or active.get('node')!=node or item.get('round')!=active.get('round')):
        raise ValueError('execute requires active policy selection worker and completed audit')


def _authorization(package,context,review,authorization,mode,task_path):
    if mode=='OFFLINE_CONTROL' and review is None and authorization is None:
        return dict(mode=mode,manifest_sha256=base.digest(package['manifest_path']),
                    bindings_sha256=base.json_digest(bindings(package)),independent_semantic_approval='PENDING')
    fresh = preflight(package,context,review,task_path=task_path)
    if mode!='MANAGED_LOCAL_ISOLATION' or authorization!=fresh:
        raise ValueError('policy authorization mismatch')
    return fresh


def _outcome(folder,context,inner):
    stopped = inner['stopped']; semantic_error=dict(error_type='ValueError',error='fixed diagnostic semantic checks failed')
    if (stopped not in [None,semantic_error] or (folder/'node-provider-error.json').exists()
            or not (folder/'semantic-review.json').is_file()):
        return dict(status='FAIL',stopped=stopped,decision=None)
    result = _decision(context,base.read_json(folder/'node-parsed.json'),
        base.read_json(folder/'semantic-review.json')['findings'],base.read_json(folder/'response.json'))
    if result['status']=='FAIL':
        stopped=dict(error_type='ValueError',error='policy shape or other diagnostic semantic checks failed')
    else:
        stopped=None
    return dict(status=result['status'],stopped=stopped,decision=result)


def record_sample(folder,context,invoke,*,mode='OFFLINE_CONTROL',identity=None,authorization=None,
                  context_window=32768,review=None,task_path=None,ticket=None):
    folder=Path(folder); package=context['policy_package']
    if (folder.exists() and any(folder.iterdir())) or receipt_path(folder).exists():
        raise ValueError('sample folder and outer receipt must be empty')
    frozen=bindings(package); manifest_hash=base.digest(package['manifest_path'])
    _version_guard(package,frozen,manifest_hash); _context_guard(package,context)
    auth=_authorization(package,context,review,authorization,mode,task_path)
    def check():
        _version_guard(package,frozen,manifest_hash); _context_guard(package,context)
        if _authorization(package,context,review,authorization,mode,task_path)!=auth:
            raise ValueError('policy authorization changed')
        if mode=='MANAGED_LOCAL_ISOLATION': _execution_guard(ticket,task_path=task_path)
    check()
    receipt=dict(version=VERSION,content_version=CONTENT_VERSION,engine_version=base.VERSION,
        sample_folder=folder.name,sample=context['sample'],mode=mode,bindings=frozen,manifest_sha256=manifest_hash,
        review=review,authorization=auth,status='INTERRUPTED',stopped=dict(error_type='InterruptedRun',error='outer run did not reach completion'),
        started_at=datetime.now(timezone.utc).isoformat(),inner_hashes=None,decision=None)
    folder.parent.mkdir(parents=True,exist_ok=True); _save_receipt(folder,receipt)
    def guarded(*args):
        if _read_receipt(folder)!=receipt: raise ValueError('policy receipt changed before HTTP')
        check()
        return invoke(*args)
    try:
        inner=base.record_sample(folder,context,guarded,mode=mode,identity=identity,authorization=auth,context_window=context_window)
        if _read_receipt(folder)!=receipt: raise ValueError('policy receipt changed after raw')
        check(); base._verify_artifacts(folder,inner)
        if inner['authorization']!=auth: raise ValueError('inner authorization mismatch')
        receipt.update(_outcome(folder,context,inner))
    except Exception as exc:
        receipt.update(status='FAIL',stopped=base.error_record(exc))
    receipt.update(finished_at=datetime.now(timezone.utc).isoformat(),
        inner_hashes={p.name:base.digest(p) for p in folder.iterdir() if p.is_file()} if folder.exists() else {})
    _save_receipt(folder,receipt)
    return receipt


def replay(folder,package=None):
    folder=Path(folder); package=package or load_package(); receipt=_read_receipt(folder)
    if receipt['status']=='INTERRUPTED': raise ValueError('policy receipt interrupted')
    if (receipt['version']!=VERSION or receipt['content_version']!=CONTENT_VERSION or receipt['engine_version']!=base.VERSION
            or receipt['sample_folder']!=folder.name or receipt['status'] not in ['PASS','FAIL']
            or (receipt['status']=='PASS')!=(receipt['stopped'] is None)):
        raise ValueError('policy receipt identity/result mismatch')
    _version_guard(package,receipt['bindings'],receipt['manifest_sha256']); context=prepare(package)
    if context['sample']!=receipt['sample']: raise ValueError('policy replay sample mismatch')
    if receipt['mode']=='OFFLINE_CONTROL':
        if receipt['review'] is not None or receipt['authorization']!=_authorization(package,context,None,None,'OFFLINE_CONTROL',None):
            raise ValueError('policy replay offline authorization mismatch')
    else:
        _review_guard(package,receipt['review']); auth=receipt['authorization']
        all_roles={**{'policy_'+k:v for k,v in auth['roles'].items()},**auth['legacy_authorization']['roles']}
        loop=dict(tickets={r['ticket']:{k:v for k,v in r.items() if k not in ['ticket','completion']} for r in all_roles.values()},
                  rounds=[r['completion'] for r in all_roles.values()])
        if (receipt['mode']!='MANAGED_LOCAL_ISOLATION' or _roles(package,receipt['review'],loop)!=auth['roles']
                or rebound._roles(package['legacy'],base.read_json(ROOT/OLD_REVIEW),loop)!=auth['legacy_authorization']['roles']
                or auth['manifest_sha256']!=receipt['manifest_sha256']
                or auth['bindings_sha256']!=base.json_digest(receipt['bindings'])
                or auth['review_sha256']!=base.json_digest(receipt['review'])
                or auth['legacy_authorization']!=dict(result='PASS',
                    manifest_sha256=REFERENCES['evaluations/fixtures/kind_diagnostics_rebound/manifest.json'],
                    bindings_sha256=base.json_digest(receipt['bindings']['legacy']),
                    review_sha256=base.json_digest(base.read_json(ROOT/OLD_REVIEW)),
                    roles=rebound._roles(package['legacy'],base.read_json(ROOT/OLD_REVIEW),loop))):
            raise ValueError('policy replay managed authorization mismatch')
    if receipt['inner_hashes']!={p.name:base.digest(p) for p in folder.iterdir() if p.is_file()}:
        raise ValueError('policy inner artifact mismatch')
    inner=base.read_json(folder/'run.json'); base._verify_artifacts(folder,inner)
    if (inner['authorization']!=receipt['authorization'] or inner['version']!=base.VERSION
            or inner['frozen']!=base.bindings(package['legacy'])
            or inner['manifest_sha256']!=base.digest(package['legacy']['manifest_path'])
            or inner['sample']!=context['sample']):
        raise ValueError('policy replay legacy version/auth mismatch')
    saved={}
    def invoke(name,messages,schema):
        if base.read_json(folder/'node-body.json')!=base._body(messages,schema): raise ValueError('policy replay new body mismatch')
        if (folder/'node-provider-error.json').exists(): raise base.RecordedProviderError(base.read_json(folder/'node-provider-error.json'))
        call=base.read_json(folder/'node-call.json')
        return AIMessage(content=call['response'],usage_metadata=call['usage'],response_metadata=call['response_metadata'] or {})
    stopped=None
    try: base._run(context,invoke,saved.__setitem__,lambda:None,inner['context_window'])
    except Exception as exc: stopped=base.error_record(exc)
    if stopped!=inner['stopped']: raise ValueError('policy replay legacy first error differs')
    for name,value in saved.items():
        original=base.read_json(folder/name)
        if name.endswith(('-call.json','-provider-error.json')):
            original.pop('elapsed_seconds',None); value.pop('elapsed_seconds',None)
        if original!=value: raise ValueError('policy replay artifact differs: '+name)
    if set(inner['artifact_hashes'])-{'node-managed.json','node-provider-response.json'}!=set(saved):
        raise ValueError('policy replay artifact set differs')
    outcome=_outcome(folder,context,inner)
    if ((receipt['decision'] is not None and receipt['decision']!=outcome['decision'])
            or (receipt['status']=='PASS' and (outcome['status']!='PASS' or receipt['decision'] is None))):
        raise ValueError('policy replay decision differs')
    return dict(result=receipt['status'],replay_verification='PASS',stopped=receipt['stopped'],
        legacy_stopped=stopped,decision=outcome['decision'],raw_replays=int('node-call.json' in saved),provider_calls=0)


def freeze_sources(destination,package=None,review=None):
    package=package or load_package(); _version_guard(package,package['manifest']['bindings'],base.digest(package['manifest_path']))
    destination=rebound.freeze_sources(destination,package['legacy'])
    names={**{name:base.digest(ROOT/name) for name in ADDITIONAL_SOURCES},**REFERENCES,
           DEFAULT_MANIFEST.relative_to(ROOT).as_posix():base.digest(package['manifest_path'])}
    names.update({(DEFAULT_MANIFEST.parent/name).relative_to(ROOT).as_posix():digest for name,digest in package['manifest']['bindings']['inputs'].items()})
    if review is not None:
        authorization=preflight(package,prepare(package),review)
        names.update({e['path']:e['sha256'] for e in authorization['roles']['reviewer']['completion']['evidence'] if _review_proof(e,review)})
    for name,expected in names.items():
        target=destination/name; target.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(ROOT/name,target)
        if base.digest(target)!=expected: raise ValueError('policy frozen source/reference differs')
    base.write_json(destination/'policy-freeze.json',dict(version=VERSION,bindings=bindings(package),files=names,
        manifest_sha256=base.digest(package['manifest_path']),replay_module=__name__))
    return destination


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); group=parser.add_mutually_exclusive_group()
    group.add_argument('--execute',action='store_true'); group.add_argument('--replay',type=Path)
    parser.add_argument('--review',type=Path); parser.add_argument('--ticket')
    args=parser.parse_args(argv); package=load_package()
    if args.replay:
        result=replay(args.replay,package); print(json.dumps(result,ensure_ascii=False)); return int(result['result']!='PASS')
    context=prepare(package)
    if not args.execute:
        print(json.dumps(dict(version=VERSION,execute=False,input_tokens=context['input_tokens'],
            bindings_match=bindings(package)==package['manifest']['bindings'],provider_calls=0),ensure_ascii=False)); return 0
    review=base.read_json(args.review) if args.review else None; auth=preflight(package,context,review)
    _execution_guard(args.ticket)
    settings=base.AssistantSettings.from_env(ROOT/'.env')
    if settings.llm_provider!='ollama': raise ValueError('only local Ollama is authorized')
    os.environ['EDD_LOCAL_ENDPOINT']=settings.llm_base_url.rstrip('/')+'/api/chat'
    identity=base.verify_model_identity(settings.llm_base_url)
    batch=ROOT/base.TASK/'.local'/(CONTENT_VERSION+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid4().hex[:6])
    batch.mkdir(mode=0o700); base.write_json(batch/'policy-review.json',review); freeze_sources(batch/'frozen',package,review=review)
    folder=batch/context['sample']['id']
    invoke=base.ManagedInvoke(folder,args.ticket,context['sample']['request_case'].removesuffix(':node'),
        lambda name,value:base.write_json(folder/name,value))
    receipt=record_sample(folder,context,invoke,mode='MANAGED_LOCAL_ISOLATION',identity=identity,
        authorization=auth,review=review,ticket=args.ticket)
    print(json.dumps(dict(batch=str(batch),status=receipt['status'],stopped=receipt['stopped']),ensure_ascii=False))
    return int(receipt['status']!='PASS')


if __name__=='__main__':
    raise SystemExit(main())
