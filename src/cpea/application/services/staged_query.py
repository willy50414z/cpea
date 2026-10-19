"""Typed independent query stages; transport framing belongs to the interface."""
from dataclasses import dataclass
from cpea.application.models.query import ClarificationChoice, SQLGenerationResponse
from cpea.application.models.progress import WorkflowStep
from cpea.application.services.sql_execution import SQLExecutionAgent, SQLExecutionResult


@dataclass(frozen=True)
class SQLStage:
    generation: SQLGenerationResponse

    @property
    def sql(self) -> str:
        return self.generation.sql


@dataclass(frozen=True)
class ResultStage:
    execution: SQLExecutionResult
    row_limit: int


class StagedQueryService:
    def __init__(self, agent: SQLExecutionAgent, datasource: str):
        self.agent = agent
        self.datasource = datasource

    def generate(self, request: str, clarification_choice: ClarificationChoice | None = None, *, mode='stream', owner=None) -> SQLStage:
        generation = self.agent.generator.generate(request, history=[], clarification_choice=clarification_choice, mode=mode, owner=owner)
        if generation.status == 'ready':
            self.agent.validate_generation(generation, request)
        return SQLStage(generation)

    def execute(self, request: str, stage: SQLStage) -> ResultStage:
        try:
            execution = self.agent.execute_generation(stage.generation, self.datasource, request=request)
            return ResultStage(execution, self.agent.settings.max_rows)
        finally:
            if stage.generation.run_id:
                self.agent.generator.workflow.registry.finish(stage.generation.run_id)

    def generate_updates(self, request: str, *, mode='web', owner=None, clarification_choice=None):
        for update in self.agent.generator.generate_updates(request, history=[], mode=mode, owner=owner,
                                                            clarification_choice=clarification_choice):
            if isinstance(update, WorkflowStep):
                yield update
                continue
            try:
                if update.status == 'ready':
                    self.agent.validate_generation(update, request)
            except Exception:
                if update.run_id:
                    self.agent.generator.workflow.registry.finish(update.run_id)
                raise
            yield SQLStage(update)
