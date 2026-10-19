from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

from cpea.domain.models import QueryFact, QueryPlan, SchemaLink
from cpea.workflows.text_to_sql.schemas import SchemaLinkDraft, SQLClauseMapping, SQLClauseMappingV3

class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)

class SourceReference(BaseModel):
    document_id: str
    source: str
    filename: str
    section: str | None = None
    page: int | None = None
    chunk_id: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    retrieval_score: float | None = None
    reranker_score: float | None = None

class CandidateAttempt(BaseModel):
    view: str
    outcome: Literal["matched", "schema_mismatch", "validation_failed", "context_budget", "ambiguous"]
    facts: list[QueryFact] = Field(default_factory=list)
    links: list[SchemaLink] = Field(default_factory=list)
    unresolved: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

class MappingAttempt(BaseModel):
    attempt_index: int
    mapping: SQLClauseMappingV3 | SQLClauseMapping | None = None
    outcome: Literal["selected", "candidate", "rejected", "parse_error"]
    reason: str | None = None

class QueryTaskTrace(BaseModel):
    request: str
    links: SchemaLinkDraft | None = None
    request_facts: list[QueryFact] = Field(default_factory=list)
    candidate_attempts: list[CandidateAttempt] = Field(default_factory=list)
    mapping_attempts: list[MappingAttempt] = Field(default_factory=list)
    selected_mapping_index: int | None = None
    mapping_unavailable_reason: str | None = None
    selected_view: str | None = None
    plan: QueryPlan | None = None
    sql: str | None = None
    sources: list[SourceReference] = Field(default_factory=list)
    rejection_stage: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    execution_attempts: int = 0
    result_columns: list[str] = Field(default_factory=list)
    rows_truncated: bool = False
    execution_error: str | None = None

class ClarificationOption(BaseModel):
    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    description: str = Field(min_length=1)


class ClarificationRequest(BaseModel):
    original_request: str = Field(min_length=1)
    contract_fingerprint: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: list[ClarificationOption] = Field(min_length=2)

    @model_validator(mode="after")
    def distinct_options(self):
        if len({item.id for item in self.options}) != len(self.options):
            raise ValueError("clarification option ids must be distinct")
        return self


class ClarificationChoice(BaseModel):
    option_id: str = Field(min_length=1)
    contract_fingerprint: str = Field(min_length=1)


class SQLGenerationResponse(BaseModel):
    supported: bool
    status: Literal["ready", "needs_clarification", "unsupported"] | None = None
    clarification: ClarificationRequest | None = None
    sql: str | None = None
    selected_views: list[str] = Field(default_factory=list)
    explanation: str
    limitations: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    retrieved_candidates: list[SourceReference] = Field(default_factory=list)
    context_tokens: int = 0
    context_budget: int = 0
    retrieval_latency_ms: float = 0.0
    reranker_latency_ms: float = 0.0
    query_plan: QueryPlan | None = None
    query_trace: QueryTaskTrace | None = None

    @model_validator(mode="after")
    def coherent_status(self):
        if self.status is None:
            self.status = "ready" if self.supported else "unsupported"
        if self.status == "needs_clarification":
            if self.supported or self.sql is not None or self.clarification is None:
                raise ValueError("clarification responses cannot contain SQL")
        elif self.clarification is not None or self.supported != (self.status == "ready"):
            raise ValueError("SQL generation status does not match its payload")
        return self

class AssistantQueryResponse(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    rows_truncated: bool = False
    generation: SQLGenerationResponse
