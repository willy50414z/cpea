"""Compile an approved, single-view plan into bounded read-only MSSQL."""

from __future__ import annotations

from cpea.domain.models import QueryPlan
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.sql_policy import SQLPolicyError


def _identifier(value: str) -> str:
    return "[" + value.replace("]", "]]") + "]"


def _literal(value: str | int | float) -> str:
    if isinstance(value, str):
        return "N'" + value.replace("'", "''") + "'"
    return str(value)


def compile_single_view(
    plan: QueryPlan, catalog: CatalogProvider, *, max_rows: int = 200, request: str = ""
) -> str:
    if len(plan.source_views) != 1:
        raise SQLPolicyError("single-view compiler requires exactly one source view")
    if not plan.select_columns:
        raise SQLPolicyError("Query Plan must select at least one column")
    if max_rows < 1:
        raise SQLPolicyError("max_rows must be positive")
    violations = catalog.validate_plan_contract(plan, request)
    if violations:
        raise SQLPolicyError("；".join(violations))
    view = plan.source_views[0]
    selected = set(plan.select_columns)
    grouped = set(plan.group_by)
    aggregate = plan.aggregations
    if grouped:
        unaggregated = selected - grouped - set(aggregate)
        if unaggregated:
            raise SQLPolicyError("grouped query has unaggregated columns: " + ", ".join(sorted(unaggregated)))
    elif aggregate and selected - set(aggregate):
        raise SQLPolicyError("aggregate query cannot mix raw columns without GROUP BY")
    limit = min(plan.limit or max_rows, max_rows)
    rendered = []
    for column in plan.select_columns:
        quoted = _identifier(column)
        if column in aggregate:
            expression = (f"COUNT(DISTINCT {quoted})" if aggregate[column] == "count_distinct"
                          else f"{aggregate[column].upper()}({quoted})")
            rendered.append(f"{expression} AS {quoted}")
        else:
            rendered.append(quoted)
    sql = f"SELECT TOP ({limit}) {', '.join(rendered)} FROM {view}"
    if plan.filters:
        predicates = []
        for item in plan.filters:
            if item.operator == "IN":
                assert isinstance(item.value, list)
                predicates.append(f"{_identifier(item.column)} IN ({', '.join(_literal(value) for value in item.value)})")
            else:
                assert not isinstance(item.value, list)
                predicates.append(f"{_identifier(item.column)} {item.operator} {_literal(item.value)}")
        sql += " WHERE " + " AND ".join(predicates)
    if plan.group_by:
        sql += " GROUP BY " + ", ".join(_identifier(column) for column in plan.group_by)
    if plan.having:
        predicates = []
        for item in plan.having:
            quoted = _identifier(item.column)
            expression = (f"COUNT(DISTINCT {quoted})" if item.aggregation == "count_distinct"
                          else f"{item.aggregation.upper()}({quoted})")
            predicates.append(f"{expression} {item.operator} {_literal(item.value)}")
        sql += " HAVING " + " AND ".join(predicates)
    if plan.order_by:
        sql += " ORDER BY " + ", ".join(
            _identifier(column) + (" DESC" if plan.order_directions.get(column) == "desc" else "")
            for column in plan.order_by)
    return sql
