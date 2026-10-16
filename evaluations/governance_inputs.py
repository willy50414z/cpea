"""Validated, credential-free inputs for model governance runs."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from evaluations.runners.query_reliability import QueryReliabilityCase
from evaluations.view_matching_cases import ViewMatchingCase


class ProjectCase(QueryReliabilityCase):
    """One stable, project-bound reliability case in the unified JSONL file."""
    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    category: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    profile_id: str = Field(min_length=1)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedResult(StrictModel):
    supported: bool | None = None
    view: str | None = None
    filters: dict[str, str] = Field(default_factory=dict)
    forbidden_filters: list[str] = Field(default_factory=list)
    forbidden_views: list[str] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    aggregations: dict[str, str] = Field(default_factory=dict)
    sql_forbidden: list[str] = Field(default_factory=list)
    answer_contains: list[str] = Field(default_factory=list)
    answer_excludes: list[str] = Field(default_factory=list)
    require_citation: bool = False
    clarification: bool = False
    human_review: bool = False

    @model_validator(mode="after")
    def meaningful(self):
        other_checks = any(value for key, value in self.model_dump().items()
                           if key not in {"supported", "human_review"})
        if self.supported is None and not other_checks and not self.human_review:
            raise ValueError("expected_result requires at least one check")
        return self


class GovernanceCase(StrictModel):
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    category: Literal["simple", "complex", "ambiguous", "security", "core", "colloquial", "normal", "unsupported"]
    difficulty: Literal["easy", "medium", "hard"]
    question: str = Field(min_length=1)
    expected_result: ExpectedResult
    reliability_case: QueryReliabilityCase | None = None
    view_matching_case: ViewMatchingCase | None = None


class CaseFile(StrictModel):
    version: Literal[1]
    cases: list[GovernanceCase] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_ids(self):
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("case_id must be unique")
        return self


class ModelTarget(StrictModel):
    provider: Literal["local", "azure", "gcp"]
    model: str = Field(min_length=1)
    transport: Literal["ollama", "llamacpp", "azure", "google"]
    deployment: str | None = None
    node_name: str | None = None
    endpoint_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    api_key_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    project_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    location_env: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]*$")
    num_ctx: int | None = Field(default=None, ge=1024)
    max_token: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0)
    top_p: float | None = Field(default=None, gt=0, le=1)

    @model_validator(mode="after")
    def matching_transport(self):
        allowed = {"local": {"ollama", "llamacpp"}, "azure": {"azure"}, "gcp": {"google"}}
        if self.transport not in allowed[self.provider]:
            raise ValueError("provider and transport do not match")
        if self.provider != "local" and not self.deployment:
            raise ValueError("cloud target requires deployment")
        return self


class ModelFile(StrictModel):
    version: Literal[1]
    models: list[ModelTarget] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_targets(self):
        ids = [(target.provider, target.model, target.deployment) for target in self.models]
        if len(ids) != len(set(ids)):
            raise ValueError("model targets must be unique")
        return self


def load_cases(path: str | Path) -> CaseFile:
    if Path(path).suffix.lower() == ".jsonl":
        lines = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        project_format = any("case_id" in case for case in lines)
        if project_format and not all("case_id" in case for case in lines):
            raise ValueError("project case file mixes stable and legacy case formats")
        cases = [ViewMatchingCase.model_validate(case) if case.get("case_kind") == "view_matching"
                 else ProjectCase.model_validate(case) if project_format else QueryReliabilityCase.model_validate(case)
                 for case in lines]
        return CaseFile(version=1, cases=[GovernanceCase(
            case_id=case.case_id if isinstance(case, (ProjectCase, ViewMatchingCase)) else f"RELIABILITY-{index:03d}",
            category=case.category if isinstance(case, (ProjectCase, ViewMatchingCase)) else ("simple" if case.expected_supported else "security"),
            difficulty=({"S": "easy", "M": "medium", "H": "hard"}.get(case.sql_difficulty, "medium")
                        if isinstance(case, ViewMatchingCase) else case.difficulty if isinstance(case, ProjectCase) else "medium"),
            question=case.request if isinstance(case, ViewMatchingCase) else case.question,
            expected_result=ExpectedResult(supported=case.category == "normal" if isinstance(case, ViewMatchingCase) else case.expected_supported),
            reliability_case=None if isinstance(case, ViewMatchingCase) else QueryReliabilityCase.model_validate(case.model_dump()),
            view_matching_case=case if isinstance(case, ViewMatchingCase) else None,
        ) for index, case in enumerate(cases, 1)])
    return CaseFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))


def load_models(path: str | Path) -> ModelFile:
    return ModelFile.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
