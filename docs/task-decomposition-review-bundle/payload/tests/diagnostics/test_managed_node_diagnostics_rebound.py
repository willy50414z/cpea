"""Rebinding controls exercise complete outer evidence without provider access."""
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

from langchain_core.messages import AIMessage
import pytest

from evaluations import managed_node_diagnostics as base


def api():
    assert importlib.util.find_spec('evaluations.diagnostics.managed_node_diagnostics_rebound'), 'rebound adapter missing'
    from evaluations.diagnostics import managed_node_diagnostics_rebound
    return managed_node_diagnostics_rebound


def synthetic_review(mod, package, tmp_path):
    roles = [('content_author', package['manifest']['content_author_ticket'], 'kind_diagnostic_fixture_v2_correction', 12),
             ('binding_author', package['manifest']['author_ticket'], 'kind_diagnostic_evidence_rebinding', 13),
             ('reviewer', 'synthetic-fresh-reviewer', 'kind_diagnostic_fixture_semantics', 14)]
    loop = dict(tickets={}, rounds=[])
    for name, ticket, node, number in roles:
        loop['tickets'][ticket] = dict(role='worker', node=node, platform_id='/' + name, round=number, closed=True)
        loop['rounds'].append(dict(round=number, node=node, producer='/' + name, result='PASS'))
    path = tmp_path / 'task.md'
    save_task(path, loop)
    review = dict(schema_version=1, verdict='ACCEPT', reviewer_role='fresh_fixture_semantics',
        ticket=roles[2][1], author_ticket=roles[1][1], content_author_ticket=roles[0][1],
        manifest_sha256=mod.digest(package['manifest_path']), bindings=deepcopy(package['manifest']['bindings']))
    return review, loop, path


def save_task(path, loop):
    path.write_text('---\n' + json.dumps(dict(plan=dict(edd_loop=loop)), ensure_ascii=False) + '\n---\n', encoding='utf-8')


def test_rebound_preserves_content_and_rejects_live_v2_lineage():
    mod = api(); package = mod.load_package()
    from evaluations.diagnostics import managed_node_diagnostics_v2 as old
    with pytest.raises(ValueError, match='lineage'): old.load_package()
    assert package['root'] == base.ROOT / 'evaluations/fixtures/kind_diagnostics_v2'
    assert mod.bindings(package) == package['manifest']['bindings']
    assert len(package['manifest']['bindings']['sources']) == 167
    content = base.read_json(package['root'] / 'manifest.json')
    for sid in base.SAMPLE_IDS:
        context = mod.prepare(package, sid)
        assert context['sample']['request_case'] == 'kind-isolation-v2-rebind-1:ISOLATION:' + sid + ':node'
        assert package['manifest']['bindings']['samples'][sid] == content['bindings']['samples'][sid]
    assert package['manifest']['bindings']['samples']['SEL-ISO-v1-01']['input_tokens'] == 22011
    assert mod.digest(package['root'] / 'manifest.json') == '33cf44c84c10842adb60bfb7cbfbb269bac6dfa136c124a43159efabd27d543f'
    with pytest.raises(ValueError): mod.load_package(package['root'] / 'manifest.json')


@pytest.mark.parametrize('who', ['content_author', 'binding_author', 'reviewer'])
@pytest.mark.parametrize('mutation', ['missing', 'role', 'node', 'platform', 'open', 'round', 'producer', 'FAIL', 'same_platform'])
def test_three_completed_roles_are_required(tmp_path, who, mutation):
    mod = api(); package = mod.load_package(); review, loop, path = synthetic_review(mod, package, tmp_path)
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    assert mod.preflight(package, [context], review, task_path=path)['result'] == 'PASS'
    ids = dict(content_author=package['manifest']['content_author_ticket'], binding_author=package['manifest']['author_ticket'], reviewer=review['ticket'])
    ticket = ids[who]; item = loop['tickets'][ticket]; index = list(ids).index(who)
    if mutation == 'missing': del loop['tickets'][ticket]
    if mutation == 'role': item['role'] = 'research'
    if mutation == 'node': item['node'] = 'root'
    if mutation == 'platform': item['platform_id'] = ''
    if mutation == 'open': item['closed'] = False
    if mutation == 'round': item['round'] += 100
    if mutation == 'producer': loop['rounds'][index]['producer'] = '/forged'
    if mutation == 'FAIL': loop['rounds'][index]['result'] = 'FAIL'
    if mutation == 'same_platform': item['platform_id'] = '/binding_author' if who != 'binding_author' else '/content_author'
    save_task(path, loop)
    with pytest.raises(ValueError, match='provenance'): mod.preflight(package, [context], review, task_path=path)


