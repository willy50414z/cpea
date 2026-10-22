"""Offline v2 boundary controls; synthetic provenance stays inside tmp_path."""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys

from langchain_core.messages import AIMessage
import pytest

from evaluations import managed_node_diagnostics as base


def api():
    from evaluations.diagnostics import managed_node_diagnostics_v2
    return managed_node_diagnostics_v2


CUSTOMER = 'demo_retail.v_customer_value'
ROW = dict(status='partial', own_gap=True,
    mappings=[dict(column='lifetime_spend', aggregation='sum', conditions=[])],
    contract_path='/columns/lifetime_spend/description')


def customer_context(mod, package):
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    # The customer contrast deliberately tests grain only. For this offline
    # control, use the original eight requirements and the real customer policy.
    context['sample'] = dict(id='customer-eight-offline', stage='coverage', view=CUSTOMER)
    context['schema'] = base.contract.coverage_schema(context['recall'])
    context['schema_json'] = context['schema'].model_json_schema()
    context['package'] = deepcopy(package)
    context['package']['oracle']['positive_outputs']['customer-eight-offline'] = deepcopy(
        base.read_json(package['root'] / 'coverage-selection.json')[CUSTOMER])
    return context


def test_fixture_keeps_useful_member_amount_and_separate_self_scope_grain_gaps():
    mod = api(); package = mod.load_package()
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    coverage = next(c for c in context['coverages'] if c.view == CUSTOMER)
    row = next(e for e in coverage.entries if e.requirement_id == 'MET-003')
    assert row.status == 'partial', 'useful member amount was dropped'
    assert [(m.column, m.aggregation) for m in row.mappings] == [('lifetime_spend', 'sum')]
    gaps = [json.loads(g) for g in row.missing_requirements]
    assert [(g['aspect'], [(r['requirement_id'], r['status']) for r in g['requirements']]) for g in gaps] == [
        ('self', [('MET-003', 'partial')]),
        ('scope', [('FILT-001', 'unsupported'), ('FILT-002', 'unsupported')]),
        ('grain', [('GRN-001', 'unsupported')])]
    evidence = next(e for e in row.contract_evidence if e.path == '/columns/lifetime_spend/description')
    assert evidence.quote == '會員在累計折扣後消費金額，單位 TWD'


@pytest.mark.parametrize('mutation', ['unsupported', 'uncertain', 'own_false'])
def test_original_omission_and_partial_without_self_are_structural_accept_semantic_fail(mutation):
    mod = api(); package = mod.load_package(); context = customer_context(mod, package)
    value = deepcopy(context['package']['oracle']['positive_outputs']['customer-eight-offline'])
    value['entries']['MET-003'] = deepcopy(ROW)
    if mutation in ['unsupported', 'uncertain']:
        value['entries']['MET-003'].update(status=mutation, mappings=[], own_gap=True, contract_path=None)
    else:
        value['entries']['MET-003']['own_gap'] = False
    result = mod.evaluate(context, json.dumps(value, ensure_ascii=False))
    assert result['normalized'], 'parser acceptance must remain visible'
    assert result['semantic']['machine_verdict'] == 'FAIL', 'fixture Oracle failed to reject dropped capability/self'
    assert result['semantic']['independent_semantic_approval'] == 'PENDING'
    if mutation == 'own_false':
        assert [f['aspect'] for f in result['semantic']['findings']] == ['status/own_gap']
        row = next(r for r in result['normalized']['entries'] if r['requirement_id'] == 'MET-003')
        assert [json.loads(g)['aspect'] for g in row['missing_requirements']] == ['scope', 'grain']


def test_other_55_rows_three_controls_and_selected_typed_answer_do_not_change():
    mod = api(); package = mod.load_package(); old = base.load_package()
    wires = base.read_json(package['root'] / 'coverage-selection.json')
    prior = base.read_json(old['root'] / 'coverage-selection.json')
    differences = [(view, rid) for view in prior for rid in prior[view]['entries']
                   if wires[view]['entries'][rid] != prior[view]['entries'][rid]]
    assert differences == [(CUSTOMER, 'MET-003')]
    assert wires[CUSTOMER]['entries']['MET-003'] == ROW
    for sid in base.SAMPLE_IDS:
        assert package['oracle']['positive_outputs'][sid] == old['oracle']['positive_outputs'][sid]
    assert package['oracle']['selection_requirements'] == old['oracle']['selection_requirements']
    assert package['oracle']['selection_positive'] == old['oracle']['selection_positive']
    changed = [(a['view'], a['requirement_id']) for a, b in zip(package['oracle']['coverage_evidence'], old['oracle']['coverage_evidence']) if a != b]
    assert changed == [(CUSTOMER, 'MET-003')]
    result = mod.evaluate(mod.prepare(package, 'SEL-ISO-v1-01'), json.dumps(package['oracle']['selection_positive'], ensure_ascii=False))
    assert result['semantic']['machine_verdict'] == 'PASS'
    assert len(result['response']['prepared_requests']) == 2
    assert len(result['parsed']['assignments']) == 8 and len(result['parsed']['exclusions']) == 5


