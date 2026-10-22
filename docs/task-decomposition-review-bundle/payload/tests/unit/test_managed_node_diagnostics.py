"""Offline isolation exercises real contracts; no inference or database access."""
from copy import deepcopy
import importlib
import importlib.util
import json
from pathlib import Path

from langchain_core.messages import AIMessage
import pytest


def api():
    assert importlib.util.find_spec('evaluations.managed_node_diagnostics'), 'isolation runner missing'
    return importlib.import_module('evaluations.managed_node_diagnostics')


def test_fixed_upstream_preserves_useful_unselected_capabilities_and_two_prepared():
    mod = api()
    package = mod.load_package()
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    assert len(context['recall'].requirements) == 8
    assert len(context['coverages']) == 7
    assert sum(len(c.entries) for c in context['coverages']) == 56
    rows = {c.view: {e.requirement_id: e for e in c.entries} for c in context['coverages']}
    daily = rows['demo_retail.v_daily_sales']
    assert daily['GRN-001'].status == 'partial'
    assert [m.column for m in daily['GRN-001'].mappings] == ['store_id']
    assert daily['MET-003'].status == 'partial'
    assert [json.loads(g)['aspect'] for g in daily['MET-003'].missing_requirements] == ['scope', 'grain']
    assert len(package['oracle']['coverage_evidence']) == 56
    result = mod.evaluate(context, json.dumps(package['oracle']['selection_positive'], ensure_ascii=False))
    assert result['response']['status'] == 'ready'
    assert len(result['response']['prepared_requests']) == 2
    assert result['semantic']['machine_verdict'] == 'PASS'
    assert result['semantic']['independent_semantic_approval'] == 'PENDING'


@pytest.mark.parametrize('sample', ['COV-ISO-v1-01', 'COV-ISO-v1-02', 'COV-ISO-v1-03', 'SEL-ISO-v1-01'])
def test_record_replay_preserves_raw_presence_compilation_and_injected_provenance(tmp_path, sample):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, sample)
    positive = package['oracle']['positive_outputs'][sample]
    raw = json.dumps(positive, ensure_ascii=False)
    folder = tmp_path / sample
    meta = mod.record_sample(folder, context, lambda *args: AIMessage(content=raw,
        usage_metadata=dict(input_tokens=10, output_tokens=20, total_tokens=30)))
    assert meta['stopped'] is None and meta['upstream_injected'] is True
    assert json.loads((folder / 'node-call.json').read_text(encoding='utf-8'))['response'] == raw
    assert (folder / 'node-presence.json').exists() and (folder / 'node-refs.json').exists()
    assert (folder / 'node-parsed.json').exists() and (folder / 'node-normalized.json').exists()
    assert mod.replay(folder, package)['result'] == 'PASS'
    if sample.endswith('03'):
        assert context['catalog'].profile_id == 'kind_diag_renamed_v1'
        entries = positive['entries']
        assert entries['月~邊界']['mappings'] == [dict(column='day_key', operator='>=', value='2032-02-01'),
                                                  dict(column='day_key', operator='<', value='2032-03-01')]
        assert entries['amount/net']['own_gap'] is False
    with pytest.raises(ValueError, match='empty'):
        mod.record_sample(folder, context, lambda *args: pytest.fail('overwrote raw'))


@pytest.mark.parametrize('failure', ['provider', 'parse', 'predicate', 'own', 'typed', 'null', 'duplicate', 'nan'])
def test_first_failure_is_saved_and_replayed_without_repair(tmp_path, failure):
    mod = api(); package = mod.load_package()
    sample = 'SEL-ISO-v1-01' if failure in ('typed', 'null') else 'COV-ISO-v1-01'
    context = mod.prepare(package, sample)
    value = deepcopy(package['oracle']['positive_outputs'][sample])
    if failure == 'predicate': value['entries']['FILT-001']['mappings'][0].pop('value')
    if failure == 'own': value['entries']['MET-001']['own_gap'] = False
    if failure == 'typed': value['draft']['tasks'][0].pop('filters')
    if failure == 'null': value['draft']['integration'] = None
    raw = 'no JSON' if failure == 'parse' else '{"entries":{},"entries":{}}' if failure == 'duplicate' else '{"entries":{"x":NaN}}' if failure == 'nan' else json.dumps(value, ensure_ascii=False)
    def invoke(*args):
        if failure == 'provider': raise OSError('offline transport failed')
        return AIMessage(content=raw)
    meta = mod.record_sample(tmp_path, context, invoke)
    assert meta['stopped'] and (tmp_path / 'node-error.json').exists()
    assert not (tmp_path / 'node-normalized.json').exists()
    if failure != 'provider':
        assert json.loads((tmp_path / 'node-call.json').read_text(encoding='utf-8'))['response'] == raw
    assert mod.replay(tmp_path, package)['stopped'] == meta['stopped']


