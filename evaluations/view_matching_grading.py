"""Grade parsed View matching separately from compiled query structure."""

from __future__ import annotations

from collections import Counter
import json

from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.infrastructure.sql_compiler import compile_single_view
from evaluations.view_matching_cases import ViewMatchingCase


def _bag(values):
    return Counter(json.dumps(value, ensure_ascii=False, sort_keys=True) for value in values)


def _mapping_values(items, *, omit_text: bool = False):
    return _bag(item.model_dump(mode="json", exclude={"text"} if omit_text else None) for item in items)


def grade_view_matching(case: ViewMatchingCase, generation, *, catalog=None,
                        max_rows: int = 200, dialect: str = 'mssql') -> tuple[str, str, list[str]]:
    trace = generation.query_trace
    attempts = trace.mapping_attempts if trace else []
    if case.category == "normal":
        index = trace.selected_mapping_index if trace else None
        mapping = next((attempt.mapping for attempt in attempts if attempt.attempt_index == index), None)
    else:
        mapping = next((attempt.mapping for attempt in reversed(attempts) if attempt.mapping is not None), None)
    mapping_failures: list[str] = []
    expected = case.expected_match
    if mapping is None:
        mapping_failures.append("mapping_unavailable")
    else:
        if isinstance(mapping.table, list) or (mapping.table.view if mapping.table else None) != (
                expected.table.view if expected.table else None):
            mapping_failures.append("mapping_view")
        for key in ("fields", "criteria", "having", "group", "order"):
            actual = getattr(mapping, key, [])
            wanted = getattr(expected, key, [])
            if _mapping_values(actual, omit_text=True) != _mapping_values(wanted, omit_text=True):
                mapping_failures.append(f"mapping_{key}")
            if any(not item.text or item.text not in case.request for item in actual):
                mapping_failures.append(f"mapping_{key}_grounding")
        if mapping.table and not isinstance(mapping.table, list) and mapping.table.text and mapping.table.text not in case.request:
            mapping_failures.append("mapping_table_grounding")
        if any(item.text not in case.request for item in mapping.ignored):
            mapping_failures.append("mapping_ignored_grounding")
    mapping_status = "pass" if not mapping_failures else "unavailable" if mapping is None else "fail"

    sql_failures: list[str] = []
    if case.category != "normal":
        if generation.supported or generation.sql or generation.query_plan:
            sql_failures.append("unsupported_query_generated")
    else:
        spec = case.expected_sql
        assert spec is not None
        plan = generation.query_plan
        if not generation.supported or plan is None or not generation.sql:
            sql_failures.append("query_plan_unavailable")
        else:
            if generation.selected_views != [case.target_view] or plan.source_views != [case.target_view]:
                sql_failures.append("sql_view")
            if Counter(plan.select_columns) != Counter(spec.select_columns):
                sql_failures.append("sql_select")
            if _bag(item.model_dump(mode="json") for item in plan.filters) != _bag(item.model_dump(mode="json") for item in spec.filters):
                sql_failures.append("sql_filters")
            if _bag(item.model_dump(mode="json") for item in plan.having) != _bag(item.model_dump(mode="json") for item in (spec.having or [])):
                sql_failures.append("sql_having")
            if plan.aggregations != spec.aggregations:
                sql_failures.append("sql_aggregations")
            if plan.group_by != spec.group_by:
                sql_failures.append("sql_group")
            if plan.order_by != spec.order_by:
                sql_failures.append("sql_order")
            if plan.order_directions != spec.order_directions:
                sql_failures.append("sql_order_direction")
            try:
                validate_generated_sql(generation.sql, {case.target_view}, dialect=dialect)
            except SQLPolicyError:
                sql_failures.append("sql_policy")
            if catalog is not None:
                try:
                    compiled_sql = compile_single_view(plan, catalog,
                        max_rows=max_rows, request=case.request, dialect=dialect)
                    if generation.sql != compiled_sql:
                        sql_failures.append("sql_compiled_structure")
                except SQLPolicyError:
                    sql_failures.append("sql_compile_error")
    sql_status = "pass" if not sql_failures else "fail"
    return mapping_status, sql_status, [*mapping_failures, *sql_failures]
