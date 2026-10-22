import json
from types import SimpleNamespace

import httpx
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_ollama import ChatOllama
import pytest

from cpea.infrastructure.llm import factory
from cpea.workflows.text_to_sql.schemas import ClarificationResolution
from tests.support import Workflow, dependencies


def test_semantic_resolution_request_includes_its_output_contract(tmp_path):
    settings, catalog, packer, _, retriever = dependencies(tmp_path)
    captured = []

    class Model:
        def invoke(self, messages):
            captured.extend(messages)
            return SimpleNamespace(content='{"source_compatible":true,"clarifications":[]}')

    workflow = Workflow(Model(), catalog, settings=settings, retriever=retriever,
                        context_packer=packer)
    prompt = ChatPromptTemplate.from_messages([('system', '請整理語意選項。'), ('human', '{request}')])
    response = workflow._invoke_model(prompt, {'request': '查庫存'}, ClarificationResolution)
    assert response.source_compatible
    assert '"source_compatible"' in '\n'.join(str(m.content) for m in captured)
    assert '"required"' in '\n'.join(str(m.content) for m in captured)


def test_common_schema_messages_reach_both_native_transports():
    provider = pytest.importorskip('langchain_openai')
    requests = {}
    payload = {'source_compatible': True, 'clarifications': []}

    def ollama_response(request):
        requests['ollama'] = json.loads(request.content)
        return httpx.Response(200, json={'model': 'synthetic', 'done': True,
            'message': {'role': 'assistant', 'content': json.dumps(payload)}})

    def azure_response(request):
        requests['azure'] = json.loads(request.content)
        return httpx.Response(200, json={'id': 'synthetic', 'object': 'chat.completion',
            'created': 0, 'model': 'synthetic', 'choices': [{'index': 0, 'finish_reason': 'stop',
            'message': {'role': 'assistant', 'content': json.dumps(payload)}}]})

    ollama = ChatOllama(model='synthetic', base_url='http://ollama.example', reasoning=False,
        sync_client_kwargs={'transport': httpx.MockTransport(ollama_response), 'trust_env': False})
    azure = provider.ChatOpenAI(model='synthetic', api_key='synthetic', max_retries=0,
        base_url='https://azure.example/openai/v1',
        http_client=httpx.Client(transport=httpx.MockTransport(azure_response), trust_env=False))
    schema = factory.response_schema_for(ClarificationResolution, column_names={'stock_qty'})
    messages = [SystemMessage(content='請整理語意選項。'), HumanMessage(content='查庫存')]
    prepared = factory.prepare_structured_messages(messages, ClarificationResolution, schema=schema)
    assert messages[0].content == '請整理語意選項。'
    assert prepared[-1].content == messages[-1].content
    for model in (ollama, azure):
        raw = factory.bind_response_schema(model, ClarificationResolution, schema=schema).invoke(prepared)
        assert ClarificationResolution.model_validate_json(raw.content).source_compatible
    normalized = [[(m['role'], m['content']) for m in requests[name]['messages']]
                  for name in ('ollama', 'azure')]
    assert normalized[0] == normalized[1]
    assert '"source_compatible"' in normalized[0][0][1]
    assert requests['ollama']['format'] == schema
    assert requests['azure']['response_format'] == {'type': 'json_object'}


def test_schema_already_in_context_is_not_duplicated():
    schema = factory.response_schema_for(ClarificationResolution)
    messages = [SystemMessage(content='整理選項'), HumanMessage(content=json.dumps(
        {'response_schema': schema}, ensure_ascii=False))]
    result = factory.prepare_structured_messages(messages, ClarificationResolution, schema=schema)
    assert [m.content for m in result] == [m.content for m in messages]
