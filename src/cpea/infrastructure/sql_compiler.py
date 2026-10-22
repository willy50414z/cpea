"""Compile an approved single-view plan for SQL Server or PostgreSQL."""

from __future__ import annotations

from cpea.domain.models import QueryPlan
from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.sql_policy import SQLPolicyError


def _identifier(value: str, dialect: str = 'mssql') -> str:
    if dialect == 'postgresql':
        return '"' + value.replace('"', '""') + '"'
    return "[" + value.replace("]", "]]") + "]"


def _literal(value: str | int | float, dialect: str = 'mssql', *, boolean: bool = False) -> str:
    if dialect == 'postgresql' and boolean:
        normalized = str(value).lower()
        if normalized in {'true', '1'}:
            return 'TRUE'
        if normalized in {'false', '0'}:
            return 'FALSE'
        raise SQLPolicyError('boolean filters require true, false, 1, or 0')
    if isinstance(value, str):
        return ("N'" if dialect == 'mssql' else "'") + value.replace("'", "''") + "'"
    return str(value)


def validate_single_view_plan(
    plan: QueryPlan, catalog: CatalogProvider, *, max_rows: int = 200, request: str = ""
) -> None:
    """Validate a draft without producing SQL before human confirmation."""
    if len(plan.source_views) != 1:
        raise SQLPolicyError("single-view compiler requires exactly one source view")
    if not plan.select_columns:
        raise SQLPolicyError("Query Plan must select at least one column")
    if max_rows < 1:
        raise SQLPolicyError("max_rows must be positive")
    violations = catalog.validate_plan_contract(plan, request)
    if violations:
        raise SQLPolicyError("；".join(violations))
    selected = set(plan.select_columns)
    grouped = set(plan.group_by)
    aggregate = plan.aggregations
    if grouped:
        unaggregated = selected - grouped - set(aggregate)
        if unaggregated:
            raise SQLPolicyError("grouped query has unaggregated columns: " + ", ".join(sorted(unaggregated)))
    elif aggregate and selected - set(aggregate):
        raise SQLPolicyError("aggregate query cannot mix raw columns without GROUP BY")


def compile_single_view(
    plan: QueryPlan, catalog: CatalogProvider, *, max_rows: int = 200, request: str = "", dialect: str = 'mssql'
) -> str:
    if dialect not in {'mssql', 'postgresql'}:
        raise SQLPolicyError('unsupported SQL dialect')
    validate_single_view_plan(plan, catalog, max_rows=max_rows, request=request)
    view = plan.source_views[0]
    if dialect == 'postgresql':
        view = '.'.join(_identifier(part, dialect) for part in view.split('.'))
    aggregate = plan.aggregations
    limit = min(plan.limit or max_rows, max_rows)
    rendered = []
    for column in plan.select_columns:
        quoted = _identifier(column, dialect)
        if column in aggregate:
            expression = (f"COUNT(DISTINCT {quoted})" if aggregate[column] == "count_distinct"
                          else f"{aggregate[column].upper()}({quoted})")
            rendered.append(f"{expression} AS {quoted}")
        else:
            rendered.append(quoted)
    prefix = f'SELECT TOP ({limit})' if dialect == 'mssql' else 'SELECT'
    sql = f"{prefix} {', '.join(rendered)} FROM {view}"
    if plan.filters:
        predicates = []
        for item in plan.filters:
            boolean = catalog.columns(plan.source_views[0])[item.column] == 'boolean'
            if item.operator == "IN":
                assert isinstance(item.value, list)
                predicates.append(f"{_identifier(item.column, dialect)} IN ({', '.join(_literal(value, dialect, boolean=boolean) for value in item.value)})")
            else:
                assert not isinstance(item.value, list)
                predicates.append(f"{_identifier(item.column, dialect)} {item.operator} {_literal(item.value, dialect, boolean=boolean)}")
        sql += " WHERE " + " AND ".join(predicates)
    if plan.group_by:
        sql += " GROUP BY " + ", ".join(_identifier(column, dialect) for column in plan.group_by)
    if plan.having:
        predicates = []
        for item in plan.having:
            quoted = _identifier(item.column, dialect)
            expression = (f"COUNT(DISTINCT {quoted})" if item.aggregation == "count_distinct"
                          else f"{item.aggregation.upper()}({quoted})")
            predicates.append(f"{expression} {item.operator} {_literal(item.value, dialect)}")
        sql += " HAVING " + " AND ".join(predicates)
    if plan.order_by:
        sql += " ORDER BY " + ", ".join(
            _identifier(column, dialect) + (" DESC" if plan.order_directions.get(column) == "desc" else "")
            for column in plan.order_by)
    if dialect == 'postgresql':
        sql += f' LIMIT {limit}'
    return sql
