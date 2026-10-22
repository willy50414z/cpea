"""Planning-only contracts; these carry no SQL or database results."""
from __future__ import annotations

from typing import Annotated, Any, Literal
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class PlanningModel(BaseModel):
    model_config = ConfigDict(extra='forbid')


class PlanningFilter(PlanningModel):
    column: str
    operator: Literal['=', '!=', '<>', '>', '>=', '<', '<=', 'IN', 'NOT IN', 'LIKE', 'IS NULL', 'IS NOT NULL']
    value: Any = None


class ConditionalMetric(PlanningModel):
    column: str
    aggregation: Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max']
    conditions: list[PlanningFilter]


class PlanningTask(PlanningModel):
    task_id: str = Field(min_length=1)
    view: str = Field(min_length=1)
    required_columns: list[str] = Field(min_length=1)
    filters: list[PlanningFilter] = Field(default_factory=list)
    metrics: dict[str, Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max']] = Field(default_factory=dict)
    conditional_metrics: list[ConditionalMetric] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)
    metadata_collections: list[str] = Field(default_factory=list, description='Date/string provenance collected as DISTINCT values at output_grain; never an extra grouping dimension or a measure.')
    group_by: list[str] = Field(default_factory=list)
    output_grain: list[str] = Field(min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    unbound_inputs: list[str] = Field(default_factory=list)
    request: str = Field(min_length=1, max_length=4000)


class Preparation(PlanningModel):
    task_id: str
    kind: Literal['aggregate', 'nest', 'pivot', 'attach_context']
    keys: list[str]
    description: str = Field(min_length=1)


class IntegrationEdge(PlanningModel):
    left_task: str
    right_task: str
    left_keys: list[str] = Field(min_length=1)
    right_keys: list[str] = Field(min_length=1)
    mode: Literal['left', 'inner', 'full'] = 'left'
    cardinality: Literal['one_to_one', 'one_to_many', 'many_to_one', 'many_to_many']
    preserve_task: str | None = None


class IntegrationPlan(PlanningModel):
    anchor_task: str
    output_grain: list[str] = Field(min_length=1)
    edges: list[IntegrationEdge] = Field(default_factory=list)
    preparation: list[Preparation] = Field(default_factory=list)
    missing_data_policy: str = '保留未匹配資料並標記缺值；契約沒有保證時不可把缺值當成零。'
    notes: list[str] = Field(default_factory=list)


class DecompositionDraft(PlanningModel):
    status: Literal['ready', 'needs_clarification', 'unsupported', 'error']
    strategy: Literal['single_view', 'multi_view'] | None = None
    tasks: list[PlanningTask] = Field(default_factory=list)
    integration: IntegrationPlan | None = None
    clarifications: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


class PreparedSQLRequest(PlanningModel):
    task_id: str
    view: str
    payload: dict[str, Any]


class DecompositionResponse(PlanningModel):
    status: Literal['ready', 'needs_clarification', 'unsupported', 'error']
    code: str | None = None
    draft: DecompositionDraft | None = None
    prepared_requests: list[PreparedSQLRequest] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    contract_fingerprint: str
    context_tokens: int = 0
    token_counter: str = ''

    def model_post_init(self, __context):
        if self.status != 'ready' and self.prepared_requests:
            raise ValueError('only ready may expose prepared requests')


class PlanningDecisionSummary(PlanningModel):
    """Brief, auditable justifications; not a model's private reasoning trace."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    source_selection: str = Field(min_length=1, max_length=600, description='Briefly justify selected sources using request requirements and admitted capabilities.')
    field_roles: str = Field(min_length=1, max_length=600, description='Briefly justify output attributes, measures, conditional counts and time metadata.')
    conditions: str = Field(min_length=1, max_length=600, description='State the period and business conditions, and which source each applies to.')
    grain: str = Field(min_length=1, max_length=600, description='State root and child query grains and their contract basis.')
    population: str = Field(min_length=1, max_length=600, description='State the preserved population and the effects of filtering and missing matches.')
    integration: str = Field(min_length=1, max_length=600, description='Briefly justify alignment keys, join direction, child shape and background treatment.')


class ExplainedDecompositionDraft(DecompositionDraft):
    """Opt-in diagnostic generation schema; the original v3 schema is unchanged."""
    decision_summary: PlanningDecisionSummary


class ExplainedDecompositionResponse(DecompositionResponse):
    """Expose the diagnostic summary without including it in SQL requests."""
    decision_summary: PlanningDecisionSummary


DecisionStage = Literal['source_selection', 'field_roles', 'conditions', 'grain', 'population', 'integration']
DecisionEvidence = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=240)]


class PlanningDecisionRecord(PlanningModel):
    """A public decision and cited basis, never a private thought transcript."""
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    step_id: int = Field(ge=1, le=6)
    stage: DecisionStage
    decision: str = Field(min_length=1, max_length=400, description='A brief final planning choice, not step-by-step private reasoning.')
    evidence: list[DecisionEvidence] = Field(min_length=1, max_length=4, description='Short request quotes or admitted contract references; correctness is reviewed separately.')
    task_ids: list[str] = Field(max_length=8, description='IDs of actual tasks affected by this decision; empty only when no task applies.')
    depends_on: list[int] = Field(max_length=5, description='Only earlier step IDs in this public decision log; not a claim about internal thought order.')


def _validate_decision_chain(chain, task_ids):
    stages = {'source_selection', 'field_roles', 'conditions', 'grain', 'population', 'integration'}
    if {record.stage for record in chain} != stages:
        raise ValueError('decision_chain requires each of the six stages exactly once')
    if [record.step_id for record in chain] != list(range(1, 7)):
        raise ValueError('decision_chain step IDs must be ordered 1 through 6')
    for record in chain:
        if len(set(record.depends_on)) != len(record.depends_on) or any(dep < 1 or dep >= record.step_id for dep in record.depends_on):
            raise ValueError('decision_chain dependencies must reference earlier unique steps')
        if len(set(record.task_ids)) != len(record.task_ids) or not set(record.task_ids) <= task_ids:
            raise ValueError('decision_chain references unknown or duplicate tasks')


class DecisionChainDecompositionDraft(ExplainedDecompositionDraft):
    """Opt-in schema requiring the model to fill an ordered decision audit log."""
    decision_chain: list[PlanningDecisionRecord] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def check_decision_chain(self):
        _validate_decision_chain(self.decision_chain, {task.task_id for task in self.tasks})
        return self


class DecisionChainDecompositionResponse(ExplainedDecompositionResponse):
    decision_chain: list[PlanningDecisionRecord] = Field(min_length=6, max_length=6)

    @model_validator(mode='after')
    def check_decision_chain(self):
        task_ids = {task.task_id for task in self.draft.tasks} if self.draft else set()
        _validate_decision_chain(self.decision_chain, task_ids)
        return self