def review_task(mod, package, tmp_path):
    author = package['manifest']['author_ticket']; reviewer = 'synthetic-reviewer'
    review = dict(schema_version=1, verdict='ACCEPT', reviewer_role='fresh_fixture_semantics', ticket=reviewer,
        author_ticket=author, manifest_sha256=mod.digest(package['manifest_path']), bindings=deepcopy(package['manifest']['bindings']))
    task = dict(plan=dict(edd_loop=dict(tickets={
        author: dict(role='worker', node='kind_diagnostic_fixture_v2_correction', platform_id='/author', round=12, closed=True),
        reviewer: dict(role='worker', node='kind_diagnostic_fixture_semantics', platform_id='/reviewer', round=13, closed=True)}, rounds=[
        dict(round=12, node='kind_diagnostic_fixture_v2_correction', producer='/author', result='PASS'),
        dict(round=13, node='kind_diagnostic_fixture_semantics', producer='/reviewer', result='PASS') ])))
    path = tmp_path / 'task.md'
    save_task(path, task)
    return review, task, path


def save_task(path, task):
    path.write_text('---\n' + json.dumps(task, ensure_ascii=False) + '\n---\n', encoding='utf-8')


@pytest.mark.parametrize('who', ['author', 'reviewer'])
@pytest.mark.parametrize('mutation', ['missing', 'role', 'node', 'unbound', 'open', 'round', 'producer', 'failed', 'same_platform'])
def test_provenance_rejects_incomplete_wrong_or_forged_controller_records(tmp_path, who, mutation):
    mod = api(); package = mod.load_package(); review, task, path = review_task(mod, package, tmp_path)
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    assert mod.preflight(package, [context], review, task_path=path)['result'] == 'PASS'
    loop = task['plan']['edd_loop']; ticket = package['manifest']['author_ticket'] if who == 'author' else review['ticket']
    item = loop['tickets'][ticket]; index = 0 if who == 'author' else 1
    if mutation == 'missing': del loop['tickets'][ticket]
    if mutation == 'role': item['role'] = 'research'
    if mutation == 'node': item['node'] = 'kind_diagnostic_fixture_v2_correction' if who == 'reviewer' else 'kind_diagnostic_fixture_semantics'
    if mutation == 'unbound': item['platform_id'] = ''
    if mutation == 'open': item['closed'] = False
    if mutation == 'round': loop['rounds'][index]['round'] += 100
    if mutation == 'producer': loop['rounds'][index]['producer'] = '/forged'
    if mutation == 'failed': loop['rounds'][index]['result'] = 'FAIL'
    if mutation == 'same_platform': item['platform_id'] = '/reviewer' if who == 'author' else '/author'
    save_task(path, task)
    with pytest.raises(ValueError, match='provenance'):
        mod.preflight(package, [context], review, task_path=path)


@pytest.mark.parametrize('mutation', ['missing', 'reject', 'v1_reject', 'manifest', 'binding', 'self', 'context', 'body', 'schema', 'messages', 'recall', 'omitted_view', 'source', 'fixture', 'oracle', 'model', 'actual_schema', 'sample'])
def test_preflight_refuses_unreviewed_drifted_or_oracle_contaminated_inputs(tmp_path, mutation):
    mod = api(); package = mod.load_package(); review, _, path = review_task(mod, package, tmp_path)
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    if mutation == 'missing': review = None
    if mutation == 'reject': review['verdict'] = 'REJECT'
    if mutation == 'v1_reject': review = base.read_json(base.ROOT / 'evidence-driven-dev/tasks/ollama-planning-mvp/agents/loop-worker-diagnostic-semantics/review.json')
    if mutation == 'manifest': review['manifest_sha256'] = '0' * 64
    if mutation == 'binding': review['bindings']['sources'].pop('evaluations/diagnostics/managed_node_diagnostics_v2.py')
    if mutation == 'self': review['ticket'] = review['author_ticket']
    if mutation == 'context': context['input_tokens'] = 32768
    if mutation == 'body': context['body']['messages'].append(dict(role='system', content='Oracle answer'))
    if mutation == 'schema': context['schema_json']['additionalProperties'] = True
    if mutation == 'messages': context['messages'][1].content = '{}'
    if mutation == 'recall': context['recall'].requirements.pop()
    if mutation == 'omitted_view': context['coverages'].pop()
    if mutation == 'source': package['manifest']['bindings']['sources']['evaluations/diagnostics/managed_node_diagnostics_v2.py'] = '0' * 64
    if mutation == 'fixture': package['manifest']['bindings']['fixtures']['oracle.json'] = '0' * 64
    if mutation == 'oracle': package['oracle']['positive_outputs']['COV-ISO-v1-01']['entries']['MET-001']['own_gap'] = False
    if mutation == 'model': package['manifest']['bindings']['model']['digest'] = '0' * 64
    if mutation == 'actual_schema': context['schema'] = base.contract.RecallWire
    if mutation == 'sample': context['sample']['role'] = 'PARENT_NATURAL'
    with pytest.raises(ValueError): mod.preflight(package, [context], review, task_path=path)


