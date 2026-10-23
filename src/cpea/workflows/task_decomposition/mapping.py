"""Deterministic checks; authentic quotes do not by themselves prove semantics."""
from __future__ import annotations

import json
import unicodedata

from cpea.workflows.task_decomposition.mapping_models import (
    MappedDraft, MappingReview, RequirementExtraction, ViewMapping)
from cpea.workflows.task_decomposition.validation import validate_decomposition

DATA_KINDS = {'concept', 'time', 'value', 'grain'}
CONSTRAINT_KINDS = {'population', 'purpose', 'prohibition'}


def valid_span(request, span):
    return 0 <= span.start < span.end <= len(request) and request[span.start:span.end] == span.text


def validate_extraction(request: str, extraction: RequirementExtraction) -> list[str]:
    errors = []
    ids = {r.id for r in extraction.requirements}
    if len(ids) != len(extraction.requirements):
        errors.append('requirement IDs must be unique')
    covered, business = set(), set()
    for requirement in extraction.requirements:
        if not valid_span(request, requirement.span):
            errors.append(f'{requirement.id}: span differs from original request')
        else:
            positions = set(range(requirement.span.start, requirement.span.end))
            covered.update(positions)
            business.update(positions)
        if (set(requirement.related_ids) - ids or requirement.id in requirement.related_ids
                or len(set(requirement.related_ids)) != len(requirement.related_ids)):
            errors.append(f'{requirement.id}: invalid related requirement IDs')
    for fragment in extraction.syntax:
        if not valid_span(request, fragment.span):
            errors.append('syntax span differs from original request')
            continue
        positions = set(range(fragment.span.start, fragment.span.end))
        if positions & business:
            errors.append('syntax overlaps a business requirement')
        if fragment.kind == 'punctuation' and any(
                not c.isspace() and not unicodedata.category(c).startswith('P') for c in fragment.span.text):
            errors.append('punctuation span contains business text')
        covered.update(positions)
    if any(not char.isspace() and i not in covered for i, char in enumerate(request)):
        errors.append('original request has unclassified text')
    return errors


def validate_evidence(evidence, policy, column):
    errors, column_supported = [], False
    for item in evidence:
        value = policy
        try:
            for part in item.path:
                if isinstance(value, dict) and isinstance(part, str):
                    value = value[part]
                elif isinstance(value, list) and type(part) is int and 0 <= part < len(value):
                    value = value[part]
                else:
                    raise KeyError(part)
        except (KeyError, IndexError):
            value = None
        if not item.quote.strip() or not isinstance(value, str) or item.quote not in value:
            errors.append('evidence quote absent from its exact contract path')
        elif item.path[:2] == ['columns', column]:
            column_supported = True
    if not column_supported:
        errors.append('column requires evidence from its own contract entry')
    return errors


def validate_view_mapping(mapping: ViewMapping, extraction: RequirementExtraction, view) -> list[str]:
    errors = []
    requirements = {r.id: r for r in extraction.requirements}
    ids = [r.requirement_id for r in mapping.results]
    if mapping.view != view.name:
        errors.append('mapping refers to a different view')
    if len(ids) != len(set(ids)) or set(ids) != set(requirements):
        errors.append('every requirement must have exactly one result per view')
    candidate_ids = set()
    for result in mapping.results:
        requirement = requirements.get(result.requirement_id)
        if (result.status == 'matched') != bool(result.candidates):
            errors.append('only matched results may contain candidates')
        if result.status == 'constraint_only' and requirement and requirement.kind not in CONSTRAINT_KINDS:
            errors.append('data requirements cannot be treated as noncolumn constraints')
        if result.candidates and requirement and requirement.kind in CONSTRAINT_KINDS:
            errors.append('purpose, population and prohibition must remain noncolumn constraints')
        for candidate in result.candidates:
            if candidate.id in candidate_ids:
                errors.append('candidate IDs must be unique')
            candidate_ids.add(candidate.id)
            if candidate.column not in view.policy.get('columns', {}):
                errors.append('candidate column absent from admitted view')
                continue
            if len(candidate.operations) != len(set(candidate.operations)):
                errors.append('candidate operations must be unique')
            errors.extend(validate_evidence(candidate.evidence, view.policy, candidate.column))
    return errors


