"""Evaluation-only, evidence-bound partial coverage. No provider/SQL/DB calls."""
from __future__ import annotations

from typing import Any, Literal
from pydantic import Field

from cpea.application.models.decomposition import DecompositionDraft, PlanningModel, PlanningFilter
from cpea.workflows.task_decomposition.validation import _valid_value
from evaluations.planning_mvp import finish, NULL_POLICY, EMPTY_POLICY

VERSION = 'three-stage-view-selection-1.1'
MISSING_POLICIES = [
    '保留未匹配資料並標記缺值；契約沒有保證時不可把缺值當成零。', NULL_POLICY, EMPTY_POLICY,
]


class Requirement(PlanningModel):
    requirement_id: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    business_object: str = Field(min_length=1)
    kind: Literal['metric', 'attribute', 'filter', 'key', 'metadata', 'grain', 'population']
    scope_ids: list[str] = Field(default_factory=list, description='Filter requirement IDs applying to this requirement, on the SAME source/task.')
    grain: str = Field(min_length=1)
    population: str = Field(min_length=1)


class CandidateView(PlanningModel):
    view: str
    reason: str = Field(min_length=1)


class RecallResult(PlanningModel):
    requirements: list[Requirement] = Field(min_length=1, max_length=24)
    candidate_views: list[CandidateView] = Field(min_length=1)


class ContractEvidence(PlanningModel):
    path: str = Field(min_length=1, description='JSON pointer relative to this View policy, e.g. /columns/field/description.')
    quote: str = Field(min_length=1, description='Exact, nonempty substring of the string at path.')


class FieldMapping(PlanningModel):
    column: str
    role: Literal['metric', 'attribute', 'filter', 'key', 'metadata']
    source_quote: str = Field(min_length=1)
    aggregation: Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max'] | None = None
    operator: str | None = None
    value: Any = None
    conditions: list[PlanningFilter] = Field(default_factory=list)
    contract_evidence: list[ContractEvidence] = Field(min_length=1)


class RequirementCoverage(PlanningModel):
    requirement_id: str
    status: Literal['supported', 'partial', 'unsupported', 'uncertain']
    mappings: list[FieldMapping]
    contract_evidence: list[ContractEvidence]
    missing_requirements: list[str]


class ViewCoverage(PlanningModel):
    view: str
    entries: list[RequirementCoverage]
    grain: str = Field(min_length=1, description='Exact contract grain.description.')
    keys: list[str] = Field(description='Exact declared grain.keys, not the desired output keys.')
    population: str = Field(min_length=1)
    contract_evidence: list[ContractEvidence] = Field(min_length=1)


class Assignment(PlanningModel):
    requirement_id: str
    view: str
    task_id: str
    reason: str = Field(min_length=1)


class Exclusion(PlanningModel):
    view: str
    reason: str = Field(min_length=1)


class SelectionResult(PlanningModel):
    selected_views: list[str]
    assignments: list[Assignment]
    exclusions: list[Exclusion]
    draft: DecompositionDraft


def _unique(items, label):
    if len(items) != len(set(items)):
        raise ValueError(f'duplicate {label}')


def validate_recall(recall, request, catalog):
    ids = [r.requirement_id for r in recall.requirements]
    _unique(ids, 'requirement IDs')
    views = [v.view for v in recall.candidate_views]
    _unique(views, 'candidate views')
    if set(views) != {v.name for v in catalog.views()}:
        raise ValueError('MVP requires all admitted candidate views')
    by_id = {r.requirement_id: r for r in recall.requirements}
    for r in recall.requirements:
        if not r.quote.strip() or r.quote not in request:
            raise ValueError(f'{r.requirement_id}: request quote does not exist')
        _unique(r.scope_ids, 'scope IDs')
        if any(s not in by_id or s == r.requirement_id or by_id[s].kind != 'filter' for s in r.scope_ids):
            raise ValueError(f'{r.requirement_id}: invalid scope requirement')
    return recall


