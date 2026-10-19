from __future__ import annotations

from typing import Any

from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.application.models.query import ConversationTurn, SQLGenerationResponse
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.config.settings import AssistantSettings
from cpea.workflows.text_to_sql.prompt_resources import MatchPrompt


class SQLGenerationService:
    def __init__(
        self,
        llm: Any,
        catalog: CatalogProvider | None = None,
        *,
        settings: AssistantSettings | None = None,
        retriever: SchemaRetriever | None = None,
        context_packer: ContextPacker | None = None,
        match_prompt: MatchPrompt | None = None,
        repository=None,
    ) -> None:
        self.workflow = SQLGenerationWorkflow(
            llm,
            catalog,
            settings=settings,
            retriever=retriever,
            context_packer=context_packer,
            match_prompt=match_prompt, repository=repository,
        )

    def generate(
        self, request: str, history: list[ConversationTurn] | None = None, *, mode="sql", owner=None
    ) -> SQLGenerationResponse:
        return self.workflow.invoke(request, history=history, mode=mode, owner=owner)

    def generate_updates(self, request: str, history=None, *, mode='sql', owner=None):
        yield from self.workflow.generate_updates(request, history=history, mode=mode, owner=owner)
