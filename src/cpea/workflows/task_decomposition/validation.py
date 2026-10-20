"""Validate catalog references before constructing dispatchable requests."""
from __future__ import annotations

import json
from cpea.application.models.decomposition import DecompositionDraft, PreparedSQLRequest
from cpea.application.ports.catalog import CatalogProvider


def validate_decomposition(draft: DecompositionDraft, catalog: CatalogProvider) -> list[str]:
    if draft.status != 'ready':
        return []
    errors = []
    tasks = {task.task_id: task for task in draft.tasks}
    if not tasks or len(tasks) != len(draft.tasks):
        errors.append('tasks must be nonempty with unique IDs')
    if draft.clarifications or draft.unsupported_reasons:
        errors.append('ready cannot have unresolved requirements')
    expected = 'multi_view' if len({t.view for t in draft.tasks}) > 1 else 'single_view'
    if draft.strategy != expected:
        errors.append('strategy differs from selected sources')
    views = {view.name: view for view in catalog.views()}
    for task in draft.tasks:
        if task.view not in views:
            errors.append(f'{task.task_id}: unadmitted view')
            continue
        fields = set(task.required_columns)
        if len(fields) != len(task.required_columns) or not fields <= set(catalog.columns(task.view)):
            errors.append(f'{task.task_id}: invalid required columns')
            continue
        if not task.request.strip() or task.unbound_inputs:
            errors.append(f'{task.task_id}: request has unresolved inputs')
        if any(view != task.view and view in task.request for view in views):
            errors.append(f'{task.task_id}: request refers to another view')
        used = set(task.group_by + task.output_grain + task.attributes) | set(task.metrics)
        filters = list(task.filters)
        metrics = list(task.metrics.items())
        for metric in task.conditional_metrics:
            metrics.append((metric.column, metric.aggregation))
            filters.extend(metric.conditions)
        used.update(c for c, _ in metrics)
        used.update(f.column for f in filters)
        if not used <= fields:
            errors.append(f'{task.task_id}: used column absent from required_columns')
            continue
        for column, aggregation in metrics:
            if aggregation not in catalog.field_contract(task.view, column).get('aggregations', []):
                errors.append(f'{task.task_id}: aggregation forbidden for {column}')
        for column in task.group_by:
            if 'group_by' not in catalog.field_contract(task.view,column).get('capabilities', []):
                errors.append(f'{task.task_id}: group_by forbidden for {column}')
        for condition in filters:
            contract = catalog.field_contract(task.view, condition.column)
            if 'filter' not in contract.get('capabilities', []):
                errors.append(f'{task.task_id}: filter forbidden')
            if condition.operator in contract.get('disallowed_operators', []):
                errors.append(f'{task.task_id}: operator forbidden')
            if condition.operator in ('IN','NOT IN') and not isinstance(condition.value,list):
                errors.append(f'{task.task_id}: IN requires a list')
        if metrics and set(task.group_by) != set(task.output_grain):
            errors.append(f'{task.task_id}: aggregate grain differs from group_by')
        if any(dep not in tasks or dep == task.task_id for dep in task.depends_on):
            errors.append(f'{task.task_id}: unknown or self dependency')
    visiting, visited = set(), set()
    def visit(name):
        if name in visiting:
            return False
        if name in visited or name not in tasks:
            return True
        visiting.add(name)
        if not all(visit(dep) for dep in tasks[name].depends_on):
            return False
        visiting.remove(name)
        visited.add(name)
        return True
    if not all(visit(name) for name in tasks):
        errors.append('cyclic dependencies')
    integration = draft.integration
    if integration is None or integration.anchor_task not in tasks:
        return errors + ['integration requires a valid anchor']
    connected = {integration.anchor_task}
    neighbors = {name:set() for name in tasks}
    for prep in integration.preparation:
        if prep.task_id not in tasks or not set(prep.keys) <= set(tasks[prep.task_id].required_columns):
            errors.append('invalid preparation source or keys')
    for edge in integration.edges:
        if edge.left_task not in tasks or edge.right_task not in tasks or edge.left_task == edge.right_task:
            errors.append('invalid integration task')
            continue
        left, right = tasks[edge.left_task], tasks[edge.right_task]
        neighbors[left.task_id].add(right.task_id); neighbors[right.task_id].add(left.task_id)
        if (len(edge.left_keys) != len(edge.right_keys) or len(set(edge.left_keys)) != len(edge.left_keys)
                or len(set(edge.right_keys)) != len(edge.right_keys)):
            errors.append('integration key arity or uniqueness invalid')
        if not set(edge.left_keys) <= set(left.output_grain) or not set(edge.right_keys) <= set(right.output_grain):
            errors.append('integration key absent from output grain')
        for task, keys in ((left,edge.left_keys),(right,edge.right_keys)):
            if not set(keys) <= set(task.required_columns):
                errors.append('integration key absent from required columns')
        if left.view in views and right.view in views:
            for lk,rk in zip(edge.left_keys,edge.right_keys):
                if lk in catalog.columns(left.view) and rk in catalog.columns(right.view):
                    if catalog.field_contract(left.view,lk)['type'] != catalog.field_contract(right.view,rk)['type']:
                        errors.append('integration key type mismatch')
        if edge.mode == 'left' and edge.preserve_task != edge.left_task:
            errors.append('left integration must preserve its left task')
        if edge.preserve_task is not None and edge.preserve_task not in (edge.left_task,edge.right_task):
            errors.append('invalid preserved task')
        for task,keys in ((left,edge.left_keys),(right,edge.right_keys)):
            reduced = set(task.output_grain) - set(keys)
            prepared = any(p.task_id == task.task_id and p.kind in ('nest','pivot','aggregate')
                           and set(p.keys) == set(keys) for p in integration.preparation)
            if reduced and not prepared:
                # A many-to-one edge may legitimately attach store context to product facts.
                if not (task is left and edge.cardinality == 'many_to_one'):
                    errors.append('finer output grain requires an explicit preparation')
    pending = list(connected)
    while pending:
        for name in neighbors[pending.pop()]:
            if name not in connected:
                connected.add(name);pending.append(name)
    if connected != set(tasks):
        errors.append('integration graph is disconnected')
    return errors


def prepare_requests(draft: DecompositionDraft, catalog: CatalogProvider) -> list[PreparedSQLRequest]:
    if draft.status != 'ready':
        return []
    errors = validate_decomposition(draft,catalog)
    if errors:
        raise ValueError('; '.join(errors))
    prepared = []
    for task in draft.tasks:
        body = {'view':task.view,'required_columns':task.required_columns,
                'filters':[f.model_dump() for f in task.filters], 'metrics':task.metrics,
                'conditional_metrics':[m.model_dump() for m in task.conditional_metrics],
                'attributes':task.attributes,'group_by':task.group_by,'output_grain':task.output_grain}
        request = '只執行以下單一 View 資料查詢；保留全部條件及指定輸出粒度，不作跨來源整合或業務決策。\n' + json.dumps(body,ensure_ascii=False)
        if len(request)>4000:
            raise ValueError('prepared request exceeds SQL API length limit')
        prepared.append(PreparedSQLRequest(task_id=task.task_id,view=task.view,
                                           payload={'request':request,'history':[]}))
    return prepared
