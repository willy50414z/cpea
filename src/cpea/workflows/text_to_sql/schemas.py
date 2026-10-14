from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

from cpea.domain.models import QueryFact, SchemaLink, _normalize_limitations

class AnswerDraft(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)

class ViewSatisfiedFact(BaseModel):
    fact_text: str
    reason: str = Field(min_length=1)

class SchemaLinkDraft(BaseModel):
    supported: bool = False
    facts: list[QueryFact] = Field(default_factory=list)
    links: list[SchemaLink] = Field(default_factory=list)
    view_satisfied: list[ViewSatisfiedFact] = Field(default_factory=list)
    ambiguity: list[str] = Field(default_factory=list)
    requires_join: bool = False
    unresolved_facts: list[str] = Field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)

    _normalize_limitations = field_validator("limitations", mode="before")(_normalize_limitations)


class ClauseColumn(BaseModel):
    text: str
    column: str


class ClauseCriterion(ClauseColumn):
    operator: str = "="
    value: str | int | float | list[str | int | float]

    @model_validator(mode="before")
    @classmethod
    def use_original_literal(cls, value: Any) -> Any:
        if isinstance(value, dict) and "value" not in value and isinstance(value.get("text"), str):
            return {**value, "value": value["text"]}
        return value


class ClauseTable(BaseModel):
    text: str | None = None
    view: str

    @model_validator(mode="before")
    @classmethod
    def accept_view_column(cls, value: Any) -> Any:
        if isinstance(value, dict) and "view" not in value and "column" in value:
            return {**value, "view": value["column"]}
        return value


class IgnoredTerm(BaseModel):
    text: str = Field(min_length=1)
    reason: str = Field(min_length=1)


class SQLClauseMapping(BaseModel):
    fields: list[ClauseColumn] = Field(default_factory=list)
    table: ClauseTable | list[ClauseTable] | None = None
    criteria: list[ClauseCriterion] = Field(default_factory=list)
    order: list[ClauseColumn] = Field(default_factory=list)
    group: list[ClauseColumn] = Field(default_factory=list)
    ignored: list[IgnoredTerm] = Field(default_factory=list)
