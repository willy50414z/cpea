"""Offline contracts for the controller-only three-stage evaluation runner."""
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations.indexed_requirement_recall import IndexedRecallResult
from evaluations.referenced_view_coverage import ReferencedViewCoverage, materialize_coverage
from evaluations.three_stage_view_selection import SelectionResult, finish_selection
from test_three_stage_view_selection import INV, REQUEST, coverage, recall, selection
from test_referenced_view_coverage import referenced


def runner():
    return importlib.import_module('evaluations.managed_three_stage_runner')


@pytest.fixture
def catalog():
    return SchemaCatalog('projects/retail')


def fixture(catalog):
    request = REQUEST + '顯示盤點日期，以供稽核討論。'
    rec = recall(catalog).model_dump()
    rec['requirements'].append(dict(requirement_id='R_PURPOSE', quote='盤點日期', kind='metadata',
        business_object='來源盤點時間', scope_ids=[], grain='店商品', population='庫存商品'))
    indexed = json.loads(json.dumps(rec))
    for r in indexed['requirements']:
        quote = r.pop('quote')
        r.update(start=request.index(quote), end=request.index(quote) + len(quote))
    maps = []
    for v in catalog.views():
        data = referenced(catalog, v.name)
        supported = v.name == INV
        data['entries'].append(dict(requirement_id='R_PURPOSE', status='supported' if supported else 'unsupported',
            mappings=[dict(column='snapshot_date', role='metadata')] if supported else [],
            contract_path='/columns/snapshot_date/description' if supported else None,
            missing_requirements=[] if supported else ['未提供盤點日期']))
        maps.append(ReferencedViewCoverage.model_validate(data))
    sel = selection(catalog).model_dump()
    sel['assignments'].append(dict(requirement_id='R_PURPOSE', view=INV, task_id='stock', reason='來源日期'))
    sel['draft']['tasks'][0]['required_columns'].append('snapshot_date')
    sel['draft']['tasks'][0]['metadata_collections'] = ['snapshot_date']
    return request, IndexedRecallResult.model_validate(indexed), maps, SelectionResult.model_validate(sel)


def fake(catalog, fail=None):
    request, rec, maps, sel = fixture(catalog)
    responses = iter([rec, *maps, sel])
    calls = []
    def invoke(name, messages, schema):
        calls.append(name)
        payload = json.loads(messages[1].content)
        assert payload['request'] == request
        assert payload['response_schema'] == schema.model_json_schema()
        data = next(responses).model_dump()
        if name.startswith('map-'):
            assert schema is ReferencedViewCoverage
        if name == fail:
            data['contract_path'] = '/not-real'
        return AIMessage(content=json.dumps(data, ensure_ascii=False),
            usage_metadata=dict(input_tokens=10, output_tokens=20, total_tokens=30))
    return request, invoke, calls


def test_prompt_distinguishes_executable_metadata_from_background():
    text = Path('evaluations/prompts/three_stage/recall_indexed.md').read_text(encoding='utf-8')
    assert '每一項都必須能由資料來源履行' in text
    assert 'metadata不是業務目的' in text
    assert '以供稽核討論' in text and '顯示資料更新日期' in text
    assert '原始request' in text


def test_full_pipeline_keeps_background_in_context_and_real_metadata_even_with_purpose_id(catalog):
    request, invoke, calls = fake(catalog)
    saved = {}
    response = runner().run_pipeline(request, catalog, invoke, saved.__setitem__)
    assert response.status == 'ready' and len(response.prepared_requests) == 2
    assert calls == ['recall', *[f'map-{i:02}' for i in range(1, 8)], 'selection']
    assert saved['recall-result.json']['requirements'][-1]['requirement_id'] == 'R_PURPOSE'
    assert all(r['quote'] != '以供稽核討論' for r in saved['recall-result.json']['requirements'])
    stock = saved['selection-result.json']['draft']['tasks'][0]
    assert stock['metadata_collections'] == ['snapshot_date']
    assert stock['group_by'] == ['store_id', 'product_id']
    assert saved['map-01-parsed.json'] and saved['map-01-normalized.json']
    assert saved['response.json']['prepared_requests']
    assert saved['usage.json']['output_tokens_actual'] == 180


