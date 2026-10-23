"""The independent planner extends the existing dispatch boundary with a trace."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from cpea.application.models.decomposition import DecompositionResponse, PlanningModel
from cpea.workflows.task_decomposition.mapping_models import (
    MappingReview, RequirementExtraction, TaskBinding, ViewMapping, ViewSelectionTrace)


class MappingStage(PlanningModel):
    stage: Literal['extract', 'map_view', 'review', 'plan_draft']
    view: str | None = None
    status: Literal['completed', 'error'] = 'completed'
    context_tokens: int = 0
    code: str | None = None


class MappingTrace(PlanningModel):
    version: str = 'schema-mapping-v1'
    request: str = ''
    retrieval: ViewSelectionTrace | None = None
    extraction: RequirementExtraction | None = None
    mappings: list[ViewMapping] = Field(default_factory=list)
    review: MappingReview | None = None
    bindings: list[TaskBinding] = Field(default_factory=list)
    stages: list[MappingStage] = Field(default_factory=list)


class SchemaMappingDecompositionResponse(DecompositionResponse):
    trace: MappingTrace = Field(default_factory=MappingTrace)