@pytest.mark.parametrize('mutation', ['omit_key', 'complete_key', 'customer_key', 'wrong_month', 'one_boundary', 'own_net', 'population'])
def test_semantic_controls_never_promote_structural_acceptance_to_correctness(mutation):
    mod = api(); package = mod.load_package()
    sample = 'COV-ISO-v1-02' if mutation == 'customer_key' else 'COV-ISO-v1-01'
    context = mod.prepare(package, sample)
    value = deepcopy(package['oracle']['positive_outputs'][sample])
    rows = value['entries']
    if mutation == 'omit_key': rows['GRN-001'].update(status='unsupported', mappings=[], own_gap=True)
    if mutation == 'complete_key':
        rows['GRN-001'].update(status='supported', own_gap=False)
    if mutation == 'customer_key': rows['unrelated/識別~鍵'].update(status='partial', mappings=[dict(column='customer_id')])
    if mutation == 'wrong_month': rows['FILT-001']['mappings'][1]['value'] = '2026-09-30'
    if mutation == 'one_boundary': rows['FILT-001']['mappings'].pop()
    if mutation == 'own_net': rows['MET-003']['own_gap'] = True
    if mutation == 'population': rows['POP-001'].update(status='partial', mappings=[dict(column='store_id')], contract_path='/summary')
    result = mod.evaluate(context, json.dumps(value, ensure_ascii=False))
    assert result['semantic']['machine_verdict'] == 'FAIL'
    assert result['semantic']['classification'] == 'SEMANTIC_REJECT'
    assert result['normalized']  # the existing parser/guard actually accepts these


def test_dry_run_and_execute_rejection_never_construct_provider(monkeypatch, capsys, tmp_path):
    mod = api()
    monkeypatch.setattr(mod, 'ManagedInvoke', lambda *a, **k: pytest.fail('provider constructed'))
    monkeypatch.setattr(mod, 'verify_model_identity', lambda *a: pytest.fail('network used'))
    assert mod.main(['--stage', 'selection']) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['execute'] is False and result['samples'] == ['SEL-ISO-v1-01']
    assert mod.main(['--stage', 'coverage']) == 0
    assert json.loads(capsys.readouterr().out)['samples'] == ['COV-ISO-v1-01', 'COV-ISO-v1-02', 'COV-ISO-v1-03']
    with pytest.raises(ValueError, match='review'):
        mod.main(['--stage', 'selection', '--execute', '--ticket', 'test'])


def accepted_offline_review(mod, package, tmp_path, monkeypatch):
    """Synthetic controller evidence exercises preflight, never a fixture approval."""
    author = package['manifest']['author_ticket']; reviewer = 'fresh-semantic-review'
    review = dict(schema_version=1, verdict='ACCEPT', reviewer_role='fresh_fixture_semantics',
        ticket=reviewer, author_ticket=author, manifest_sha256=mod.digest(package['manifest_path']),
        bindings=deepcopy(package['manifest']['bindings']))
    task = dict(plan=dict(edd_loop=dict(tickets={author:dict(platform_id='/author'),
        reviewer:dict(role='worker', node='kind_diagnostic_fixture_semantics', platform_id='/reviewer', round=11, closed=True)},
        rounds=[dict(round=11,node='kind_diagnostic_fixture_semantics',producer='/reviewer',result='PASS')])))
    (tmp_path / 'task.md').write_text('---\n'+json.dumps(task, ensure_ascii=False)+'\n---\n', encoding='utf-8')
    monkeypatch.setattr(mod, 'TASK', tmp_path)
    return review, task


