"""Evidence-bearing contracts used only by the independent mapping planner."""
from __future__ import annotations

from typing import Literal

from pydantic import Field

from cpea.application.models.decomposition import DecompositionDraft, PlanningFilter, PlanningModel

Operation = Literal['attribute', 'metric', 'filter', 'grain', 'metadata']
RequirementKind = Literal['concept', 'time', 'value', 'grain', 'population', 'purpose', 'prohibition']


class RequestSpan(PlanningModel):
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    text: str = Field(min_length=1)


class Requirement(PlanningModel):
    id: str = Field(min_length=1)
    span: RequestSpan
    kind: RequirementKind
    required: bool = True
    related_ids: list[str] = Field(default_factory=list)


class SyntaxFragment(PlanningModel):
    span: RequestSpan
    kind: Literal['syntax', 'punctuation']


class RequirementExtraction(PlanningModel):
    requirements: list[Requirement] = Field(min_length=1)
    syntax: list[SyntaxFragment] = Field(default_factory=list)


class ContractEvidence(PlanningModel):
    path: list[str | int] = Field(min_length=1)
    quote: str = Field(min_length=1)


class ColumnCandidate(PlanningModel):
    id: str = Field(min_length=1)
    column: str = Field(min_length=1)
    operations: list[Operation] = Field(min_length=1)
    reason: str = Field(min_length=1)
    evidence: list[ContractEvidence] = Field(min_length=1)


class RequirementMatch(PlanningModel):
    requirement_id: str = Field(min_length=1)
    status: Literal['matched', 'unmatched', 'constraint_only']
    candidates: list[ColumnCandidate] = Field(default_factory=list)
    reason: str = Field(min_length=1)


class ViewMapping(PlanningModel):
    view: str = Field(min_length=1)
    results: list[RequirementMatch]


class AuxiliaryColumn(PlanningModel):
    view: str = Field(min_length=1)
    column: str = Field(min_length=1)
    requirement_ids: list[str] = Field(min_length=1)
    operations: list[Operation] = Field(min_length=1)
    evidence: list[ContractEvidence] = Field(min_length=1)
    reason: str = Field(min_length=1)


class ReviewedFilter(PlanningModel):
    view: str = Field(min_length=1)
    condition: PlanningFilter


class ForbiddenUse(PlanningModel):
    view: str = Field(min_length=1)
    column: str = Field(min_length=1)
    operations: list[Operation] = Field(min_length=1)


class ConstraintDecision(PlanningModel):
    requirement_id: str = Field(min_length=1)
    kind: Literal['time', 'value', 'population', 'purpose', 'prohibition']
    anchor_view: str | None = None
    filters: list[ReviewedFilter] = Field(default_factory=list)
    forbidden_uses: list[ForbiddenUse] = Field(default_factory=list)
    note: str = Field(min_length=1)


class CandidateRejection(PlanningModel):
    candidate_id: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class MappingReview(PlanningModel):
    status: Literal['ready', 'needs_clarification', 'unsupported']
    selected_candidate_ids: list[str] = Field(default_factory=list)
    auxiliary_columns: list[AuxiliaryColumn] = Field(default_factory=list)
    constraints: list[ConstraintDecision] = Field(default_factory=list)
    missing_requirements: list[RequestSpan] = Field(default_factory=list)
    rejected_candidates: list[CandidateRejection] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)


class TaskBinding(PlanningModel):
    requirement_id: str = Field(min_length=1)
    task_id: str = Field(min_length=1)
    columns: list[str] = Field(min_length=1)


class MappedDraft(PlanningModel):
    draft: DecompositionDraft
    bindings: list[TaskBinding] = Field(default_factory=list)


class RetrievedView(PlanningModel):
    view: str
    retrieval_score: float | None = None
    reranker_score: float | None = None
    reasons: list[str] = Field(default_factory=list)


class ExcludedView(PlanningModel):
    view: str
    reason: str = 'below_cutoff_or_not_returned'


class ViewSelectionTrace(PlanningModel):
    status: Literal['pending', 'completed', 'error'] = 'pending'
    query: str = ''
    limit: int = 0
    candidates: list[RetrievedView] = Field(default_factory=list)
    excluded: list[ExcludedView] = Field(default_factory=list)
    retrieval_latency_ms: float = 0
    reranker_latency_ms: float = 0
    code: str | None = None