def _policy(catalog, view):
    policy = next((v.policy for v in catalog.views() if v.name == view), None)
    if policy is None:
        raise ValueError('unadmitted coverage view')
    return policy


def _evidence(evidence, policy):
    for e in evidence:
        value = policy
        try:
            if not e.path.startswith('/'):
                raise KeyError(e.path)
            for part in e.path[1:].split('/'):
                key = part.replace('~1', '/').replace('~0', '~')
                if isinstance(value, list):
                    if not key.isascii() or not key.isdigit() or (len(key) > 1 and key.startswith('0')):
                        raise KeyError(key)
                    value = value[int(key)]
                else:
                    value = value[key]
        except (KeyError, IndexError, TypeError):
            raise ValueError(f'invalid contract evidence path {e.path}') from None
        if not isinstance(value, str) or not e.quote.strip() or e.quote not in value:
            raise ValueError(f'invalid contract evidence quote {e.path}')


def _filter_valid(mapping, catalog, view):
    contract = catalog.field_contract(view, mapping.column)
    allowed = {'=', '!=', '<>', '>', '>=', '<', '<=', 'IN', 'NOT IN', 'LIKE', 'IS NULL', 'IS NOT NULL'}
    if (mapping.operator not in allowed or 'filter' not in contract.get('capabilities', [])
            or mapping.operator in contract.get('disallowed_operators', [])):
        raise ValueError('forbidden mapping operator/capability')
    if mapping.operator in ('IN', 'NOT IN') and not isinstance(mapping.value, list):
        raise ValueError('IN mapping requires list')
    if mapping.operator == 'LIKE' and contract['type'] != 'string':
        raise ValueError('LIKE mapping requires string')
    if contract['type'] == 'boolean' and mapping.operator not in ('=', '!=', '<>', 'IN', 'NOT IN', 'IS NULL', 'IS NOT NULL'):
        raise ValueError('boolean mapping operator forbidden')
    if mapping.operator not in ('IS NULL', 'IS NOT NULL'):
        values = mapping.value if isinstance(mapping.value, list) else [mapping.value]
        if not values or any(not _valid_value(v, contract['type']) for v in values):
            raise ValueError('invalid mapping filter value')


def validate_coverage(coverage, recall, request, catalog):
    validate_recall(recall, request, catalog)
    policy = _policy(catalog, coverage.view)
    requirements = {r.requirement_id: r for r in recall.requirements}
    ids = [e.requirement_id for e in coverage.entries]
    _unique(ids, 'coverage requirement IDs')
    if set(ids) != set(requirements):
        raise ValueError('every requirement requires a coverage record')
    if coverage.grain != policy['grain']['description'] or coverage.keys != (policy['grain']['keys'] or []):
        raise ValueError('coverage grain/keys differ from contract')
    _evidence(coverage.contract_evidence, policy)
    entries = {e.requirement_id: e for e in coverage.entries}
    for entry in coverage.entries:
        r = requirements[entry.requirement_id]
        _evidence(entry.contract_evidence, policy)
        if entry.status == 'supported':
            if entry.missing_requirements or not entry.mappings or not entry.contract_evidence:
                raise ValueError('supported requires mappings/evidence and no missing requirements')
            if any(entries[s].status != 'supported' for s in r.scope_ids):
                raise ValueError('supported metric requires same-source scope support')
        elif not entry.missing_requirements:
            raise ValueError('non-supported must state missing requirements')
        if entry.status in ('unsupported', 'uncertain') and entry.mappings:
            raise ValueError('unsupported/uncertain cannot expose usable mappings')
        for m in entry.mappings:
            if m.column not in policy['columns']:
                raise ValueError('unadmitted mapping column')
            if m.source_quote not in request or m.source_quote not in r.quote:
                raise ValueError('mapping quote must belong to its requirement quote')
            _evidence(m.contract_evidence, policy)
            if not any(e.path == f'/columns/{m.column}/description' for e in m.contract_evidence):
                raise ValueError('mapping evidence must cite its own column description')
            if r.kind not in ('grain', 'population') and m.role != r.kind:
                raise ValueError('mapping role differs from requirement')
            contract = catalog.field_contract(coverage.view, m.column)
            if m.role == 'metric':
                if m.aggregation not in contract.get('aggregations', []) or m.operator is not None or m.value is not None:
                    raise ValueError('forbidden mapping aggregation or metric filter fields')
                for condition in m.conditions:
                    if condition.column not in policy['columns']:
                        raise ValueError('unadmitted conditional metric field')
                    _filter_valid(condition, catalog, coverage.view)
                    # Conditions also need their own independently verified filter mapping.
                    if not any(c.role == 'filter' and c.column == condition.column and c.operator == condition.operator
                               and c.value == condition.value for e in coverage.entries for c in e.mappings):
                        raise ValueError('conditional metric lacks verified condition evidence')
            elif m.aggregation is not None or m.conditions:
                raise ValueError('only metric mapping may aggregate')
            if m.role == 'filter':
                _filter_valid(m, catalog, coverage.view)
            elif m.operator is not None or m.value is not None:
                raise ValueError('only filter mapping may carry filter fields')
            if m.role in ('attribute', 'key', 'metadata') and 'select' not in contract.get('capabilities', []):
                raise ValueError('forbidden output mapping')
    return coverage


