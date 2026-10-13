"""Compose existing services; deployment supplies execution, core owns no DB adapter."""
from __future__ import annotations
from functools import cached_property
from typing import Any
from cpea.application.errors import DependencyUnavailable
from cpea.application.ports.catalog import CatalogProvider
from cpea.application.ports.sql_executor import SQLQueryExecutor
from cpea.config.settings import AssistantSettings
from cpea.config.deployment import DeploymentSettings

class AssistantRuntime:
    def __init__(self, settings: AssistantSettings, *, deployment: DeploymentSettings | None = None,
                 catalog: CatalogProvider | None = None, llm: Any = None,
                 executor: SQLQueryExecutor | None = None, datasource_id: str | None = None,
                 retriever: Any = None, context_packer: Any = None):
        from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
        self.settings = settings
        self.deployment = deployment or DeploymentSettings.load(settings.deployment_file,
            profile_path=settings.integration_path, datasource_id=settings.datasource_id)
        self.catalog = catalog if catalog is not None else SchemaCatalog(self.deployment.profile_path)
        self._llm = llm
        self.executor = executor
        self.datasource_id = datasource_id if datasource_id is not None else self.deployment.datasource_id
        self._retriever = retriever
        self._context_packer = context_packer

    @classmethod
    def from_env(cls, env_file=None, **dependencies):
        return cls(AssistantSettings.from_env(env_file), **dependencies)

    def require_execution(self):
        if self.executor is None or not self.datasource_id:
            raise DependencyUnavailable()

    @cached_property
    def llm(self):
        if self._llm is not None:
            return self._llm
        from cpea.infrastructure.llm.factory import get_llm_config
        return get_llm_config(settings=self.settings)

    @cached_property
    def retriever(self):
        if self._retriever is not None:
            return self._retriever
        from cpea.infrastructure.retrieval.schema import get_schema_retriever
        return get_schema_retriever(self.settings, self.catalog)

    @cached_property
    def context_packer(self):
        if self._context_packer is not None:
            return self._context_packer
        from cpea.infrastructure.llm.context_budget import ContextPacker
        return ContextPacker(self.settings)

    def generation_service(self):
        from cpea.application.services.sql_generation import SQLGenerationService
        return SQLGenerationService(self.llm, self.catalog, settings=self.settings,
            retriever=self.retriever, context_packer=self.context_packer)

    def execution_agent(self):
        self.require_execution()
        from cpea.application.services.sql_execution import SQLExecutionAgent
        return SQLExecutionAgent(self.llm, self.catalog, executor=self.executor, settings=self.settings,
            retriever=self.retriever, context_packer=self.context_packer)

    def answer_service(self, llm=None):
        from cpea.application.services.answering import AnswerSynthesisService
        return AnswerSynthesisService(self.llm if llm is None else llm,
            settings=self.settings, context_packer=self.context_packer)

    def generate(self, request, history=None):
        return self.generation_service().generate(request, history=history)

    def execute(self, request, history=None):
        self.require_execution()
        return self.execution_agent().run(request, datasource=self.datasource_id, history=history)

    def query(self, request, history=None):
        self.require_execution()
        execution = self.execute(request, history)
        return self.answer_service().synthesize(request, execution)
