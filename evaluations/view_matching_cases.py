"""Contract-bound View Matching cases for the shared project evaluator."""

from __future__ import annotations

from hashlib import sha256
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from cpea.domain.models import HavingFilter, QueryFilter, QueryPlan
from cpea.infrastructure.llm.factory import response_schema_for
from cpea.infrastructure.sql_compiler import compile_single_view
from cpea.infrastructure.sql_policy import validate_generated_sql
from cpea.workflows.text_to_sql.schemas import SQLClauseMapping, SQLClauseMappingV3
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExpectedSQL(StrictModel):
    select_columns: list[str]
    filters: list[QueryFilter]
    having: list[HavingFilter] | None = None
    aggregations: dict[str, Literal["sum", "count", "count_distinct", "avg", "min", "max"]]
    group_by: list[str]
    order_by: list[str]
    order_directions: dict[str, Literal["asc", "desc"]] = Field(default_factory=dict)


class ViewMatchingCase(StrictModel):
    case_kind: Literal["view_matching"]
    case_format_version: Literal[1]
    case_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
    profile_id: str
    contract_fingerprint: str = Field(min_length=64, max_length=64)
    prompt_version: str
    prompt_sha256: str = Field(min_length=64, max_length=64)
    target_view: str
    candidate_views: list[str]
    sql_difficulty: Literal["S", "M", "H"] | None
    semantic_difficulty: Literal["L1", "L2", "L3"] | None
    category: Literal["normal", "unsupported", "ambiguous", "security"]
    request: str = Field(min_length=1)
    expected_match: SQLClauseMappingV3 | SQLClauseMapping
    expected_sql: ExpectedSQL | None
    rationale: str
    validation_status: Literal["validated", "needs_review"]
    review_status: Literal["pending", "approved", "rejected"]
    reviewer: str | None = None
    reviewed_at: str | None = None
    reviewed_case_sha256: str | None = None
    reviewed_contract_fingerprint: str | None = None
    unsupported_evidence: str | None = None

    @model_validator(mode="before")
    @classmethod
    def expected_match_shape(cls, data):
        if isinstance(data, dict) and isinstance(data.get("expected_match"), dict):
            mapping = data["expected_match"]
            has_having = data.get("prompt_version") in {"v3", "v4", "v5", "v6", "v7", "v8", "v9"}
            required = {"fields", "table", "criteria", "order", "group", "ignored"} | ({"having"} if has_having else set())
            if not required <= mapping.keys() or set(mapping) - (required | {"unsupported_reason"}):
                raise ValueError("expected_match does not match MATCH_PROMPT keys")
            shapes = {"fields": {"text", "column", "aggregation"},
                      "criteria": {"text", "column", "operator", "value"},
                      "group": {"text", "column"},
                      "ignored": {"text", "reason"}}
            if has_having:
                shapes["having"] = {"text", "column", "aggregation", "operator", "value"}
            for key, keys in shapes.items():
                if not isinstance(mapping[key], list) or any(not isinstance(item, dict) or set(item) != keys
                                                              for item in mapping[key]):
                    raise ValueError(f"expected_match.{key} has invalid shape")
            if not isinstance(mapping["order"], list) or any(
                    not isinstance(item, dict) or not {"text", "column"} <= set(item)
                    or set(item) - {"text", "column", "direction"}
                    for item in mapping["order"]):
                raise ValueError("expected_match.order has invalid shape")
            if mapping["table"] is not None and (not isinstance(mapping["table"], dict)
                or set(mapping["table"]) != {"text", "view"}):
                raise ValueError("expected_match.table has invalid shape")
        return data

    @model_validator(mode="after")
    def coherent(self):
        if self.target_view not in self.candidate_views or len(self.candidate_views) != len(set(self.candidate_views)):
            raise ValueError("candidate_views must contain the target View exactly once")
        normal = self.category == "normal"
        if (self.prompt_version in {"v3", "v4", "v5", "v6", "v7", "v8", "v9"}) != isinstance(self.expected_match, SQLClauseMappingV3):
            raise ValueError("expected_match shape does not match prompt version")
        if normal and self.prompt_version in {"v3", "v4", "v5", "v6", "v7", "v8", "v9"} and self.expected_sql.having is None:
            raise ValueError("v3+ normal cases require expected_sql.having")
        if normal != (self.expected_sql is not None):
            raise ValueError("normal cases require expected_sql; rejection cases must omit it")
        if normal and (self.expected_match.table is None or
                       ("-G-" not in self.case_id and "-B-" not in self.case_id and
                        (self.sql_difficulty is None or self.semantic_difficulty is None))):
            raise ValueError("normal cases require both difficulty labels and a selected table")
        if not normal and (self.expected_match.table is not None or not self.unsupported_evidence):
            raise ValueError("rejection cases require table=null and unsupported evidence")
        if self.review_status == "approved" and not all((self.reviewer, self.reviewed_at,
                self.reviewed_case_sha256, self.reviewed_contract_fingerprint)):
            raise ValueError("approved cases require reviewer, time and case/contract fingerprints")
        return self

    def content_sha256(self) -> str:
        fields = self.model_dump(mode="json", exclude={"review_status", "reviewer", "reviewed_at",
                                                       "reviewed_case_sha256", "reviewed_contract_fingerprint"})
        if self.prompt_version not in {"v3", "v4", "v5", "v6", "v7", "v8", "v9"} and fields.get("expected_sql") is not None:
            fields["expected_sql"].pop("having", None)
        return sha256(json.dumps(fields, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()

    def approved_for(self, fingerprint: str) -> bool:
        return (self.review_status == "approved" and self.validation_status == "validated"
                and self.reviewed_case_sha256 == self.content_sha256()
                and self.reviewed_contract_fingerprint == fingerprint)


def validate_view_case(case: ViewMatchingCase, catalog) -> None:
    """Reject invalid ground truth before any model call."""
    if case.profile_id != catalog.profile_id or case.contract_fingerprint != catalog.fingerprint:
        raise ValueError(f"{case.case_id}: profile or contract fingerprint mismatch")
    prompt = load_match_prompt(case.prompt_version)
    if case.prompt_sha256 != prompt.system_sha256:
        raise ValueError(f"{case.case_id}: MATCH_PROMPT fingerprint mismatch")
    views = {definition.name for definition in catalog.views()}
    if not set(case.candidate_views) <= views:
        raise ValueError(f"{case.case_id}: candidate View outside catalog")
    if case.review_status == "approved" and not case.approved_for(catalog.fingerprint):
        raise ValueError(f"{case.case_id}: stale human approval")
    mapping = case.expected_match
    if isinstance(mapping.table, list):
        raise ValueError(f"{case.case_id}: multiple Views in expected_match")
    # Compare the actual constrained schema's column and View enums as well as Pydantic shape.
    columns = {column for view in case.candidate_views for column in catalog.columns(view)}
    schema = response_schema_for(prompt.response_model, column_names=columns, view_names=set(case.candidate_views))
    for item in [*mapping.fields, *mapping.criteria, *getattr(mapping, "having", []), *mapping.group, *mapping.order]:
        if item.column not in schema["$defs"]["ClauseColumn"]["properties"]["column"]["enum"]:
            raise ValueError(f"{case.case_id}: unknown mapping column {item.column}")
        if not item.text or item.text not in case.request:
            raise ValueError(f"{case.case_id}: mapping text absent from request")
    for item in mapping.ignored:
        if item.text not in case.request:
            raise ValueError(f"{case.case_id}: ignored text absent from request")
    if mapping.table and mapping.table.text and mapping.table.text not in case.request:
        raise ValueError(f"{case.case_id}: table text absent from request")
    if mapping.table and mapping.table.view not in case.candidate_views:
        raise ValueError(f"{case.case_id}: mapping View outside candidates")
    if case.category != "normal":
        return
    if not mapping.table or mapping.table.view != case.target_view:
        raise ValueError(f"{case.case_id}: expected table differs from target View")
    spec = case.expected_sql
    assert spec is not None
    if [field.column for field in mapping.fields] != spec.select_columns:
        raise ValueError(f"{case.case_id}: mapping SELECT differs from expected_sql")
    if [item.column for item in mapping.group] != spec.group_by or [item.column for item in mapping.order] != spec.order_by:
        raise ValueError(f"{case.case_id}: mapping GROUP/ORDER differs from expected_sql")
    if {item.column: item.direction for item in mapping.order if item.direction != "asc"} != spec.order_directions:
        raise ValueError(f"{case.case_id}: mapping ORDER direction differs from expected_sql")
    if [item.model_dump(exclude={"text"}) for item in mapping.criteria] != [item.model_dump() for item in spec.filters]:
        raise ValueError(f"{case.case_id}: mapping criteria differ from expected_sql")
    if [item.model_dump(exclude={"text"}) for item in getattr(mapping, "having", [])] != [item.model_dump() for item in (spec.having or [])]:
        raise ValueError(f"{case.case_id}: mapping HAVING differs from expected_sql")
    if {item.column: item.aggregation for item in mapping.fields if item.aggregation} != spec.aggregations:
        raise ValueError(f"{case.case_id}: mapping aggregations differ from expected_sql")
    for item in mapping.criteria:
        values = item.value if isinstance(item.value, list) else [item.value]
        if not all(str(value) in item.text for value in values):
            raise ValueError(f"{case.case_id}: filter value not grounded in criteria text")
    for item in getattr(mapping, "having", []):
        if str(item.value) not in item.text:
            raise ValueError(f"{case.case_id}: HAVING value not grounded in text")
    columns = set(spec.select_columns) | {item.column for item in spec.filters} | set(spec.group_by) | set(spec.order_by)
    funcs = set(spec.aggregations.values())
    is_grid = "-G-" not in case.case_id and "-B-" not in case.case_id
    if is_grid and case.sql_difficulty == "S" and (len(columns) > 4 or not spec.filters or spec.group_by or spec.order_by or funcs):
        raise ValueError(f"{case.case_id}: S difficulty mismatch")
    if is_grid and case.sql_difficulty in {"M", "H"} and (len(columns) < (6 if case.sql_difficulty == "M" else 8)
        or len(spec.group_by) < (1 if case.sql_difficulty == "M" else 3)
        or len(funcs) < 2 or len(spec.filters) < (1 if case.sql_difficulty == "M" else 2)
        or not spec.order_by):
        raise ValueError(f"{case.case_id}: {case.sql_difficulty} difficulty mismatch")
    plan = QueryPlan(supported=True, source_views=[case.target_view], select_columns=spec.select_columns,
                     filters=spec.filters, having=spec.having or [], group_by=spec.group_by, order_by=spec.order_by,
                     aggregations=spec.aggregations, order_directions=spec.order_directions)
    sql = compile_single_view(plan, catalog, request=case.request)
    validate_generated_sql(sql, {case.target_view})