def candidate_index(mappings):
    return {candidate.id: (mapping.view, result.requirement_id, candidate)
            for mapping in mappings for result in mapping.results for candidate in result.candidates}


def approved_uses(mappings, review):
    """Map (view, column, operation) to the requirements admitting that use."""
    candidates, grants = candidate_index(mappings), {}
    for candidate_id in review.selected_candidate_ids:
        if candidate_id not in candidates:
            continue
        view, requirement_id, candidate = candidates[candidate_id]
        for operation in candidate.operations:
            grants.setdefault((view, candidate.column, operation), set()).add(requirement_id)
    for auxiliary in review.auxiliary_columns:
        for operation in auxiliary.operations:
            grants.setdefault((auxiliary.view, auxiliary.column, operation), set()).update(auxiliary.requirement_ids)
    return grants


def validate_review(request: str, extraction: RequirementExtraction, mappings: list[ViewMapping],
                    review: MappingReview, views) -> list[str]:
    errors = []
    requirements = {r.id: r for r in extraction.requirements}
    definitions = {view.name: view for view in views}
    names = [mapping.view for mapping in mappings]
    if len(names) != len(set(names)) or set(names) != set(definitions):
        errors.append('review requires completed comparison of every admitted view')
    candidates = candidate_index(mappings)
    count = sum(len(result.candidates) for m in mappings for result in m.results)
    if count != len(candidates):
        errors.append('candidate IDs must be globally unique')
    selected = review.selected_candidate_ids
    rejected = [r.candidate_id for r in review.rejected_candidates]
    if (len(set(selected)) != len(selected) or len(set(rejected)) != len(rejected)
            or set(selected) & set(rejected) or (set(selected) | set(rejected)) - set(candidates)):
        errors.append('invalid selected or rejected candidate IDs')
    for missing in review.missing_requirements:
        if not valid_span(request, missing):
            errors.append('review omission span differs from original request')
    if review.missing_requirements:
        errors.append('review discovered omitted or misclassified requirements')
    for auxiliary in review.auxiliary_columns:
        view = definitions.get(auxiliary.view)
        if view is None or auxiliary.column not in view.policy.get('columns', {}):
            errors.append('auxiliary column absent from admitted view')
            continue
        if (set(auxiliary.requirement_ids) - set(requirements)
                or any(requirements[r].kind in {'purpose', 'prohibition'}
                       for r in auxiliary.requirement_ids if r in requirements)):
            errors.append('auxiliary column lacks a supporting data or population requirement')
        errors.extend(validate_evidence(auxiliary.evidence, view.policy, auxiliary.column))
    grants = approved_uses(mappings, review)
    decisions = [decision.requirement_id for decision in review.constraints]
    if len(set(decisions)) != len(decisions):
        errors.append('constraint decisions must be unique')
    for decision in review.constraints:
        requirement = requirements.get(decision.requirement_id)
        if requirement is None or requirement.kind != decision.kind:
            errors.append('constraint decision kind differs from original requirement')
        if decision.kind in {'time', 'value'}:
            if not decision.filters or decision.anchor_view or decision.forbidden_uses:
                errors.append('time and value constraints require only reviewed filters')
            for item in decision.filters:
                if decision.requirement_id not in grants.get((item.view, item.condition.column, 'filter'), set()):
                    errors.append('reviewed filter lacks approved evidence for its requirement')
        elif decision.kind == 'population':
            if (not decision.anchor_view or decision.filters or decision.forbidden_uses
                    or not any(view == decision.anchor_view for view, _, _ in grants)):
                errors.append('population requires a selected anchor view')
            if requirement and requirement.related_ids:
                supported = {candidates[cid][0] for cid in selected if cid in candidates
                             and candidates[cid][1] in requirement.related_ids}
                if decision.anchor_view not in supported:
                    errors.append('population anchor lacks evidence for its related requirement')
        elif decision.kind == 'prohibition':
            if decision.filters or decision.anchor_view:
                errors.append('prohibition cannot introduce filters or an anchor')
            for item in decision.forbidden_uses:
                view = definitions.get(item.view)
                if view is None or item.column not in view.policy.get('columns', {}):
                    errors.append('forbidden use references an unadmitted column')
        elif decision.filters or decision.anchor_view or decision.forbidden_uses:
            errors.append('purpose must be retained as context without column operations')
    if review.status != 'ready':
        if not review.reasons or any(not reason.strip() for reason in review.reasons):
            errors.append('non-ready review requires an explanation')
        return errors
    if review.reasons:
        errors.append('ready review cannot contain unresolved reasons')
    if set(selected) | set(rejected) != set(candidates):
        errors.append('ready review must explain every unselected candidate')
    covered = {candidates[cid][1] for cid in selected if cid in candidates}
    for requirement in extraction.requirements:
        if requirement.required and requirement.kind in DATA_KINDS and requirement.id not in covered:
            errors.append(f'{requirement.id}: required data has no selected candidate')
        if (requirement.required and requirement.kind in CONSTRAINT_KINDS | {'time', 'value'}
                and requirement.id not in decisions):
            errors.append(f'{requirement.id}: missing constraint decision')
    anchors = {d.anchor_view for d in review.constraints if d.kind == 'population'}
    if len(anchors) > 1:
        errors.append('population constraints select incompatible anchors')
    return errors