@pytest.mark.parametrize('mutation', ['missing', 'reject', 'old_review', 'manifest', 'new_source', 'new_test', 'lineage', 'content', 'fixture', 'model', 'runtime', 'sample', 'count', 'context', 'body', 'schema', 'actual_schema', 'messages', 'recall', 'coverage', 'oracle'])
def test_complete_review_and_input_guard_rejects_every_drift(tmp_path, mutation):
    mod = api(); package = deepcopy(mod.load_package()); review, _, path = synthetic_review(mod, package, tmp_path)
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    if mutation == 'missing': review = None
    if mutation == 'reject': review['verdict'] = 'REJECT'
    if mutation == 'old_review': review = base.read_json(base.ROOT / 'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-diagnostic-semantics/review.json')
    if mutation == 'manifest': review['manifest_sha256'] = '0' * 64
    if mutation in ['new_source', 'new_test']:
        review['bindings']['sources'].pop('evaluations/diagnostics/managed_node_diagnostics_rebound.py' if mutation == 'new_source' else 'tests/diagnostics/test_managed_node_diagnostics_rebound.py')
    if mutation == 'lineage': review['bindings']['lineage'].pop(next(iter(mod.LINEAGE)))
    if mutation == 'content': package['manifest']['content_manifest']['sha256'] = '0' * 64
    if mutation == 'fixture': package['manifest']['bindings']['fixtures']['oracle.json'] = '0' * 64
    if mutation == 'model': package['manifest']['bindings']['model']['digest'] = '0' * 64
    if mutation == 'runtime': package['manifest']['bindings']['runtime']['python'] = 'forged'
    if mutation == 'sample': context['sample']['role'] = 'PARENT_NATURAL'
    if mutation == 'count': context['sample']['count'] = 2
    if mutation == 'context': context['input_tokens'] = 32768
    if mutation == 'body': context['body']['messages'].append(dict(role='system', content='Oracle answer'))
    if mutation == 'schema': context['schema_json']['additionalProperties'] = True
    if mutation == 'actual_schema': context['schema'] = base.contract.RecallWire
    if mutation == 'messages': context['messages'][1].content = '{}'
    if mutation == 'recall': context['recall'].requirements.pop()
    if mutation == 'coverage': context['coverages'].pop()
    if mutation == 'oracle': package['oracle']['positive_outputs']['COV-ISO-v1-01']['entries']['MET-001']['own_gap'] = False
    with pytest.raises(ValueError): mod.preflight(package, [context], review, task_path=path)


@pytest.mark.parametrize('sample', base.SAMPLE_IDS)
def test_explicit_engine_keeps_outer_version_raw_and_same_version_replay(tmp_path, sample):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, sample)
    raw = json.dumps(package['oracle']['positive_outputs'][sample], ensure_ascii=False)
    folder = tmp_path / sample
    outer = mod.record_sample(folder, context, lambda *args: AIMessage(content=raw))
    inner = base.read_json(folder / 'run.json')
    assert outer['status'] == 'PASS' and outer['stopped'] is None
    assert inner['version'] == 'managed-node-diagnostics-1' and len(inner['frozen']['sources']) == 163
    assert len(outer['bindings']['sources']) == 167 and outer['version'] == 'managed-node-diagnostics-rebind-1'
    assert inner['authorization'] == outer['authorization']
    assert mod.replay(folder, package)['result'] == 'PASS'
    assert base.read_json(folder / 'node-call.json')['response'] == raw
    assert mod.receipt_path(folder).parent == folder.parent
    if sample.startswith('SEL'): assert len(base.read_json(folder / 'response.json')['prepared_requests']) == 2
    with pytest.raises(ValueError, match='empty'): mod.record_sample(folder, context, lambda *args: None)


