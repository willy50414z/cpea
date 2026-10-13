from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

def _normalize_string_list(value: object) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [] if value.strip() in {"未指定", "無", "none", "None"} else [value]
    return value

def _normalize_limitations(value: object) -> list[str]:
    """Accept the empty string some local models emit for no limitations."""
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    return value

class QueryFilter(BaseModel):
    column: str
    operator: str
    value: str | int | float | list[str | int | float]

class QueryFact(BaseModel):
    kind: Literal["entity", "metric", "dimension", "time", "constraint", "other"]
    text: str
    required: bool = True
    reason: str = ""

class SchemaLink(BaseModel):
    fact_text: str
    view: str
    column: str
    role: Literal["filter", "metric", "dimension"]
    operator: str | None = None
    value: str | int | float | list[str | int | float] | None = None
    aggregation: str | None = None

class QueryPlan(BaseModel):
    """Validated plan handed to the SQL node; it deliberately contains no SQL."""

    supported: bool = False
    source_views: list[str] = Field(default_factory=list)
    select_columns: list[str] = Field(default_factory=list)
    filters: list[QueryFilter] = Field(default_factory=list)
    group_by: list[str] = Field(default_factory=list)
    order_by: list[str] = Field(default_factory=list)
    aggregations: dict[str, str] = Field(default_factory=dict)
    limit: int | None = Field(default=None, ge=1, le=10000)
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)

    _normalize_source_views = field_validator("source_views", mode="before")(
        _normalize_string_list
    )
    _normalize_select_columns = field_validator("select_columns", mode="before")(
        _normalize_string_list
    )
    _normalize_group_by = field_validator("group_by", mode="before")(
        _normalize_string_list
    )
    _normalize_order_by = field_validator("order_by", mode="before")(
        _normalize_string_list
    )
    _normalize_limitations = field_validator("limitations", mode="before")(_normalize_limitations)