def task_uses(task):
    uses = {(c, 'attribute') for c in task.attributes}
    uses.update((c, 'grain') for c in task.output_grain + task.group_by)
    uses.update((c, 'metadata') for c in task.metadata_collections)
    uses.update((c, 'metric') for c in task.metrics)
    conditions = list(task.filters)
    for metric in task.conditional_metrics:
        uses.add((metric.column, 'metric'))
        conditions.extend(metric.conditions)
    uses.update((condition.column, 'filter') for condition in conditions)
    return uses, conditions


def filter_key(condition):
    return json.dumps(condition.model_dump(), ensure_ascii=False, sort_keys=True)


def validate_condition_scope(decision, requirements, bindings, tasks):
    """A conditional metric's predicates cannot constrain another output."""
    related = {decision.requirement_id, *requirements[decision.requirement_id].related_ids}
    related.update(r.id for r in requirements.values() if decision.requirement_id in r.related_ids)
    expected_by_view = {}
    for item in decision.filters:
        expected_by_view.setdefault(item.view, set()).add(filter_key(item.condition))
    errors = []
    for view, expected in expected_by_view.items():
        applicable = {b.task_id for b in bindings if b.requirement_id in related
                      and b.task_id in tasks and tasks[b.task_id].view == view}
        if not applicable:
            errors.append('reviewed condition has no related task')
        for task_id in applicable:
            task = tasks[task_id]
            global_filters = {filter_key(f) for f in task.filters}
            if expected <= global_filters:
                continue
            columns = {c for b in bindings if b.task_id == task_id and b.requirement_id in related
                       and b.requirement_id != decision.requirement_id for c in b.columns}
            scoped_metrics = [m for m in task.conditional_metrics if m.column in columns]
            unrestricted = (set(task.metrics) | set(task.attributes) | set(task.metadata_collections)) & columns
            if unrestricted or not scoped_metrics:
                errors.append('related output lacks reviewed task-level conditions')
            if any(not expected <= global_filters | {filter_key(f) for f in m.conditions} for m in scoped_metrics):
                errors.append('conditional metric lacks its complete reviewed conditions')
    return errors