@pytest.mark.parametrize('failure', ['provider', 'context', 'parse', 'predicate', 'own', 'typed', 'null', 'duplicate', 'nan', 'semantic', 'leap'])
def test_outer_preserves_all_first_error_prefixes(tmp_path, failure):
    mod = api(); package = mod.load_package()
    sid = 'SEL-ISO-v1-01' if failure in ['typed', 'null'] else 'COV-ISO-v1-03' if failure == 'leap' else 'COV-ISO-v1-01'
    context = mod.prepare(package, sid); value = deepcopy(package['oracle']['positive_outputs'][sid])
    if failure == 'predicate': value['entries']['FILT-001']['mappings'][0].pop('value')
    if failure == 'own': value['entries']['MET-001']['own_gap'] = False
    if failure == 'typed': value['draft']['tasks'][0].pop('filters')
    if failure == 'null': value['draft']['integration'] = None
    if failure == 'semantic': value['entries']['GRN-001'].update(status='unsupported', mappings=[], own_gap=True)
    if failure == 'leap': value['entries']['月~邊界']['mappings'][1]['value'] = '2032-02-28'
    raw = dict(parse='not JSON', duplicate='{"entries":{},"entries":{}}', nan='{"entries":{"x":NaN}}').get(failure, json.dumps(value, ensure_ascii=False))
    def invoke(*args):
        if failure == 'provider': raise OSError('offline transport failure')
        return AIMessage(content=raw)
    folder = tmp_path / 'run'
    outer = mod.record_sample(folder, context, invoke, context_window=1 if failure == 'context' else 32768)
    assert outer['status'] == 'FAIL' and outer['stopped']
    assert (folder / 'node-call.json').exists() == (failure not in ['provider', 'context'])
    replay = mod.replay(folder, package)
    assert replay['result'] == 'FAIL' and replay['stopped'] == outer['stopped'] and replay['replay_verification'] == 'PASS'


def test_interrupted_outer_and_tampered_authorization_cannot_become_pass(tmp_path):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, 'COV-ISO-v1-02')
    def interrupt(*args): raise KeyboardInterrupt('offline interruption')
    folder = tmp_path / 'interrupted'
    with pytest.raises(KeyboardInterrupt): mod.record_sample(folder, context, interrupt)
    assert base.read_json(mod.receipt_path(folder))['status'] == 'INTERRUPTED'
    with pytest.raises(ValueError, match='interrupted'): mod.replay(folder, package)
    raw = json.dumps(package['oracle']['positive_outputs']['COV-ISO-v1-02'], ensure_ascii=False)
    folder = tmp_path / 'complete'; mod.record_sample(folder, context, lambda *args: AIMessage(content=raw))
    receipt = base.read_json(mod.receipt_path(folder)); receipt['authorization']['manifest_sha256'] = '0' * 64
    base.write_json(mod.receipt_path(folder), receipt)
    with pytest.raises(ValueError, match='receipt'): mod.replay(folder, package)


def test_real_task_remains_unapproved_and_dry_runs_are_offline(capsys, tmp_path):
    mod = api(); package = mod.load_package(); review, _, _ = synthetic_review(mod, package, tmp_path)
    with pytest.raises(ValueError, match='provenance'): mod.preflight(package, [mod.prepare(package, 'SEL-ISO-v1-01')], review)
    for stage, size in [('selection', 1), ('coverage', 3)]:
        assert mod.main(['--stage', stage]) == 0
        result = json.loads(capsys.readouterr().out)
        assert len(result['samples']) == size and result['provider_calls'] == 0 and result['bindings_match']
    with pytest.raises(ValueError, match='review'): mod.main(['--execute', '--ticket', 'unused'])


def test_outer_receipt_drift_after_raw_cannot_be_overwritten_as_pass(tmp_path):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, 'COV-ISO-v1-02')
    folder = tmp_path / 'run'
    raw = json.dumps(package['oracle']['positive_outputs']['COV-ISO-v1-02'], ensure_ascii=False)
    def drift(*args):
        path = mod.receipt_path(folder); receipt = base.read_json(path)
        receipt['version'] = 'forged'
        base.write_json(path, receipt)
        return AIMessage(content=raw)
    outer = mod.record_sample(folder, context, drift)
    assert outer['status'] == 'FAIL', 'outer receipt drift was silently overwritten'
    assert base.read_json(folder / 'run.json')['stopped'] is None
    assert base.read_json(folder / 'node-call.json')['response'] == raw
    assert mod.replay(folder, package)['result'] == 'FAIL'


