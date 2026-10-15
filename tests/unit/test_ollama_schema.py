import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from langchain_ollama import ChatOllama

from cpea.workflows.text_to_sql.schemas import AnswerDraft, SQLClauseMapping
from tests.support import QUESTION, StubLLM, Workflow, dependencies


def ollama_with_transport(payload, requests):
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'model': 'synthetic',
            'message': {'role': 'assistant', 'content': json.dumps(payload, ensure_ascii=False)},
            'done': True,
            'done_reason': 'stop',
        })

    return ChatOllama(model='synthetic', base_url='http://ollama.example', format='json',
                      reasoning=False,
                      sync_client_kwargs={'transport': httpx.MockTransport(respond), 'trust_env': False})


def test_workflow_sends_pydantic_schema_in_ollama_request(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    mapping = json.loads(StubLLM().invoke([SimpleNamespace(content='table定義:')]).content)
    requests = []
    llm = ollama_with_transport(mapping, requests)
    result = Workflow(llm, catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke(QUESTION)
    assert result.supported, result.limitations
    assert len(requests) == 1
    schema = requests[0]['format']
    assert schema['$defs']['ClauseField']['properties']['column']['enum'] == sorted(catalog.columns('gms2.v_inventory'))
    assert schema['$defs']['ClauseTable']['properties']['view']['enum'] == ['gms2.v_inventory']
    assert result.query_plan.aggregations == {'库存数量': 'sum'}
    assert llm.format == 'json'


def test_response_schema_binding_does_not_change_other_response_formats():
    from cpea.infrastructure.llm.factory import bind_response_schema

    requests = []
    llm = ollama_with_transport({'answer': '合成回答', 'citations': []}, requests)
    structured = bind_response_schema(llm, AnswerDraft)
    raw = structured.invoke('請回傳回答 JSON')
    assert AnswerDraft.model_validate_json(raw.content).answer == '合成回答'
    assert requests[0]['format'] == AnswerDraft.model_json_schema()
    llm.invoke('請回傳一般 JSON')
    assert requests[1]['format'] == 'json'


@pytest.mark.parametrize('output_tokens', [8192, -1])
def test_configured_thinking_keeps_scratchpad_out_of_json_response(tmp_path, monkeypatch, output_tokens):
    from cpea.infrastructure.llm import factory
    from cpea.infrastructure.llm.parsing import parse_model

    settings, *_ = dependencies(tmp_path)
    settings = replace(settings, llm_reasoning=True, max_output_tokens=output_tokens)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'model': 'synthetic', 'done': True, 'done_reason': 'stop',
            'message': {'role': 'assistant', 'thinking': 'private synthetic scratchpad',
                        'content': '{"fields":[],"table":null}'},
        })

    original = ChatOllama
    monkeypatch.setattr(factory, 'ChatOllama', lambda **kwargs: original(
        **kwargs, sync_client_kwargs={'transport': httpx.MockTransport(respond), 'trust_env': False}))
    llm = factory.get_llm_config(settings=settings)
    raw = llm.invoke('回傳結構化 JSON')
    assert requests[0]['think'] is True
    assert requests[0]['options']['num_predict'] == output_tokens
    assert raw.additional_kwargs['reasoning_content'] == 'private synthetic scratchpad'
    assert parse_model(raw, SQLClauseMapping).table is None


@pytest.mark.parametrize('output_tokens', [-1, 4096])
def test_azure_output_budget_uses_provider_request_semantics(tmp_path, monkeypatch, output_tokens):
    provider = pytest.importorskip('langchain_openai')
    from cpea.infrastructure.llm import factory

    settings, *_ = dependencies(tmp_path)
    settings = replace(settings, llm_provider='azure', llm_api_key='synthetic',
                       llm_base_url='https://azure.example/openai/v1', max_output_tokens=output_tokens)
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'id': 'synthetic', 'object': 'chat.completion', 'created': 0, 'model': 'synthetic',
            'choices': [{'index': 0, 'finish_reason': 'stop',
                         'message': {'role': 'assistant', 'content': '{}'}}],
        })

    original = provider.ChatOpenAI
    monkeypatch.setattr(provider, 'ChatOpenAI', lambda **kwargs: original(
        **kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond), trust_env=False)))
    factory.get_llm_config(settings=settings).invoke('configuration probe')
    if output_tokens == -1:
        assert 'max_tokens' not in requests[0]
        assert 'max_completion_tokens' not in requests[0]
    else:
        assert requests[0].get('max_completion_tokens', requests[0].get('max_tokens')) == output_tokens


def test_call_recorder_preserves_per_request_contract_name_constraints(tmp_path):
    from evaluations.stability_runner import RecordedModel

    settings, catalog, packer, _, retriever = dependencies(tmp_path / 'profile')
    payload = json.loads(StubLLM().invoke([SimpleNamespace(content='table定義:')]).content)
    requests = []
    native = ollama_with_transport(payload, requests)
    traced = RecordedModel(native, 'ollama', 'synthetic', tmp_path / 'calls.jsonl', tmp_path / 'ledger.jsonl')
    result = Workflow(traced, catalog, settings=settings, retriever=retriever,
                      context_packer=packer).invoke(QUESTION)
    assert result.supported
    assert requests[0]['format']['$defs']['ClauseField']['properties']['column']['enum'] == sorted(catalog.columns('gms2.v_inventory'))
    assert requests[0]['format']['$defs']['ClauseTable']['properties']['view']['enum'] == ['gms2.v_inventory']
    assert native.format == 'json'
    assert len((tmp_path / 'ledger.jsonl').read_text(encoding='utf-8').splitlines()) == 1