def test_true_metadata_requires_real_column_mapping_and_own_evidence(catalog):
    from evaluations.indexed_requirement_recall import materialize_recall
    request, rec, maps, sel = fixture(catalog)
    recalled = materialize_recall(rec, request, catalog)
    mapped = [materialize_coverage(m, recalled, request, catalog) for m in maps]
    assert finish_selection(sel, recalled, mapped, request, catalog).status == 'ready'
    data = next(m for m in maps if m.view == INV).model_dump()
    data['entries'][-1]['mappings'] = []
    with pytest.raises(ValueError, match='supported requires mappings/evidence'):
        materialize_coverage(ReferencedViewCoverage.model_validate(data), recalled, request, catalog)
    data['entries'][-1]['mappings'] = [dict(column='snapshot_date', role='attribute')]
    with pytest.raises(ValueError, match='role differs'):
        materialize_coverage(ReferencedViewCoverage.model_validate(data), recalled, request, catalog)


@pytest.mark.parametrize('failure', ['map-02', 'provider', 'parse'])
def test_failure_keeps_first_raw_or_provider_error_and_stops(catalog, failure):
    request, invoke, calls = fake(catalog, fail='map-02' if failure == 'map-02' else None)
    saved = {}
    if failure != 'map-02':
        def invoke(name, messages, schema):
            calls.append(name)
            if failure == 'provider':
                raise OSError('connection lost')
            return AIMessage(content='not json')
    with pytest.raises(Exception):
        runner().run_pipeline(request, catalog, invoke, saved.__setitem__)
    node = 'map-02' if failure == 'map-02' else 'recall'
    assert calls[-1] == node
    assert node + '-error.json' in saved
    assert node + ('-provider-error.json' if failure == 'provider' else '-call.json') in saved
    assert 'response.json' not in saved


@pytest.mark.parametrize('failure', [None, 'map-02', 'provider', 'parse', 'input'])
def test_offline_replay_matches_complete_run_and_failed_prefix(tmp_path, catalog, failure):
    request, invoke, calls = fake(catalog, fail='map-02' if failure == 'map-02' else None)
    if failure in ('provider', 'parse'):
        def invoke(name, messages, schema):
            if failure == 'provider':
                raise OSError('connection lost')
            return AIMessage(content='not json')
    case = runner().diagnostic_case(catalog, request)
    outcome = runner().record_run(tmp_path, catalog, case, invoke,
        context_window=1 if failure == 'input' else 32768)
    assert bool(outcome['stopped']) == bool(failure)
    assert runner().replay(tmp_path, catalog, case)['result'] == 'PASS'
    assert runner().replay(tmp_path, catalog, case)['stopped'] == outcome['stopped']


