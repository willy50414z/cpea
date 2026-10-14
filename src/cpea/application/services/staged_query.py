"""Typed independent query stages; transport framing belongs to the interface."""
from dataclasses import dataclass
from cpea.application.models.query import SQLGenerationResponse
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

    def generate(self, request: str) -> SQLStage:
        generation = self.agent.generator.generate(request, history=[])
        self.agent.validate_generation(generation, request)
        return SQLStage(generation)

    def execute(self, request: str, stage: SQLStage) -> ResultStage:
        execution = self.agent.execute_generation(stage.generation, self.datasource, request=request)
        return ResultStage(execution, self.agent.settings.max_rows)
