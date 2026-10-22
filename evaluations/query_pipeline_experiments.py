"""Evaluation-only capability envelopes; never imported by product services."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from evaluations.query_pipeline_grading import content_hash

Capability = Literal['requirement_parsing', 'capability_resolution', 'query_planning',
                     'single_view_sql', 'semantic_validation', 'cross_view_integration']
Scope = Literal['internal_coverage', 'complete_planning', 'single_view_sql',
                'external_semantic_plan', 'full_architecture']
Verdict = Literal['PASS', 'FAIL', 'NOT_OBSERVED', 'NOT_APPLICABLE']
LAYERS = ('schema', 'references', 'requirements', 'integration', 'sql_static', 'natural')


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)


class StrategyDescriptor(Contract):
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    adapter_id: str = Field(min_length=1)
    adapter_version: str = Field(min_length=1)
    implementation_kind: Literal['product_service', 'research_candidate', 'external_engine']
    capabilities: list[Capability] = Field(min_length=1)
    input_kind: str
    output_kind: str
    native_schema_id: str
    native_schema_version: str
    package_versions: dict[str, str] = Field(default_factory=dict)
    requires_model: bool
    requires_db: bool
    dialects: list[str]
    limitations: list[str] = Field(default_factory=list)


class EvaluationInput(Contract):
    # Identity, approvals and oracles are deliberately excluded from model_context().
    case_ref: str
    case_sha256: str
    request: str = Field(min_length=1, max_length=4000)
    catalog_snapshot: dict[str, Any]
    catalog_fingerprint: str
    catalog_snapshot_sha256: str
    capability: Capability
    input_origin: Literal['original_request', 'approved_recall', 'approved_planning', 'approved_tasks', 'semantic_request']
    upstream_injected: bool
    approval_ref: str | None
    upstream: dict[str, Any] | None = None
    upstream_sha256: str | None = None

    @model_validator(mode='after')
    def verify_snapshot(self):
        if content_hash(self.catalog_snapshot) != self.catalog_snapshot_sha256:
            raise ValueError('catalog snapshot drift')
        if self.upstream_injected:
            if (not self.approval_ref or self.upstream is None
                    or self.upstream_sha256 != content_hash(self.upstream)
                    or self.input_origin == 'original_request'):
                raise ValueError('injected upstream requires approval and matching hash')
        elif self.upstream is not None or self.upstream_sha256 is not None or self.input_origin != 'original_request':
            raise ValueError('upstream must be explicitly injected')
        def reject_oracle(value):
            if isinstance(value, dict):
                if set(value) & {'oracle', 'expected_sql', 'case_id', 'approved_plans', 'output_reviews',
                                 'reviewer', 'reviewed_at', 'expected_stage_status'}:
                    raise ValueError('oracle/review metadata is forbidden in model context')
                for child in value.values():
                    reject_oracle(child)
            elif isinstance(value, list):
                for child in value:
                    reject_oracle(child)
        reject_oracle(self.upstream)
        return self

    def model_context(self):
        context = {'request': self.request, 'catalog': deepcopy(self.catalog_snapshot)}
        if self.upstream_injected:
            context['upstream'] = deepcopy(self.upstream)
        return context


class ArtifactReference(Contract):
    ref: str
    sha256: str


class StrategyObservation(Contract):
    node_id: str
    native_schema_id: str
    native_schema_version: str
    status: Literal['completed', 'failed', 'pending', 'unsupported', 'skipped', 'unfinished']
    raw: ArtifactReference | None = None
    parsed: ArtifactReference | None = None
    normalized: ArtifactReference | None = None
    calls: int = Field(default=0, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    token_counter: str = 'provider_usage_or_unknown'
    elapsed_ms: float | None = Field(default=None, ge=0)
    conversion_ms: float | None = Field(default=None, ge=0)
    retries: Literal[0] = 0
    first_error: str | None = None
    errors: list[str] = Field(default_factory=list)


class ExperimentManifest(Contract):
    schema_version: Literal['query-pipeline-experiment-v1'] = 'query-pipeline-experiment-v1'
    experiment_id: str = Field(min_length=1)
    scope: Scope
    mode: Literal['planning', 'sql', 'integrated']
    case_hashes: list[str] = Field(min_length=1)
    strategies: list[StrategyDescriptor] = Field(min_length=1)
    runs: int = Field(gt=0, strict=True)
    group: Literal['Regression', 'Diagnostic', 'Metamorphic', 'Holdout']
    preregistration_ref: str
    result_completeness: Literal['not_tested'] = 'not_tested'

    @model_validator(mode='after')
    def unique_cells(self):
        expected_mode = {'internal_coverage': 'planning', 'complete_planning': 'planning',
            'single_view_sql': 'sql', 'external_semantic_plan': 'planning', 'full_architecture': 'integrated'}[self.scope]
        if self.mode != expected_mode:
            raise ValueError('experiment scope/mode mismatch')
        keys = [(s.strategy_id, s.strategy_version, s.adapter_id, s.adapter_version) for s in self.strategies]
        if len(set(keys)) != len(keys) or len(set(self.case_hashes)) != len(self.case_hashes):
            raise ValueError('duplicate comparison cells')
        return self

    @computed_field
    @property
    def planned(self) -> int:
        return len(self.case_hashes) * len(self.strategies) * self.runs


class RequirementAssessment(Contract):
    requirement_id: str
    obligation: str
    evidence: list[str]
    verdict: Verdict
    coverage: Literal['satisfied', 'partial', 'missing', 'unsupported', 'clarification', 'unknown']
    derived_by_evaluator: bool = True


class SemanticAssessment(Contract):
    grading_version: str
    rules_sha256: str
    requirements: list[RequirementAssessment]
    layers: dict[str, Verdict]
    first_error: str | None
    independent_approval: bool = False
    natural_success: bool = False
    result_completeness: Literal['not_tested'] = 'not_tested'


def validate_strategy(strategy: StrategyDescriptor, value: EvaluationInput, *, scope: Scope):
    expected = {'internal_coverage': 'capability_resolution', 'complete_planning': 'query_planning',
                'single_view_sql': 'single_view_sql', 'external_semantic_plan': 'query_planning',
                'full_architecture': 'cross_view_integration'}[scope]
    if strategy.requires_db:
        raise ValueError('DB candidates are forbidden in static S1/R1/R2 evaluation')
    if expected not in strategy.capabilities or value.capability != expected:
        raise ValueError('candidate responsibility does not match experiment scope')