@pytest.mark.parametrize('tamper', ['artifact', 'input', 'source', 'extra'])
def test_replay_rejects_changed_artifact_input_or_version(tmp_path, catalog, monkeypatch, tamper):
    request, invoke, _ = fake(catalog)
    case = runner().diagnostic_case(catalog, request)
    runner().record_run(tmp_path, catalog, case, invoke)
    if tamper == 'artifact':
        (tmp_path/'recall-call.json').write_text('{}', encoding='utf-8')
    elif tamper == 'input':
        case['request'] += '。'
    elif tamper == 'source':
        original = runner().fingerprint
        monkeypatch.setattr(runner(), 'fingerprint', lambda *a: dict(original(*a), modified=True))
    else:
        (tmp_path/'extra.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='artifact|version'):
        runner().replay(tmp_path, catalog, case)


def test_managed_invoke_uses_one_controller_request_without_timeout_or_sdk(tmp_path, monkeypatch):
    mod = runner()
    from evaluations.three_stage_view_selection_runner import messages_for
    messages = messages_for('recall', IndexedRecallResult, '完整原始需求🧾', views=[])
    response = tmp_path/'controller-response.txt'
    response.write_text(json.dumps(dict(model=mod.MODEL, done=True, done_reason='stop',
        message=dict(role='assistant', content='{}', thinking='保留原始推理'),
        prompt_eval_count=13, eval_count=21)), encoding='utf-8')
    calls = []
    def process(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout=json.dumps(dict(request_id='req1', result='ok',
            response_path=str(response), http_status=200)))
    monkeypatch.setattr(mod.subprocess, 'run', process)
    saved = {}
    invoke = mod.ManagedInvoke(tmp_path, 'worker-ticket', 'fixed-candidate-v1', saved.__setitem__)
    raw = invoke('recall', messages, IndexedRecallResult)
    assert len(calls) == 1
    command, options = calls[0]
    assert command[command.index('--provider')+1] == 'local'
    assert command[command.index('--url-env')+1] == 'EDD_LOCAL_ENDPOINT'
    assert command[command.index('--ticket')+1] == 'worker-ticket'
    assert 'request' in command and '--retry-of' not in command
    assert 'timeout' not in options
    body = json.loads((tmp_path/'recall-body.json').read_text(encoding='utf-8'))
    assert body['model'] == mod.MODEL and body['stream'] is False and body['think'] is True
    assert body['options'] == dict(num_predict=-1, num_ctx=32768, temperature=1, top_p=1, seed=42)
    assert body['format'] == IndexedRecallResult.model_json_schema()
    assert json.loads(body['messages'][1]['content'])['request'] == '完整原始需求🧾'
    assert raw.usage_metadata['total_tokens'] == 34
    assert saved['recall-managed.json']['request_id'] == 'req1'
    assert saved['recall-provider-response.json']['message']['thinking'] == '保留原始推理'


@pytest.mark.parametrize('result', ['http_error', 'rate_limited', 'transport_error'])
def test_managed_failure_records_receipt_and_never_retries(tmp_path, monkeypatch, result):
    mod = runner()
    calls, saved = [], {}
    response = tmp_path/'response.txt'
    response.write_text('provider failed', encoding='utf-8')
    def process(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=1, stdout=json.dumps(dict(request_id='failed', result=result,
            response_path=str(response), http_status=503)))
    monkeypatch.setattr(mod.subprocess, 'run', process)
    with pytest.raises(Exception, match='managed request'):
        mod.ManagedInvoke(tmp_path, 'ticket', 'fixed', saved.__setitem__)('recall', [], IndexedRecallResult)
    assert len(calls) == 1 and saved['recall-managed.json']['request_id'] == 'failed'
    assert saved['recall-provider-response.json']['raw_text'] == 'provider failed'


def test_dry_run_never_constructs_provider_or_calls_network(monkeypatch, capsys):
    mod = runner()
    monkeypatch.setattr(mod, 'ManagedInvoke', lambda *a, **k: pytest.fail('provider constructed'))
    monkeypatch.setattr(mod, 'verify_model_identity', lambda *a: pytest.fail('network called'))
    assert mod.main([]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result['execute'] is False and result['num_predict'] == -1
    assert result['HTTP_timeout_seconds'] is None


def test_interrupted_run_is_saved_as_incomplete_and_cannot_replay_as_success(tmp_path, catalog):
    mod = runner()
    case = mod.diagnostic_case(catalog, REQUEST)
    def interrupt(*args):
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        mod.record_run(tmp_path, catalog, case, interrupt)
    meta = json.loads((tmp_path/'run.json').read_text(encoding='utf-8'))
    assert meta['stopped'] is not None
    assert 'recall-request.json' in meta['artifact_hashes']
    with pytest.raises(ValueError, match='replay stopped result differs'):
        mod.replay(tmp_path, catalog, case)


def test_diagnostic_request_preserves_exact_unicode_and_line_endings(tmp_path, catalog, monkeypatch):
    mod = runner()
    (tmp_path/'.local').mkdir()
    original = '庫存🧾\r\n顯示資料日期。\n'
    (tmp_path/'.local/index-recall-request.txt').write_bytes(original.encode('utf-8'))
    monkeypatch.setattr(mod, 'TASK', tmp_path)
    assert mod.diagnostic_case(catalog)['request'] == original
