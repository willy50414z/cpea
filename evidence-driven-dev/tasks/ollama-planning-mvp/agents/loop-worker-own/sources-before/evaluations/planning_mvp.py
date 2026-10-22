"""Experimental planning compiler and conservative semantic sidecar.

No provider or database imports. Oracles are used only by semantic_check,
never by the compiler, column closure, or the runtime guard.
"""
from __future__ import annotations

from itertools import permutations
from typing import Literal

from pydantic import Field

from cpea.application.models.decomposition import (
    PlanningModel, PlanningFilter, ConditionalMetric, PlanningTask,
    DecompositionDraft, DecompositionResponse, IntegrationPlan, IntegrationEdge, Preparation,
)
from cpea.workflows.task_decomposition.validation import validate_decomposition, prepare_requests
from evaluations.decomposition_grading import _filters


VERSION = 'semantic-mvp-b1'
NULL_POLICY = '保留未匹配母體並標記缺值；無契約保證不得補零。'
EMPTY_POLICY = '保留未匹配母體；未匹配子集合為空集合，不製造零值元素或將數值缺值補零。'


def used_columns(task):
    columns = set(task.group_by + task.output_grain + task.attributes + task.metadata_collections)
    columns.update(task.metrics)
    columns.update(f.column for f in task.filters)
    for metric in task.conditional_metrics:
        columns.add(metric.column)
        columns.update(f.column for f in metric.conditions)
    return columns


def close_columns(draft, catalog):
    """Add only admitted, already typed references; preserve the caller's draft."""
    result = draft.model_copy(deep=True)
    additions = []
    tasks = {t.task_id: t for t in result.tasks}
    references = {t.task_id: used_columns(t) for t in result.tasks}
    if result.integration:
        i = result.integration
        for p in i.preparation:
            if p.task_id not in references:
                raise ValueError('unknown preparation task')
            references[p.task_id].update(p.keys)
        for edge in i.edges:
            for name, keys in ((edge.left_task, edge.left_keys), (edge.right_task, edge.right_keys)):
                if name not in references:
                    raise ValueError('unknown integration task')
                references[name].update(keys)
    for name, columns in references.items():
        t = tasks[name]
        unknown = (columns | set(t.required_columns)) - set(catalog.columns(t.view))
        if unknown:
            raise ValueError(f'{name}: unadmitted columns {sorted(unknown)}')
        missing = sorted(columns - set(t.required_columns))
        t.required_columns.extend(missing)
        additions.extend({'task_id':name, 'column':column, 'evidence':'typed reference'} for column in missing)
    return result, additions


def source_keys(task, catalog):
    # The admitted review document disputes this view's declared uniqueness.
    # Do not use it to prove FD or COUNT == COUNT DISTINCT.
    if task.view == 'demo_retail.v_sales_detail':
        return set()
    v = next((v for v in catalog.views() if v.name == task.view), None)
    grain = v.policy.get('grain', {}) if v else {}
    return set(grain.get('keys', [])) if isinstance(grain, dict) else set()


def singleton(task, catalog, keys=None):
    source = source_keys(task, catalog)
    fixed = {f.column for f in task.filters if f.operator == '='}
    return bool(source) and source - fixed <= set(task.output_grain if keys is None else keys)


def guard_errors(draft, catalog):
    """Typed safety checks only; cannot prove natural-language requirement coverage."""
    errors = []
    for t in draft.tasks:
        if (t.view == 'demo_retail.v_inventory_status' and t.metrics.get('stock_qty') == 'sum'
                and not singleton(t, catalog)
                and 'snapshot_date' not in t.group_by
                and not any(f.column == 'snapshot_date' and f.operator == '=' for f in t.filters)):
            errors.append(f'{t.task_id}: cross-snapshot stock sum')
        if (t.metrics or t.conditional_metrics or t.metadata_collections or t.group_by):
            fixed = {f.column for f in t.filters if f.operator == '='}
            if set(t.attributes) - set(t.group_by) - fixed and not singleton(t, catalog):
                errors.append(f'{t.task_id}: attributes lack uniqueness proof')
        for column, aggregation in t.metrics.items():
            if aggregation == 'sum' and catalog.field_contract(t.view, column).get('unit') == '%':
                errors.append(f'{t.task_id}: nonadditive percentage')
    if draft.integration:
        for e in draft.integration.edges:
            if e.mode == 'inner' and e.preserve_task:
                errors.append('inner cannot guarantee the declared preserved population')
    return errors


def finish(draft, catalog, *, guard=False):
    if draft.status != 'ready':
        return DecompositionResponse(status=draft.status, draft=draft, contract_fingerprint=catalog.fingerprint)
    try:
        errors = validate_decomposition(draft, catalog)
        if not errors and guard:
            errors += guard_errors(draft, catalog)
        payloads = [] if errors else prepare_requests(draft, catalog)
    except (KeyError, ValueError) as exc:
        errors, payloads = [str(exc)], []
    return DecompositionResponse(status='error' if errors else 'ready', code='invalid_plan' if errors else None,
                                 draft=draft, prepared_requests=payloads, validation_errors=errors,
                                 contract_fingerprint=catalog.fingerprint)