@pytest.mark.parametrize('mutation', ['none', 'node', 'closed', 'round', 'audit', 'status', 'unbound'])
def test_execute_requires_active_stage_worker_and_completed_audit(tmp_path, mutation):
    mod = api()
    assert hasattr(mod, '_execution_guard'), 'active-stage execution guard missing'
    loop = dict(status='RUNNING', audit_due=False, needs_research=False,
        active=dict(node='natural_kind_selection_isolation', round=15), tickets={
            'selection-worker': dict(role='worker', node='natural_kind_selection_isolation', round=15, closed=False, platform_id='/selection')})
    item = loop['tickets']['selection-worker']
    if mutation == 'node': item['node'] = 'kind_diagnostic_fixture_semantics'
    if mutation == 'closed': item['closed'] = True
    if mutation == 'round': item['round'] = 14
    if mutation == 'audit': loop['audit_due'] = True
    if mutation == 'status': loop['status'] = 'NEEDS_USER'
    if mutation == 'unbound': item['platform_id'] = ''
    path = tmp_path / 'task.md'; save_task(path, loop)
    if mutation == 'none': mod._execution_guard('selection-worker', 'selection', task_path=path)
    else:
        with pytest.raises(ValueError, match='active'): mod._execution_guard('selection-worker', 'selection', task_path=path)


def test_full_frozen_replay_and_outer_only_drift_preserve_inner_raw(tmp_path):
    mod = api(); package = mod.load_package(); bound = mod.bindings(package)
    frozen = mod.freeze_sources(tmp_path / 'frozen', package)
    for group in ['sources', 'lineage', 'historical_fixtures']:
        for name, expected in bound[group].items(): assert mod.digest(frozen / name) == expected
    assert mod.digest(frozen / 'evaluations/fixtures/kind_diagnostics_rebound/manifest.json') == mod.digest(package['manifest_path'])
    assert (frozen / '_external/edd/ledger.py').is_file()
    script = '''import json
from pathlib import Path
from langchain_core.messages import AIMessage
from evaluations.diagnostics import managed_node_diagnostics_rebound as m
p=m.load_package()
out=Path(__import__('sys').argv[1])
for i,name in enumerate(['evaluations/fixtures/kind_diagnostics_v2/manifest.json', 'evaluations/fixtures/kind_diagnostics_v2/oracle.json', 'tests/diagnostics/test_managed_node_diagnostics_rebound.py', next(iter(m.LINEAGE))]):
 target=m.ROOT/name; original=target.read_bytes(); target.write_bytes(original+b'\\n')
 try:
  try: m.record_sample(out/('preflight-drift-'+str(i)),m.prepare(p,'COV-ISO-v1-02'),lambda *a:(_ for _ in ()).throw(AssertionError('invoke reached')))
  except ValueError: pass
  else: raise AssertionError('drift accepted: '+name)
 finally: target.write_bytes(original)
for sid in m.base.SAMPLE_IDS:
 c=m.prepare(p,sid); raw=json.dumps(p['oracle']['positive_outputs'][sid],ensure_ascii=False)
 f=out/sid; r=m.record_sample(f,c,lambda *a:AIMessage(content=raw)); assert r['status']=='PASS'; assert m.replay(f,p)['result']=='PASS'
c=m.prepare(p,'COV-ISO-v1-02'); raw=json.dumps(p['oracle']['positive_outputs']['COV-ISO-v1-02'],ensure_ascii=False)
source=Path(m.__file__); original=source.read_bytes()
def drift(*a):
 source.write_bytes(original+b'\\n'); return AIMessage(content=raw)
f=out/'outer-drift'
try:
 r=m.record_sample(f,c,drift)
 assert r['status']=='FAIL'; assert m.base.read_json(f/'run.json')['stopped'] is None
 assert m.base.read_json(f/'node-call.json')['response']==raw
finally: source.write_bytes(original)
r=m.replay(f,p); assert r['result']=='FAIL' and r['inner']['result']=='PASS'
print(json.dumps(dict(four_positive_frozen_replays='PASS',outer_drift_raw_preserved=True,outer_result=r['result'],inner_result=r['inner']['result'],provider_calls=0)))
'''
    env = dict(os.environ, PYTHONPATH=str(frozen / 'src') + ':' + str(frozen), PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, '-c', script, str(tmp_path / 'runs')], cwd=frozen, env=env, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert json.loads(proc.stdout)['outer_result'] == 'FAIL'