@pytest.mark.parametrize('sample', base.SAMPLE_IDS)
def test_all_fixed_samples_record_replay_and_v2_case_identity(tmp_path, sample):
    mod = api(); package = mod.load_package(); context = mod.prepare(package, sample)
    raw = json.dumps(package['oracle']['positive_outputs'][sample], ensure_ascii=False)
    meta = mod.record_sample(tmp_path / 'run', context, lambda *a: AIMessage(content=raw))
    assert meta['stopped'] is None
    assert meta['version'] == 'managed-node-diagnostics-2'
    assert meta['sample']['request_case'] == 'kind-isolation-v2:ISOLATION:' + sample + ':node'
    assert mod.replay(tmp_path / 'run', package)['result'] == 'PASS'
    assert base.read_json(tmp_path / 'run/node-call.json')['response'] == raw
    with pytest.raises(ValueError, match='empty'): mod.record_sample(tmp_path / 'run', context, lambda *a: None)


@pytest.mark.parametrize('failure', ['provider', 'context', 'parse', 'own', 'typed', 'null', 'duplicate', 'nan', 'semantic'])
def test_failure_prefix_is_saved_and_replayed_without_repair(tmp_path, failure):
    mod = api(); package = mod.load_package()
    sample = 'SEL-ISO-v1-01' if failure in ['typed', 'null'] else 'COV-ISO-v1-01'
    context = mod.prepare(package, sample); value = deepcopy(package['oracle']['positive_outputs'][sample])
    if failure == 'own': value['entries']['MET-001']['own_gap'] = False
    if failure == 'typed': value['draft']['tasks'][0].pop('filters')
    if failure == 'null': value['draft']['integration'] = None
    if failure == 'semantic': value['entries']['GRN-001'].update(status='unsupported', mappings=[], own_gap=True)
    raw = {'parse': 'no JSON', 'duplicate': '{"entries":{},"entries":{}}', 'nan': '{"entries":{"x":NaN}}'}.get(failure, json.dumps(value, ensure_ascii=False))
    calls = []
    def invoke(*args):
        calls.append(args)
        if failure == 'provider': raise OSError('offline transport failure')
        return AIMessage(content=raw)
    meta = mod.record_sample(tmp_path, context, invoke, context_window=1 if failure == 'context' else 32768)
    assert meta['stopped']
    assert len(calls) == (0 if failure == 'context' else 1)
    assert (tmp_path / 'node-call.json').exists() == (failure not in ['provider', 'context'])
    assert (tmp_path / 'node-normalized.json').exists() == (failure == 'semantic')
    assert mod.replay(tmp_path, package)['stopped'] == meta['stopped']