class SemanticTask(PlanningModel):
    task_id: str
    view: str
    query_grain: list[str] = Field(min_length=1)
    filters: list[PlanningFilter] = Field(default_factory=list)
    metrics: dict[str, Literal['sum','count','count_distinct','avg','min','max']] = Field(default_factory=dict)
    conditional_metrics: list[ConditionalMetric] = Field(default_factory=list)
    attributes: list[str] = Field(default_factory=list)
    metadata_collections: list[str] = Field(default_factory=list)


class SemanticLink(PlanningModel):
    parent: str
    child: str
    parent_keys: list[str] = Field(min_length=1)
    child_keys: list[str] = Field(min_length=1)
    mode: Literal['left','inner','full']
    shape: Literal['merge','collection','pivot','context']
    cardinality: Literal['one_to_one','one_to_many','many_to_one','many_to_many']


class SemanticPlan(PlanningModel):
    status: Literal['ready','needs_clarification','unsupported','error']
    tasks: list[SemanticTask] = Field(default_factory=list)
    anchor_task: str | None = None
    root_grain: list[str] = Field(default_factory=list)
    links: list[SemanticLink] = Field(default_factory=list)
    missing_values: Literal['preserve_null','empty_collection'] = 'preserve_null'
    clarifications: list[str] = Field(default_factory=list)
    unsupported_reasons: list[str] = Field(default_factory=list)


def compile_plan(plan, catalog):
    if plan.status != 'ready':
        return DecompositionDraft(status=plan.status, clarifications=plan.clarifications,
                                  unsupported_reasons=plan.unsupported_reasons)
    if not plan.tasks or not plan.anchor_task or not plan.root_grain:
        raise ValueError('ready requires explicit population and root grain')
    tasks = []
    for t in plan.tasks:
        aggregate = bool(t.metrics or t.conditional_metrics or t.metadata_collections)
        tasks.append(PlanningTask(task_id=t.task_id, view=t.view, required_columns=list(t.query_grain),
            output_grain=t.query_grain, group_by=t.query_grain if aggregate else [],
            filters=t.filters, metrics=t.metrics, conditional_metrics=t.conditional_metrics,
            attributes=t.attributes, metadata_collections=t.metadata_collections,
            request='依型別條件、欄位角色與查詢粒度準備單一來源資料。'))
    edges, preparations = [], []
    for link in plan.links:
        edges.append(IntegrationEdge(left_task=link.parent, right_task=link.child,
            left_keys=link.parent_keys, right_keys=link.child_keys, mode=link.mode,
            cardinality=link.cardinality, preserve_task=link.parent if link.mode == 'left' else None))
        if link.shape != 'merge':
            kind = {'collection':'nest','pivot':'pivot','context':'attach_context'}[link.shape]
            preparations.append(Preparation(task_id=link.child, kind=kind, keys=link.child_keys,
                description='依模型明示的形狀與對齊鍵準備；保留原查詢粒度及背景值語意。'))
    policy = NULL_POLICY if plan.missing_values == 'preserve_null' else EMPTY_POLICY
    draft = DecompositionDraft(status='ready', strategy='multi_view' if len({t.view for t in tasks}) > 1 else 'single_view',
        tasks=tasks, clarifications=plan.clarifications, unsupported_reasons=plan.unsupported_reasons,
        integration=IntegrationPlan(anchor_task=plan.anchor_task, output_grain=plan.root_grain,
                                   edges=edges, preparation=preparations, missing_data_policy=policy))
    return close_columns(draft, catalog)[0]


def _task_errors(expected, actual, catalog):
    errors = []
    if expected['view'] != actual.view:
        return ['source']
    if _filters(expected.get('filters', [])) != _filters(actual.filters):
        errors.append('conditions/period')
    fixed = {f.column for f in actual.filters if f.operator == '='}
    eg = set(expected['output_grain']) - fixed
    ag = set(actual.output_grain) - fixed
    if eg != ag:
        # Only source-key-proven redundant dimensions are admissible.
        if not (eg <= ag and singleton(actual, catalog, eg)):
            errors.append('query grain')
    unique = singleton(actual, catalog)
    actual_metrics = dict(actual.metrics)
    for col, agg in expected.get('metrics', {}).items():
        got = actual_metrics.get(col)
        equivalent_count = ({agg, got} == {'count','count_distinct'} and bool(source_keys(actual, catalog))
                            and source_keys(actual, catalog) <= set(actual.output_grain) | fixed | {col})
        if not (got == agg or equivalent_count or
                (unique and col in actual.attributes and agg in ('sum','min','max','avg'))):
            errors.append('metric:' + col)
    for col in expected.get('attributes', []):
        if col in fixed or col in actual.output_grain:
            continue
        if col not in actual.attributes and not (unique and
                (col in actual.metadata_collections or actual_metrics.get(col) in ('sum','min','max','avg'))):
            errors.append('output attribute:' + col)
    for col in expected.get('metadata_collections', []):
        if col not in actual.metadata_collections:
            errors.append('date metadata:' + col)
    expected_conditions = expected.get('conditional_metrics', [])
    def condition_key(m):
        m = m.model_dump() if hasattr(m, 'model_dump') else m
        return m['column'], m['aggregation'], frozenset(_filters(m['conditions']))
    if {condition_key(m) for m in expected_conditions} != {condition_key(m) for m in actual.conditional_metrics}:
        errors.append('conditional metrics')
    allowed_measures = set(expected.get('metrics', {})) | set(expected.get('attributes', []))
    if set(actual.metrics) - allowed_measures:
        errors.append('extra metric roles')
    return errors