def _filter_tuple(f):
    import json
    return (f.column, f.operator, json.dumps(f.value, ensure_ascii=False, sort_keys=True))


def _mapping_in_task(m, task):
    if m.role == 'filter':
        return _filter_tuple(m) in {_filter_tuple(f) for f in task.filters}
    if m.role == 'metric':
        if m.conditions:
            return any(c.column == m.column and c.aggregation == m.aggregation
                       and {_filter_tuple(f) for f in c.conditions} == {_filter_tuple(f) for f in m.conditions}
                       for c in task.conditional_metrics)
        return task.metrics.get(m.column) == m.aggregation
    if m.role == 'key':
        return m.column in task.output_grain or any(f.column == m.column and f.operator == '=' for f in task.filters)
    if m.role == 'metadata':
        return m.column in task.metadata_collections
    return m.column in task.attributes


def finish_selection(selection, recall, coverages, request, catalog):
    validate_recall(recall, request, catalog)
    _unique([v.view for v in coverages], 'coverage views')
    if {v.view for v in coverages} != {v.view for v in recall.candidate_views}:
        raise ValueError('missing candidate coverage')
    for coverage in coverages:
        validate_coverage(coverage, recall, request, catalog)
    if selection.draft.status != 'ready':
        if selection.draft.tasks or selection.assignments or selection.selected_views:
            raise ValueError('non-ready selection cannot contain executable assignments')
        return finish(selection.draft, catalog, guard=True)
    _unique(selection.selected_views, 'selected views')
    _unique([a.requirement_id for a in selection.assignments], 'assignments')
    requirements = {r.requirement_id: r for r in recall.requirements}
    if {a.requirement_id for a in selection.assignments} != set(requirements):
        raise ValueError('selection omitted requirements')
    tasks = {t.task_id: t for t in selection.draft.tasks}
    if len(tasks) != len(selection.draft.tasks):
        raise ValueError('duplicate task IDs')
    selected = set(selection.selected_views)
    if selected != {t.view for t in tasks.values()} or selected != {a.view for a in selection.assignments}:
        raise ValueError('selected views/tasks/assignments differ')
    excluded = [v.view for v in selection.exclusions]
    _unique(excluded, 'exclusions')
    if selected & set(excluded) or selected | set(excluded) != {v.view for v in recall.candidate_views}:
        raise ValueError('every candidate must be selected or excluded')
    entries = {(v.view, e.requirement_id): e for v in coverages for e in v.entries}
    for a in selection.assignments:
        entry = entries.get((a.view, a.requirement_id))
        task = tasks.get(a.task_id)
        if not entry or entry.status != 'supported' or not task or task.view != a.view:
            raise ValueError('assignment lacks supported same-source mapping')
        required = [entry, *(entries[(a.view, s)] for s in requirements[a.requirement_id].scope_ids)]
        if any(e.status != 'supported' or any(not _mapping_in_task(m, task) for m in e.mappings) for e in required):
            raise ValueError('task omitted verified requirement/scope mapping')
        if requirements[a.requirement_id].kind == 'population':
            integration = selection.draft.integration
            if not integration or integration.anchor_task != a.task_id:
                raise ValueError('preserved population must be the anchor')
            if any(e.mode != 'left' or e.preserve_task != a.task_id or e.left_task != a.task_id for e in integration.edges):
                raise ValueError('integration cannot preserve required anchor population')
        if requirements[a.requirement_id].kind == 'grain':
            integration = selection.draft.integration
            keys = {m.column for m in entry.mappings if m.role == 'key'}
            if not integration or a.task_id != integration.anchor_task or set(integration.output_grain) != keys:
                raise ValueError('final grain differs from verified requirement keys')
    integration = selection.draft.integration
    if not integration or integration.missing_data_policy not in MISSING_POLICIES:
        raise ValueError('missing-data policy must use an admitted no-zero policy')
    for preparation in integration.preparation:
        allowed_keys = [integration.output_grain] if preparation.task_id == integration.anchor_task else []
        allowed_keys += [keys for e in integration.edges for task_id, keys in
                         [(e.left_task, e.left_keys), (e.right_task, e.right_keys)] if task_id == preparation.task_id]
        if not allowed_keys or any(set(preparation.keys) != set(keys) for keys in allowed_keys):
            raise ValueError('preparation cannot erase verified alignment/final grain keys')
    for task in tasks.values():
        assigned = [entries[(a.view, a.requirement_id)] for a in selection.assignments if a.task_id == task.task_id]
        scopes = [entries[(a.view, s)] for a in selection.assignments if a.task_id == task.task_id
                  for s in requirements[a.requirement_id].scope_ids]
        mappings = [m for e in assigned + scopes for m in e.mappings]
        # Child alignment keys may reuse validated grain mappings even when
        # the final grain requirement is owned by the anchor task.
        mappings += [m for (view, _), e in entries.items() if view == task.view and e.status == 'supported'
                     for m in e.mappings if m.role == 'key']
        if not set(task.required_columns) <= {m.column for m in mappings}:
            raise ValueError('stage three introduced unverified task columns')
        if any(not any(m.role == 'filter' and _filter_tuple(m) == _filter_tuple(f) for m in mappings) for f in task.filters):
            raise ValueError('stage three introduced unverified filters')
        if any(not any(m.role == 'metric' and not m.conditions and m.column == c and m.aggregation == agg for m in mappings)
               for c, agg in task.metrics.items()):
            raise ValueError('stage three introduced unverified metrics')
        for field, role in [('attributes', 'attribute'), ('metadata_collections', 'metadata'), ('output_grain', 'key'), ('group_by', 'key')]:
            if not set(getattr(task, field)) <= {m.column for m in mappings if m.role == role}:
                raise ValueError('stage three introduced unverified output roles')
        for metric in task.conditional_metrics:
            if not any(m.role == 'metric' and m.column == metric.column and m.aggregation == metric.aggregation
                       and {_filter_tuple(f) for f in m.conditions} == {_filter_tuple(f) for f in metric.conditions} for m in mappings):
                raise ValueError('stage three introduced unverified conditional metric')
    response = finish(selection.draft, catalog, guard=True)
    if response.status != 'ready':
        raise ValueError('draft validation: ' + '; '.join(response.validation_errors))
    return response
