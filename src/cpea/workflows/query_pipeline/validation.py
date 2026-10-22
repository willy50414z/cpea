"""Deterministic batch admission and task-to-SQL equivalence checks."""
from __future__ import annotations

from collections import Counter
import json
from math import isfinite

from cpea.application.models.query_pipeline import PipelineIssue
from cpea.infrastructure.sql_compiler import compile_single_view, validate_single_view_plan
from cpea.infrastructure.sql_policy import SQLPolicyError, validate_generated_sql
from cpea.workflows.task_decomposition.validation import render_task_request, validate_decomposition


def issue(stage, code, task_id=None):
    messages = {
        'unsupported_task_capability': '此任務需要 SQL 階段尚未支援的能力。',
        'stale_contract': '來源契約版本已改變。', 'invalid_handoff': '交接資料與核准任務不一致。',
        'handoff_too_long': '交接文字超過 4000 字元。',
        'semantic_drift': 'SQL 計畫與核准任務不一致。', 'sql_mismatch': 'SQL 與重編譯結果不一致。',
        'sql_policy_violation': 'SQL 未通過來源或安全檢查。',
        'provider_error': '模型服務呼叫失敗；未重試。', 'invalid_model_response': '模型回應未通過契約。',
        'invalid_request': '需求須為 1 至 4000 字元的非空白文字。',
        'planning_not_ready': '規劃尚未就緒。',
    }
    return PipelineIssue(stage=stage, code=code, task_id=task_id,
                         message=messages.get(code, '此階段未通過驗證。'))


def task_capability_issues(task, catalog):
    unsupported = bool(task.conditional_metrics or task.metadata_collections or task.depends_on or task.unbound_inputs)
    for condition in task.filters:
        value = condition.value
        values = value if isinstance(value, list) else [value]
        unsupported |= condition.operator not in {'=', '!=', '<>', '>', '>=', '<', '<=', 'IN', 'LIKE'}
        unsupported |= (isinstance(value, list) != (condition.operator == 'IN')) or not values
        unsupported |= any(type(v) not in (str, int, float) or (type(v) is float and not isfinite(v)) for v in values)
        if task.view in {v.name for v in catalog.views()} and condition.column in catalog.columns(task.view):
            unsupported |= catalog.columns(task.view)[condition.column] == 'boolean'
    return [issue('handoff', 'unsupported_task_capability', task.task_id)] if unsupported else []


def preflight_tasks(planning, *, catalog):
    if planning.contract_fingerprint != catalog.fingerprint:
        return [issue('handoff', 'stale_contract')]
    if planning.status != 'ready' or not planning.draft or planning.draft.status != 'ready':
        return [issue('handoff', 'planning_not_ready')]
    tasks = planning.draft.tasks
    capabilities = [i for task in tasks for i in task_capability_issues(task, catalog)]
    if capabilities:
        return capabilities
    if validate_decomposition(planning.draft, catalog):
        return [issue('handoff', 'invalid_handoff')]
    expected = {}
    for task in tasks:
        try:
            expected[task.task_id] = (task.view, {'request': render_task_request(task), 'history': []})
        except ValueError:
            return [issue('handoff', 'handoff_too_long', task.task_id)]
    actual = {p.task_id: (p.view, p.payload) for p in planning.prepared_requests}
    if len(actual) != len(planning.prepared_requests) or actual != expected or planning.validation_errors:
        return [issue('handoff', 'invalid_handoff')]
    return []


def normalized_filters(filters):
    """Only AND ordering, IN set ordering and SQL's !=/<> synonym are equivalent."""
    items = []
    for item in filters:
        item = item.model_dump() if hasattr(item, 'model_dump') else item
        value = item.get('value')
        operator = '<>' if item['operator'] == '!=' else item['operator']
        if operator == 'IN' and isinstance(value, list):
            value = sorted(set(json.dumps(v, ensure_ascii=False, sort_keys=True) for v in value))
        items.append((item['column'], operator, json.dumps(value, ensure_ascii=False, sort_keys=True)))
    return Counter(items)


def validate_task_sql(task_input, generation, *, catalog, settings):
    task = task_input.task
    if task_input.contract_fingerprint != catalog.fingerprint:
        return [issue('handoff', 'stale_contract', task.task_id)]
    unsupported = task_capability_issues(task, catalog)
    if unsupported:
        return unsupported
    if generation.status != 'ready':
        return [issue('sql_validation', 'invalid_model_response', task.task_id)]
    plan = generation.query_plan
    outputs = set(task.attributes + task.output_grain) | set(task.metrics)
    if (not plan or not plan.supported or plan.source_views != [task.view]
            or generation.selected_views != [task.view]
            or set(plan.select_columns) != outputs or len(plan.select_columns) != len(outputs)
            or set(plan.group_by) != set(task.group_by) or len(plan.group_by) != len(set(task.group_by))
            or plan.aggregations != task.metrics or normalized_filters(plan.filters) != normalized_filters(task.filters)
            or plan.having or plan.order_by or plan.order_directions or plan.limit is not None):
        return [issue('sql_validation', 'semantic_drift', task.task_id)]
    try:
        request = render_task_request(task)
        validate_single_view_plan(plan, catalog, max_rows=settings.max_rows, request=request)
        dialect = settings.database_settings.resolved_dialect
        compiled = compile_single_view(plan, catalog, max_rows=settings.max_rows, request=request, dialect=dialect)
        validate_generated_sql(generation.sql, {task.view}, dialect=dialect)
    except (SQLPolicyError, ValueError, TypeError, AssertionError):
        return [issue('sql_validation', 'sql_policy_violation', task.task_id)]
    if generation.sql != compiled:
        return [issue('sql_validation', 'sql_mismatch', task.task_id)]
    return []