def semantic_check(case, response, catalog):
    """Strict diagnostic check, not a substitute for the independent review manifest."""
    errors = []
    if response.status != case['expected_status']:
        errors.append('status')
    if case['expected_status'] != 'ready':
        d = response.draft
        if response.prepared_requests or not d or not (d.clarifications or d.unsupported_reasons):
            errors.append('negative response needs explicit reason and no payload')
        return {'safe':not errors, 'errors':errors, 'review_required':True}
    d = response.draft
    if not d:
        return {'safe':False, 'errors':errors + ['missing draft'], 'review_required':True}
    expected = case['expected_tasks']
    if len(d.tasks) != len(expected) or len(d.tasks) > 8:
        return {'safe':False, 'errors':errors + ['task count/equivalence review'], 'review_required':True}
    best = None
    for ordering in permutations(d.tasks):
        details = []
        for e, a in zip(expected, ordering):
            variants = [e, *e.get('acceptable_alternatives', [])]
            details.extend(f'{a.task_id}: {x}' for x in min((_task_errors(v, a, catalog) for v in variants), key=len))
        if best is None or len(details) < len(best[0]):
            best = details, ordering
    details, ordering = best
    errors += details
    try:
        errors += validate_decomposition(d, catalog)
        errors += guard_errors(d, catalog)
    except (KeyError, ValueError) as exc:
        errors.append('contract: ' + str(exc))
    i = d.integration
    oracle = case['expected_integration']
    matched = {e['task_id']:a for e,a in zip(expected, ordering)}
    anchor = matched[oracle['anchor_task']]
    if not i:
        errors.append('integration')
    else:
        if i.anchor_task != anchor.task_id:
            errors.append('anchor population')
        fixed = {f.column for f in anchor.filters if f.operator == '='}
        required_root = set(next(e for e in expected if e['task_id'] == oracle['anchor_task'])['output_grain']) - fixed
        if set(i.output_grain) - fixed != required_root:
            errors.append('root grain')
        if any(e.mode != oracle['mode'] for e in i.edges):
            errors.append('population preservation')
        expected_by_actual = {a.task_id:e for e,a in zip(expected, ordering)}
        if len(i.edges) != len(d.tasks) - 1:
            errors.append('integration topology')
        for edge in i.edges:
            left = expected_by_actual.get(edge.left_task)
            right = expected_by_actual.get(edge.right_task)
            if not left or not right:
                errors.append('unknown integration task')
                continue
            pair_keys = set(left['output_grain']) & set(right['output_grain']) & set(oracle['keys'])
            if not pair_keys or set(edge.left_keys) != pair_keys or set(edge.right_keys) != pair_keys:
                errors.append('semantic integration keys')
        if oracle.get('required_steps'):
            for e in i.edges:
                child = next((t for t in d.tasks if t.task_id == e.right_task), None)
                if not child:
                    continue
                child_fixed = {f.column for f in child.filters if f.operator == '='}
                extra = set(child.output_grain) - child_fixed - set(e.right_keys)
                if extra and not singleton(child, catalog, e.right_keys):
                    if not any(p.task_id == child.task_id and p.kind in ('nest','pivot')
                               and set(p.keys) == set(e.right_keys) for p in i.preparation):
                        errors.append('child collection shape')
        # Free text cannot prove an arbitrary missing-value policy equivalent.
        if i.missing_data_policy not in (IntegrationPlan.model_fields['missing_data_policy'].default, NULL_POLICY, EMPTY_POLICY):
            errors.append('missing policy requires independent review')
    try:
        if [p.model_dump() for p in response.prepared_requests] != [p.model_dump() for p in prepare_requests(d, catalog)]:
            errors.append('payload integrity')
    except (KeyError, ValueError):
        errors.append('payload unavailable')
    return {'safe':not errors, 'errors':list(dict.fromkeys(errors)), 'review_required':True}
