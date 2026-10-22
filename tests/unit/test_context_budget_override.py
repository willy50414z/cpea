from dataclasses import replace
from types import SimpleNamespace

from langchain_core.documents import Document
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
import pytest

from cpea.config.settings import AssistantSettings
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.retrieval.schema import RetrievalCandidate
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from tests.support import Counter


def settings():
    return replace(AssistantSettings.from_env(), context_window=512,
                   max_output_tokens=128, context_safety_tokens=32)


def candidate():
    return RetrievalCandidate(Document(id='demo.v_example', page_content='large contract ' * 500,
        metadata={'document_id': 'demo.v_example', 'source': 'view.yaml',
                  'filename': 'view.yaml', 'section': 'schema_contract',
                  'chunk_id': 'demo.v_example:schema_contract'}), retrieval_score=1.0)


@pytest.mark.parametrize('disabled', [False, True])
def test_override_preserves_full_contract_and_actual_token_count(disabled):
    kwargs = {'enforce_budget': False} if disabled else {}
    packer = ContextPacker(settings(), token_counter=Counter(), **kwargs)
    packed = packer.pack_documents(system_prompt='system', question='question',
                                    history_text='', candidates=[candidate()])
    assert bool(packed.sources) is disabled
    if disabled:
        assert packed.context_tokens > packed.document_budget
        assert 'large contract ' * 500 in packed.text
        assert packed.dropped_document_ids == []
    else:
        assert packed.dropped_document_ids == ['demo.v_example']


@pytest.mark.parametrize('disabled', [False, True])
def test_override_controls_pre_invoke_guard_without_changing_model_settings(disabled):
    class Reply(BaseModel):
        ok: bool

    invoked = []
    workflow = object.__new__(SQLGenerationWorkflow)
    workflow.settings = settings()
    kwargs = {'enforce_budget': False} if disabled else {}
    workflow.context_packer = ContextPacker(workflow.settings, token_counter=Counter(), **kwargs)
    workflow.llm = SimpleNamespace(invoke=lambda messages: invoked.append(messages) or
                                   SimpleNamespace(content='{"ok":true}'))
    prompt = ChatPromptTemplate.from_messages([('system', 'system'), ('human', '{request}')])
    original = workflow.settings
    if disabled:
        assert workflow._invoke_model(prompt, {'request': 'long input ' * 500}, Reply).ok
        assert len(invoked) == 1
    else:
        with pytest.raises(ValueError, match='prompt exceeds context budget'):
            workflow._invoke_model(prompt, {'request': 'long input ' * 500}, Reply)
        assert invoked == []
    assert workflow.settings == original
