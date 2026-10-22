"""SQL-stage contracts. No execution or business-result claims."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cpea.application.models.decomposition import DecompositionResponse, PlanningTask
from cpea.application.models.query import SQLGenerationResponse


class PipelineModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PipelineIssue(PipelineModel):
    stage: Literal['planning', 'handoff', 'sql_generation', 'sql_validation', 'evaluation']
    code: str
    task_id: str | None = None
    message: str


class TaskSQLInput(PipelineModel):
    original_request: str = Field(min_length=1, max_length=4000)
    task: PlanningTask
    contract_fingerprint: str = Field(min_length=1)


class TaskSQLResult(PipelineModel):
    task_id: str
    status: Literal['ready', 'needs_confirmation', 'needs_clarification', 'unsupported', 'cancelled', 'error']
    generation: SQLGenerationResponse | None = None
    issues: list[PipelineIssue] = Field(default_factory=list)
    gate_passed: bool = False

    @model_validator(mode='after')
    def check_generation(self):
        if self.generation is not None and self.generation.status != self.status:
            raise ValueError('task and generation status differ')
        if self.status != 'ready' and self.generation is not None and self.generation.sql:
            raise ValueError('only ready tasks may carry SQL')
        return self


class QueryPipelineResponse(PipelineModel):
    run_id: str
    status: Literal['sql_ready', 'needs_clarification', 'needs_confirmation', 'unsupported', 'error']
    planning: DecompositionResponse | None = None
    task_results: list[TaskSQLResult] = Field(default_factory=list)
    skipped_task_ids: list[str] = Field(default_factory=list)
    issues: list[PipelineIssue] = Field(default_factory=list)
    contract_fingerprint: str
    semantic_review_required: bool = True

    @model_validator(mode='after')
    def check_completion(self):
        tasks = self.planning.draft.tasks if self.planning and self.planning.draft else []
        ids = [t.task_id for t in tasks]
        results = [t.task_id for t in self.task_results]
        skipped = self.skipped_task_ids
        if (len(results) != len(set(results))
                or len(skipped) != len(set(skipped)) or not set(results + skipped) <= set(ids)
                or set(results) & set(skipped)):
            raise ValueError('duplicate, unknown or overlapping task IDs')
        if self.status == 'sql_ready':
            if (not self.planning or self.planning.status != 'ready' or not tasks or len(ids) != len(set(ids))
                    or self.contract_fingerprint != self.planning.contract_fingerprint
                    or set(results) != set(ids) or skipped or self.issues):
                raise ValueError('sql_ready requires every approved task and no issues or skips')
            for item in self.task_results:
                if (item.status != 'ready' or not item.gate_passed or item.issues
                        or not item.generation or not item.generation.query_plan):
                    raise ValueError('sql_ready requires gate-validated generations')
        else:
            # Copy instead of destroying the diagnostic object retained by the observer.
            sanitized = []
            for result in self.task_results:
                generation = result.generation
                if result.status == 'ready':
                    generation = None
                elif generation is not None:
                    generation = generation.model_copy(update={'query_trace': None, 'query_plan': None})
                sanitized.append(result.model_copy(update={'generation': generation}))
            self.task_results = sanitized
        return self
