"""Execute one compiled read-only SQL query and report database failures."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from cpea.application.ports.sql_executor import SQLQueryExecutor
from cpea.application.errors import DependencyUnavailable

from cpea.application.services.sql_generation import SQLGenerationService
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.application.models.query import ClarificationChoice, ConversationTurn, SQLGenerationResponse
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.sql_policy import validate_generated_sql
from cpea.infrastructure.sql_compiler import compile_single_view


class SQLExecutionError(RuntimeError):
    def __init__(self, message: str, generation: SQLGenerationResponse | None = None):
        super().__init__(message)
        self.generation = generation


@dataclass(frozen=True)
class SQLExecutionResult:
    generation: SQLGenerationResponse
    columns: list[str]
    rows: list[list[Any]]
    attempts: int
    repaired: bool
    rows_truncated: bool = False


class SQLExecutionAgent:
    """Executes one compiled query with no LLM repair attempt."""

    def __init__(
        self,
        llm: Any,
        catalog: CatalogProvider | None = None,
        executor: SQLQueryExecutor | None = None,
        settings: AssistantSettings | None = None,
        retriever: SchemaRetriever | None = None,
        context_packer: ContextPacker | None = None,
    ) -> None:
        self.llm = llm
        self.catalog = catalog or _default_catalog()
        self.settings = settings or AssistantSettings.from_env()
        self.generator = SQLGenerationService(
            llm,
            self.catalog,
            settings=self.settings,
            retriever=retriever,
            context_packer=context_packer,
        )
        self.executor = executor

    def run(
        self,
        request: str,
        datasource: str | None = None,
        history: list[ConversationTurn] | None = None,
        clarification_choice: ClarificationChoice | None = None,
    ) -> SQLExecutionResult:
        if self.executor is None or not datasource:
            raise DependencyUnavailable()
        generation = self.generator.generate(request, history=history, clarification_choice=clarification_choice)
        return self.execute_generation(generation, datasource, request=request)

    def validate_generation(self, generation: SQLGenerationResponse, request: str) -> None:
        if not generation.supported or not generation.sql:
            raise SQLExecutionError(generation.explanation, generation)
        validate_generated_sql(generation.sql, {view.name for view in self.catalog.views()})
        if generation.query_plan is None:
            raise SQLExecutionError('Missing approved query plan', generation)
        # Recompile deterministically to confirm the approved plan and exact SQL.
        approved = compile_single_view(generation.query_plan, self.catalog, request=request,
                                       max_rows=self.settings.max_rows)
        if approved != generation.sql:
            raise SQLExecutionError('SQL does not match approved query plan', generation)

    def execute_generation(self, generation: SQLGenerationResponse,
                           datasource: str | None = None, *, request: str) -> SQLExecutionResult:
        if self.executor is None or not datasource:
            raise DependencyUnavailable()
        self.validate_generation(generation, request)
        try:
            columns, rows = self.executor(datasource, generation.sql)
            rows, truncated = self._bounded_rows(rows)
            generation = self._with_execution_trace(generation, 1, columns, truncated)
            return SQLExecutionResult(
                generation,
                columns,
                rows,
                attempts=1,
                repaired=False,
                rows_truncated=truncated,
            )
        except Exception as error:  # noqa: BLE001 - DB drivers vary by deployment
            safe_error = self._safe_error(error)
            failed = self._with_execution_trace(generation, 1, [], False, safe_error)
            raise SQLExecutionError(f"已編譯 SQL 執行失敗：{safe_error}", failed) from error

    @staticmethod
    def _with_execution_trace(
        generation: SQLGenerationResponse, attempts: int, columns: list[str],
        truncated: bool, error: str | None = None,
    ) -> SQLGenerationResponse:
        if generation.query_trace is None:
            return generation
        trace = generation.query_trace.model_copy(update={
            "execution_attempts": attempts,
            "result_columns": columns,
            "rows_truncated": truncated,
            "execution_error": error,
            "rejection_stage": "execution" if error else generation.query_trace.rejection_stage,
        })
        return generation.model_copy(update={"query_trace": trace})

    @staticmethod
    def _safe_error(error: Exception) -> str:
        # DB exceptions may include a long SQLAlchemy trace. Keep the public
        # execution diagnostic bounded.
        return " ".join(str(error).split())[:1500]

    def _bounded_rows(self, rows: list[list[Any]]) -> tuple[list[list[Any]], bool]:
        truncated = len(rows) > self.settings.max_rows
        return rows[: self.settings.max_rows], truncated


def _default_catalog():
    from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
    return SchemaCatalog(AssistantSettings.from_env().integration_path)
