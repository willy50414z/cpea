"""Planning-only contracts; these carry no SQL or database results."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field


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
