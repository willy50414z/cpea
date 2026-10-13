from __future__ import annotations

from typing import Any

from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.application.models.query import ConversationTurn, SQLGenerationResponse
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.config.settings import AssistantSettings


class SQLGenerationService:
    def __init__(
        self,
        llm: Any,
        catalog: CatalogProvider | None = None,
        *,
        settings: AssistantSettings | None = None,
        retriever: SchemaRetriever | None = None,
        context_packer: ContextPacker | None = None,
    ) -> None:
        self.workflow = SQLGenerationWorkflow(
            llm,
            catalog,
            settings=settings,
            retriever=retriever,
            context_packer=context_packer,
        )

    def generate(
        self, request: str, history: list[ConversationTurn] | None = None
    ) -> SQLGenerationResponse:
        return self.workflow.invoke(request, history=history)