def test_full_source_freeze_binds_adapter_tests_and_old_lineage(tmp_path):
    mod = api(); package = mod.load_package(); bound = mod.bindings(package)
    assert bound == package['manifest']['bindings']
    assert base.bindings(base.load_package()) == base.load_package()['manifest']['bindings']
    assert 'evaluations/diagnostics/managed_node_diagnostics_v2.py' in bound['sources']
    assert 'tests/diagnostics/test_managed_node_diagnostics_v2.py' in bound['sources']
    frozen = mod.freeze_sources(tmp_path / 'frozen', package)
    for name in bound['sources']:
        assert mod.digest(frozen / name) == bound['sources'][name]
    for name in package['manifest']['lineage']:
        assert mod.digest(frozen / name) == package['manifest']['lineage'][name]
    assert (frozen / '_external/edd/ledger.py').is_file()
    context = mod.prepare(package, 'COV-ISO-v1-03')
    folder = tmp_path / 'run'
    mod.record_sample(folder, context, lambda *a: AIMessage(content=json.dumps(package['oracle']['positive_outputs']['COV-ISO-v1-03'], ensure_ascii=False)))
    env = dict(os.environ, PYTHONPATH=str(frozen / 'src') + ':' + str(frozen), PYTHONDONTWRITEBYTECODE='1')
    proc = subprocess.run([sys.executable, '-m', 'evaluations.diagnostics.managed_node_diagnostics_v2', '--replay', str(folder)],
        cwd=frozen, env=env, capture_output=True, text=True, encoding='utf-8')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    (folder / 'node-call.json').write_text('{}\n', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact'): mod.replay(folder, package)


def test_dry_run_and_unapproved_execute_need_no_provider(capsys):
    mod = api()
    for stage, size in [('selection', 1), ('coverage', 3)]:
        assert mod.main(['--stage', stage]) == 0
        dry = json.loads(capsys.readouterr().out)
        assert len(dry['samples']) == size and dry['provider_calls'] == 0 and dry['bindings_match']
    with pytest.raises(ValueError, match='review'): mod.main(['--execute', '--ticket', 'unused'])


@pytest.mark.parametrize('mutation', ['last_order_month', 'customer_key', 'inventory_population', 'avg', 'member_filter'])
def test_member_amount_does_not_promote_unproven_month_keys_population_or_average(mutation):
    mod = api(); package = mod.load_package(); context = customer_context(mod, package)
    value = deepcopy(context['package']['oracle']['positive_outputs']['customer-eight-offline'])
    rows = value['entries']
    if mutation == 'last_order_month': rows['FILT-001'].update(status='supported', own_gap=False,
        mappings=[dict(column='last_order_date', operator='>=', value='2026-09-01'),
                  dict(column='last_order_date', operator='<', value='2026-10-01')])
    if mutation == 'customer_key': rows['GRN-001'].update(status='partial', mappings=[dict(column='customer_id')])
    if mutation == 'inventory_population': rows['POP-001'].update(status='partial', mappings=[dict(column='customer_id')], contract_path='/summary')
    if mutation == 'avg': rows['MET-003']['mappings'][0]['aggregation'] = 'avg'
    if mutation == 'member_filter': rows['MET-003']['mappings'][0]['conditions'] = [dict(column='membership_tier', operator='=', value='VIP')]
    try:
        result = mod.evaluate(context, json.dumps(value, ensure_ascii=False))
    except ValueError:
        return  # Preserve the real materializer's first rejection.
    assert result['semantic']['machine_verdict'] == 'FAIL'


def test_fixed_body_hashes_input_boundary_and_free_text_review_remain_explicit():
    mod = api(); package = mod.load_package(); expected = [
        'eb6a1dd98d63365b76b4f513cbf4794b293d9706489c00344f435b13fe133957',
        '30be965cceda1b54a473d77b3f03f8f1d668040b784c615adfdc6e9bb6f1eb35',
        'a54fe8c06fd3410b3c579ab9000ccf13352a548f3b6496052e3e71721ed1914e',
        '40eaa96a187ace445ce041c42e4036ef70551d3cb9d30e034f96752d28ad7f2f']
    for sid, body_hash in zip(base.SAMPLE_IDS, expected):
        context = mod.prepare(package, sid)
        assert base.json_digest(context['body']) == body_hash
        human = json.loads(context['messages'][1].content)
        assert set(human) == (set(['request', 'requirements', 'coverages', 'views', 'missing_policy_options', 'response_schema'])
                             if sid.startswith('SEL') else set(['request', 'requirements', 'view', 'response_schema']))
    fixed = package['manifest']['bindings']['samples']['SEL-ISO-v1-01']
    assert fixed['input_tokens'] == 22011
    assert fixed['messages'] == 'c6116af069cb945c678d5aea9e64b1c8eae6371e0a9decd7b809325847877ec5'
    assert fixed['upstream'] == '70460cc22c0deccd75d96896c4bd914efc0038a5a3bb300dc8e20be8ad4e43ff'
    context = mod.prepare(package, 'SEL-ISO-v1-01')
    value = deepcopy(package['oracle']['selection_positive'])
    value['draft']['tasks'][1]['request'] = '此來源保證所有未交易庫存都有一列且缺值為0'
    result = mod.evaluate(context, json.dumps(value, ensure_ascii=False))
    assert result['semantic']['machine_verdict'] == 'PASS'  # Never claim this checker reads prose.
    assert result['semantic']['independent_semantic_approval'] == 'PENDING'
    assert 'PENDING' in result['semantic']['free_text_review']
