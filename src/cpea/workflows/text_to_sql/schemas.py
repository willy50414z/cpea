from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

from cpea.domain.models import QueryFact, SchemaLink, _normalize_limitations, validate_numeric_threshold

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


class ClauseField(ClauseColumn):
    aggregation: Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max'] | None = None


class ClauseOrder(ClauseColumn):
    direction: Literal['asc', 'desc'] = 'asc'


class ClauseCriterion(ClauseColumn):
    operator: str = "="
    value: str | int | float | list[str | int | float]

    @model_validator(mode="before")
    @classmethod
    def use_original_literal(cls, value: Any) -> Any:
        if isinstance(value, dict) and "value" not in value and isinstance(value.get("text"), str):
            return {**value, "value": value["text"]}
        return value


class ClauseHaving(ClauseColumn):
    aggregation: Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max']
    operator: Literal['=', '!=', '<>', '>', '>=', '<', '<=']
    value: int | float

    _validate_value = field_validator("value", mode="before")(validate_numeric_threshold)


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
    fields: list[ClauseField] = Field(default_factory=list)
    table: ClauseTable | list[ClauseTable] | None = None
    criteria: list[ClauseCriterion] = Field(default_factory=list)
    order: list[ClauseOrder] = Field(default_factory=list)
    group: list[ClauseColumn] = Field(default_factory=list)
    ignored: list[IgnoredTerm] = Field(default_factory=list)
    unsupported_reason: str | None = None


class SQLClauseMappingV3(SQLClauseMapping):
    having: list[ClauseHaving]


class TermEvidence(BaseModel):
    clause: Literal['fields', 'criteria', 'group', 'order', 'having']
    index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=1)
    term: str = Field(min_length=1)
    candidates: list[str] = Field(default_factory=list)
    evidence_quote: str | None = None


class SyntaxSpan(BaseModel):
    kind: Literal['aggregation', 'operator', 'literal', 'source']
    clause: Literal['fields', 'criteria', 'group', 'order', 'having', 'table']
    index: int = Field(ge=0)
    start: int = Field(ge=0)
    end: int = Field(ge=1)


class SemanticOption(BaseModel):
    column: str
    label: str = Field(min_length=1, max_length=60)
    evidence_quote: str = Field(min_length=1)
    same_concept: bool
    grain_compatible: bool


class SemanticClarification(BaseModel):
    term: str = Field(min_length=1)
    options: list[SemanticOption] = Field(default_factory=list)
    needs_refinement: bool = False


class ClarificationResolution(BaseModel):
    source_compatible: bool
    clarifications: list[SemanticClarification]


class SQLClauseMappingV10(SQLClauseMappingV3):
    # Defaults permit conservative migration of drafts; missing evidence never
    # grants trust. The server independently checks the entire original request.
    terms: list[TermEvidence] = Field(default_factory=list)
    syntax_spans: list[SyntaxSpan] = Field(default_factory=list)
    candidate_view: str | None = None
    clarifications: list[SemanticClarification] = Field(default_factory=list)
