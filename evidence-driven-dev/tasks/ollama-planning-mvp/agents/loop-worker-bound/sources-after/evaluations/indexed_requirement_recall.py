"""Model-selected source offsets; request quotations are derived by Python."""
from typing import Literal

from pydantic import Field
from cpea.application.models.decomposition import PlanningModel
from evaluations.three_stage_view_selection import CandidateView, Requirement, RecallResult, validate_recall

VERSION = 'three-stage-view-selection-indexed-1'


class IndexedRequirement(PlanningModel):
    requirement_id: str = Field(min_length=1)
    start: int = Field(ge=0, strict=True, description='Zero-based Python Unicode code-point index, inclusive.')
    end: int = Field(ge=1, strict=True, description='Zero-based Python Unicode code-point index, exclusive.')
    business_object: str = Field(min_length=1)
    kind: Literal['metric', 'attribute', 'filter', 'key', 'metadata', 'grain', 'population']
    scope_ids: list[str] = Field(default_factory=list, description='Filter requirement IDs applying to this requirement on the SAME source/task.')
    grain: str = Field(min_length=1)
    population: str = Field(min_length=1)


class IndexedRecallResult(PlanningModel):
    requirements: list[IndexedRequirement] = Field(min_length=1, max_length=24)
    candidate_views: list[CandidateView] = Field(min_length=1)


def request_index(request):
    return [{'index': i, 'character': character} for i, character in enumerate(request)]


def materialize_recall(indexed, request, catalog):
    requirements = []
    for item in indexed.requirements:
        if not 0 <= item.start < item.end <= len(request):
            raise ValueError(f'{item.requirement_id}: source span out of bounds or empty')
        quote = request[item.start:item.end]
        if not quote.strip():
            raise ValueError(f'{item.requirement_id}: blank source span')
        requirements.append(Requirement(**item.model_dump(exclude={'start', 'end'}), quote=quote))
    return validate_recall(RecallResult(requirements=requirements, candidate_views=indexed.candidate_views), request, catalog)