@pytest.mark.parametrize('mutation', ['missing', 'reject', 'self_review', 'manifest', 'binding', 'context', 'body', 'schema', 'source', 'fixture', 'omitted_view', 'messages', 'recall', 'actual_schema'])
def test_execute_preflight_refuses_any_unreviewed_or_drifted_input(tmp_path, mutation, monkeypatch):
    mod = api(); package = mod.load_package()
    review, _ = accepted_offline_review(mod, package, tmp_path, monkeypatch)
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    if mutation == 'missing': review = None
    elif mutation == 'reject': review['verdict'] = 'REJECT'
    elif mutation == 'self_review': review['ticket'] = package['manifest']['author_ticket']
    elif mutation == 'manifest': review['manifest_sha256'] = '0' * 64
    elif mutation == 'binding': review['bindings'].pop(next(iter(review['bindings'])))
    elif mutation == 'context': context['input_tokens'] = 32768
    elif mutation == 'body': context['body']['think'] = False
    elif mutation == 'schema': context['schema_json']['additionalProperties'] = True
    elif mutation == 'source': package['manifest']['bindings']['sources']['evaluations/managed_node_diagnostics.py'] = '0' * 64
    elif mutation == 'fixture': package['manifest']['bindings']['fixtures']['request-original.txt'] = '0' * 64
    elif mutation == 'omitted_view': context['coverages'].pop()
    elif mutation == 'messages': context['messages'][1].content = '{}'
    elif mutation == 'recall': context['recall'].requirements.pop()
    elif mutation == 'actual_schema': context['schema'] = mod.contract.RecallWire
    with pytest.raises(ValueError): mod.preflight(package, [context], review)


def test_frozen_replay_and_artifact_drift_are_enforced(tmp_path):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, 'COV-ISO-v1-03')
    raw = json.dumps(package['oracle']['positive_outputs'][context['sample']['id']], ensure_ascii=False)
    folder = tmp_path / 'run'
    meta = mod.record_sample(folder, context, lambda *a: AIMessage(content=raw))
    assert meta['stopped'] is None
    frozen = mod.freeze_sources(tmp_path / 'frozen', package)
    assert (frozen / 'evaluations/managed_node_diagnostics.py').is_file()
    assert (frozen / 'src/cpea/infrastructure/catalog/yaml_catalog.py').is_file()
    assert (frozen / '_external/edd/ledger.py').is_file()
    assert (frozen / '_external/loopctl.py').is_file()
    assert mod.replay(folder, package)['result'] == 'PASS'
    (folder / 'node-call.json').write_text('{}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact'): mod.replay(folder, package)


def test_execute_preflight_accepts_only_different_bound_completed_semantic_worker(tmp_path, monkeypatch):
    mod = api(); package = mod.load_package()
    review, task = accepted_offline_review(mod, package, tmp_path, monkeypatch)
    path = tmp_path / 'task.md'
    def save(): path.write_text('---\n'+json.dumps(task, ensure_ascii=False)+'\n---\n', encoding='utf-8')
    save()
    contexts = [mod.prepare(package, 'SEL-ISO-v1-01')]
    assert mod.preflight(package, contexts, review)['result'] == 'PASS'
    task['plan']['edd_loop']['rounds'][0]['result'] = 'FAIL'; save()
    with pytest.raises(ValueError, match='provenance'): mod.preflight(package, contexts, review)


@pytest.mark.parametrize('mutation', ['cross_scope','stock_sales_scope','request_only','anchor','inner','wrong_key','erase_key','zero','missing_metadata','nonready','free_text'])
def test_selection_negative_controls_reject_instead_of_inventing_typed_answers(mutation):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, 'SEL-ISO-v1-01')
    value = deepcopy(package['oracle']['selection_positive'])
    stock, sales = value['draft']['tasks']; integration = value['draft']['integration']
    if mutation == 'cross_scope': stock['filters'], sales['filters'] = sales['filters'], []
    if mutation == 'stock_sales_scope': stock['filters'] = deepcopy(sales['filters'])
    if mutation == 'request_only': sales['filters'] = []; sales['metrics'] = {}
    if mutation == 'anchor': integration['anchor_task'] = sales['task_id']
    if mutation == 'inner': integration['edges'][0]['mode'] = 'inner'
    if mutation == 'wrong_key': integration['edges'][0]['right_keys'] = ['store_id','order_id']
    if mutation == 'erase_key': sales['group_by'] = ['store_id']; sales['output_grain'] = ['store_id']
    if mutation == 'zero': integration['missing_data_policy'] = '缺值一律補零'
    if mutation == 'missing_metadata': stock.pop('metadata_collections')
    if mutation == 'nonready':
        value['draft'].update(status='unsupported',tasks=[],integration=None,unsupported_reasons=['無能力'])
    if mutation == 'free_text': sales['request'] = '此來源保證所有未交易庫存都有一列且缺值為0'
    try:
        result = mod.evaluate(context, json.dumps(value, ensure_ascii=False))
    except ValueError:
        return  # existing guard rejects the original raw, without changes
    if mutation == 'free_text':
        assert result['semantic']['independent_semantic_approval'] == 'PENDING'
        assert 'PENDING' in result['semantic']['free_text_review']
    else:
        assert result['semantic']['machine_verdict'] == 'FAIL'
