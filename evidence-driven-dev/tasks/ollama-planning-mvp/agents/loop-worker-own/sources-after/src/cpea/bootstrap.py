"""Compose services with injected or explicitly configured optional execution."""
from __future__ import annotations
from functools import cached_property
from typing import Any
from threading import RLock
from dataclasses import replace
from pathlib import Path
from cpea.application.errors import DependencyUnavailable
from cpea.application.ports.catalog import CatalogProvider
from cpea.application.ports.sql_executor import SQLQueryExecutor
from cpea.config.settings import AssistantSettings
from cpea.config.deployment import DeploymentSettings


class ProjectRuntimes:
    """Cache isolated runtimes for the web application's fixed project choices."""
    project_ids = ('gms2', 'retail')

    def __init__(self, projects_root: str | Path, *, runtime_factory=None):
        self.projects_root = Path(projects_root).resolve()
        self._runtime_factory = runtime_factory or AssistantRuntime
        self._runtimes = {}
        self._lock = RLock()

    @classmethod
    def from_env(cls):
        from cpea.config.projects import configured_projects_root
        return cls(configured_projects_root())

    def get(self, project_id: str):
        from cpea.config.projects import resolve_project
        if project_id not in self.project_ids:
            raise ValueError('selected project is not available')
        with self._lock:
            if project_id not in self._runtimes:
                workspace = resolve_project(project_id, projects_root=self.projects_root, require_cases=False)
                settings = AssistantSettings.from_env(workspace.env_file)
                # The dropdown selects the profile. A startup shell's profile
                # must not silently override this project's contracts.
                settings = replace(settings, integration_path=str(workspace.root))
                if settings.deployment_file and not Path(settings.deployment_file).resolve().is_relative_to(workspace.root):
                    raise ValueError('project deployment configuration must remain inside the selected project')
                deployment = DeploymentSettings.load(settings.deployment_file,
                    profile_path=str(workspace.root), datasource_id=settings.datasource_id)
                self._runtimes[project_id] = self._runtime_factory(settings, deployment=deployment)
            return self._runtimes[project_id]

    def close(self):
        with self._lock:
            for runtime in self._runtimes.values():
                runtime.close()

class AssistantRuntime:
    def __init__(self, settings: AssistantSettings, *, deployment: DeploymentSettings | None = None,
                 catalog: CatalogProvider | None = None, llm: Any = None,
                 executor: SQLQueryExecutor | None = None, datasource_id: str | None = None,
                 retriever: Any = None, context_packer: Any = None, match_prompt: Any = None):
        from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
        self._service_lock = RLock()
        self.settings = settings
        self.deployment = deployment or DeploymentSettings.load(settings.deployment_file,
            profile_path=settings.integration_path, datasource_id=settings.datasource_id)
        self.catalog = catalog if catalog is not None else SchemaCatalog(self.deployment.profile_path)
        self._llm = llm
        self.executor = executor
        self.datasource_id = datasource_id if datasource_id is not None else self.deployment.datasource_id
        if executor is None and settings.sqlserver.enabled:
            from cpea.infrastructure.database.sql_server import SQLServerExecutor
            self.executor = SQLServerExecutor(settings.sqlserver, self.datasource_id,
                {view.name for view in self.catalog.views()}, settings.max_rows)
        self._retriever = retriever
        self._context_packer = context_packer
        self.match_prompt = match_prompt

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

    @cached_property
    def _generation_service(self):
        from cpea.application.services.sql_generation import SQLGenerationService
        from cpea.application.ports.term_mappings import MappingScope
        from cpea.infrastructure.terms_mapping import JsonTermMappingRepository
        from pathlib import Path
        scope = MappingScope(profile_id=self.catalog.profile_id, datasource_id=self.datasource_id)
        path = self.settings.terms_mapping_path or Path(getattr(self.catalog, 'root', None) or self.deployment.profile_path or '.') / 'terms_mapping.json'
        repository = JsonTermMappingRepository(path, scope)
        return SQLGenerationService(self.llm, self.catalog, settings=self.settings, repository=repository,
            retriever=self.retriever, context_packer=self.context_packer,
            match_prompt=self.match_prompt)

    def generation_service(self):
        with self._service_lock:
            return self._generation_service

    def execution_agent(self):
        self.require_execution()
        from cpea.application.services.sql_execution import SQLExecutionAgent
        return SQLExecutionAgent(self.llm, self.catalog, executor=self.executor, settings=self.settings,
            retriever=self.retriever, context_packer=self.context_packer, generator=self.generation_service())

    def answer_service(self, llm=None):
        from cpea.application.services.answering import AnswerSynthesisService
        return AnswerSynthesisService(self.llm if llm is None else llm,
            settings=self.settings, context_packer=self.context_packer)

    def generate(self, request, history=None):
        return self.generation_service().generate(request, history=history)

    def execute(self, request, history=None):
        self.require_execution()
        generation = self.generation_service().generate(request, history, mode='execute')
        return self._complete(request, generation, answer=False)

    def query(self, request, history=None):
        self.require_execution()
        generation = self.generation_service().generate(request, history, mode='query')
        return self._complete(request, generation, answer=True)

    def _complete(self, request, generation, *, answer):
        if generation.status != 'ready':
            return generation
        try:
            execution = self.execution_agent().execute_generation(generation, self.datasource_id, request=request)
            return self.answer_service().synthesize(request, execution) if answer else execution
        finally:
            self.finish(generation)

    def resume_generation(self, payload, *, mode='sql', owner=None, claimed=None):
        return self.generation_service().workflow.confirm(payload, mode=mode, owner=owner, claimed=claimed)

    def resume_generation_updates(self, payload, *, mode='web', owner=None):
        yield from self.generation_service().workflow.confirm_updates(payload, mode=mode, owner=owner)

    def confirm(self, payload, *, mode='sql', owner=None):
        if mode != 'sql':
            self.require_execution()
        request, generation = self.resume_generation(payload, mode=mode, owner=owner)
        return generation if mode == 'sql' else self._complete(request, generation, answer=mode == 'query')

    def finish(self, generation):
        if generation.run_id:
            self.generation_service().workflow.registry.finish(generation.run_id)

    def close(self):
        if '_generation_service' in self.__dict__:
            self._generation_service.workflow.registry.close()

    def staged_query_service(self):
        self.require_execution()
        from cpea.application.services.staged_query import StagedQueryService
        return StagedQueryService(self.execution_agent(), self.datasource_id)