def validate_mapped_draft(extraction: RequirementExtraction, mappings: list[ViewMapping],
                          review: MappingReview, mapped: MappedDraft, catalog) -> list[str]:
    draft = mapped.draft
    if draft.status != 'ready':
        return []
    errors = validate_decomposition(draft, catalog)
    requirements = {r.id: r for r in extraction.requirements}
    candidates, grants = candidate_index(mappings), approved_uses(mappings, review)
    tasks = {task.task_id: task for task in draft.tasks}
    uses = {task.task_id: task_uses(task) for task in draft.tasks}
    bound, covered_fields = set(), set()
    for binding in mapped.bindings:
        task, requirement = tasks.get(binding.task_id), requirements.get(binding.requirement_id)
        if task is None or requirement is None or requirement.kind in CONSTRAINT_KINDS:
            errors.append('task binding lacks a valid task or data requirement')
            continue
        if len(binding.columns) != len(set(binding.columns)):
            errors.append('task binding columns must be unique')
        for column in binding.columns:
            operations = [op for col, op in uses[task.task_id][0] if col == column]
            if (column not in task.required_columns or not operations
                    or not any(binding.requirement_id in grants.get((task.view, column, op), set())
                               for op in operations)):
                errors.append('task binding lacks an actual approved column use')
                continue
            bound.add((binding.requirement_id, task.view, column))
            covered_fields.add((binding.task_id, column))
    for task in draft.tasks:
        for column in task.required_columns:
            if (task.task_id, column) not in covered_fields:
                errors.append(f'{task.task_id}: required column lacks a requirement binding')
        for column, operation in uses[task.task_id][0]:
            if (task.view, column, operation) not in grants:
                errors.append(f'{task.task_id}: column operation exceeds reviewed allowlist')
    for candidate_id in review.selected_candidate_ids:
        if candidate_id not in candidates:
            errors.append('selected candidate no longer exists')
            continue
        view, rid, candidate = candidates[candidate_id]
        if (rid, view, candidate.column) not in bound:
            errors.append(f'{rid}: selected candidate is not bound to an actual task column')
    for requirement in extraction.requirements:
        if (requirement.required and requirement.kind in DATA_KINDS
                and not any(rid == requirement.id for rid, _, _ in bound)):
            errors.append(f'{requirement.id}: required data missing from draft bindings')
        if requirement.required and requirement.kind == 'grain' and draft.integration:
            anchor = tasks.get(draft.integration.anchor_task)
            columns = {c for b in mapped.bindings if anchor and b.task_id == anchor.task_id
                       and b.requirement_id == requirement.id for c in b.columns}
            if not columns & set(draft.integration.output_grain):
                errors.append(f'{requirement.id}: required grain missing from final integration output')
    reviewed_filters = {(item.view, filter_key(item.condition))
                        for decision in review.constraints for item in decision.filters}
    for task in draft.tasks:
        if any((task.view, filter_key(f)) not in reviewed_filters for f in uses[task.task_id][1]):
            errors.append(f'{task.task_id}: draft filter differs from reviewed conditions')
    for decision in review.constraints:
        if decision.kind in {'time', 'value'}:
            if decision.requirement_id in requirements:
                errors.extend(validate_condition_scope(decision, requirements, mapped.bindings, tasks))
        elif decision.kind == 'population':
            integration = draft.integration
            anchor = tasks.get(integration.anchor_task) if integration else None
            if anchor is None or anchor.view != decision.anchor_view:
                errors.append('draft anchor differs from reviewed population')
            if integration and any(edge.mode == 'inner' for edge in integration.edges):
                errors.append('inner integration can discard the required population')
        elif decision.kind == 'prohibition':
            for forbidden in decision.forbidden_uses:
                if any(task.view == forbidden.view and any((forbidden.column, operation) in uses[task.task_id][0]
                       for operation in forbidden.operations) for task in draft.tasks):
                    errors.append('draft contains a prohibited column operation')
    return errors
