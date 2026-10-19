from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator, model_validator
from cpea.application.models.confirmation import Clarification, TermMappingReasoning

from cpea.domain.models import QueryFact, QueryPlan, SchemaLink
from cpea.workflows.text_to_sql.schemas import SchemaLinkDraft, SQLClauseMapping, SQLClauseMappingV3, SQLClauseMappingV10

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
    mapping: SQLClauseMappingV10 | SQLClauseMappingV3 | SQLClauseMapping | None = None
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
    run_id: str | None = Field(default=None, exclude=True)
    status: Literal['ready', 'needs_confirmation', 'needs_clarification', 'unsupported', 'cancelled', 'error'] = 'unsupported'
    code: str | None = None
    clarification: Clarification | ClarificationRequest | None = None
    term_mapping_reasoning: list[TermMappingReasoning] = Field(default_factory=list)
    supported: bool
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

    @model_validator(mode='before')
    @classmethod
    def infer_legacy_status(cls, value):
        if isinstance(value, dict) and 'status' not in value:
            value = {**value, 'status': 'ready' if value.get('supported') and value.get('sql') else 'unsupported'}
        return value

    @model_validator(mode='after')
    def check_status(self):
        if self.status == 'ready':
            if not self.supported or not self.sql:
                raise ValueError('ready requires supported and SQL')
        elif self.supported or self.sql is not None:
            raise ValueError('only ready may expose SQL or supported=true')
        expected = {'needs_confirmation': Clarification, 'needs_clarification': ClarificationRequest}
        if self.status in expected:
            if not isinstance(self.clarification, expected[self.status]):
                raise ValueError('clarification payload does not match its status')
        elif self.clarification is not None:
            raise ValueError('clarification requires a pending confirmation status')
        return self

class AssistantQueryResponse(BaseModel):
    term_mapping_reasoning: list[TermMappingReasoning] = Field(default_factory=list)
    answer: str
    citations: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    sql: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    rows_truncated: bool = False
    generation: SQLGenerationResponse
