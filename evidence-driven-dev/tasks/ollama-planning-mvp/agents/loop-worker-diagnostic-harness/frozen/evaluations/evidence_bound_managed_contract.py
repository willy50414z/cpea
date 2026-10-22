"""Managed-only evidence references; never infer or repair a planning answer."""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, create_model, model_validator

from cpea.application.models.decomposition import (
    ConditionalMetric, DecompositionDraft, IntegrationEdge, IntegrationPlan,
    PlanningFilter, PlanningModel, PlanningTask, Preparation,
)
from evaluations.indexed_requirement_recall import IndexedRequirement, request_index
from evaluations.referenced_view_coverage import ReferencedMapping, ReferencedViewCoverage, contract_text
from evaluations.referenced_view_coverage import materialize_coverage as materialize_references
from evaluations.slotted_view_coverage import parse_slots
from evaluations.three_stage_view_selection import (
    Assignment, CandidateView, Exclusion, RecallResult, Requirement, SelectionResult,
    finish_selection, validate_recall,
)

VERSION = 'managed-evidence-bound-1'
PROMPTS = Path('evaluations/prompts/evidence_bound')
SOURCES = [Path(__file__), Path('tests/unit/test_evidence_bound_managed_contract.py'),
           Path('tests/unit/test_evidence_bound_managed_runner.py'), *sorted(PROMPTS.glob('*.md'))]
parse_wire = parse_slots


class IndexedBoundRequirement(IndexedRequirement):
    scope_ids: list[str]
    grain_binding: Literal['linked', 'independent', 'unspecified'] | None
    grain_requirement_ids: list[str]


class RecallWire(PlanningModel):
    requirements: list[IndexedBoundRequirement] = Field(min_length=1, max_length=24)


class BoundRequirement(Requirement):
    grain_binding: Literal['linked', 'independent', 'unspecified'] | None
    grain_requirement_ids: list[str]


class BoundRecall(RecallResult):
    requirements: list[BoundRequirement] = Field(min_length=1, max_length=24)


def materialize_recall(wire, request, catalog):
    requirements = []
    for item in wire.requirements:
        if not 0 <= item.start < item.end <= len(request) or not request[item.start:item.end].strip():
            raise ValueError('invalid source span: ' + item.requirement_id)
        requirements.append(BoundRequirement(**item.model_dump(exclude={'start', 'end'}),
                                             quote=request[item.start:item.end]))
    by_id = {r.requirement_id: r for r in requirements}
    for r in requirements:
        refs = r.grain_requirement_ids
        if len(refs) != len(set(refs)) or any(i not in by_id or i == r.requirement_id or by_id[i].kind != 'grain' for i in refs):
            raise ValueError('invalid grain requirement references: ' + r.requirement_id)
        if r.kind == 'metric':
            if r.grain_binding is None or (r.grain_binding == 'linked') != bool(refs):
                raise ValueError('metric grain binding/references differ: ' + r.requirement_id)
        elif r.grain_binding is not None:
            raise ValueError('only metric has grain binding')
    candidates = [CandidateView(view=v.name, reason=json.dumps(dict(
        policy='本MVP保留全部admitted候選', evidence=[dict(path=p, quote=contract_text(v.policy, p))
        for p in ('/summary', '/grain/description')]), ensure_ascii=False)) for v in catalog.views()]
    return validate_recall(BoundRecall(requirements=requirements, candidate_views=candidates), request, catalog)


class Gap(PlanningModel):
    aspect: Literal['mapping', 'grain', 'scope', 'population', 'evidence']
    requirement_ids: list[str] = Field(min_length=1)


class CoverageDecision(PlanningModel):
    status: Literal['supported', 'partial', 'unsupported', 'uncertain']
    mappings: list[ReferencedMapping]
    contract_path: str | None
    gaps: list[Gap]


def coverage_schema(recall):
    ids = [r.requirement_id for r in recall.requirements]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('coverage requires unique IDs')
    suffix = sha256(json.dumps(ids, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
    entries = create_model('BoundSlots_' + suffix, __base__=PlanningModel,
        **{f'slot_{i}': (CoverageDecision, Field(alias=rid)) for i, rid in enumerate(ids)})
    return create_model('BoundCoverage_' + suffix, __base__=PlanningModel, entries=(entries, ...))


def materialize_coverage(wire, recall, request, catalog, policy):
    admitted = next((v.policy for v in catalog.views() if v.name == policy.get('view')), None)
    if admitted is None or policy != admitted:
        raise ValueError('coverage requires exact admitted policy')
    decisions = wire.entries.model_dump(by_alias=True)
    requirements = {r.requirement_id: r for r in recall.requirements}
    if set(decisions) != set(requirements):
        raise ValueError('coverage slots differ from requirements')
    entries = []
    for rid, r in requirements.items():
        decision = decisions[rid]
        status, mappings, gaps = decision['status'], decision['mappings'], decision['gaps']
        if (status == 'supported') != (not gaps):
            raise ValueError('supported must have no gaps; non-supported requires gaps')
        if status == 'partial' and not mappings:
            raise ValueError('partial requires usable mappings')
        if r.kind == 'metric' and status == 'supported':
            if r.grain_binding == 'unspecified':
                raise ValueError('supported metric requires explicit grain binding')
            if r.grain_binding == 'linked' and any(decisions[i]['status'] != 'supported' for i in r.grain_requirement_ids):
                raise ValueError('supported metric requires same-source grain support')
        rendered = []
        seen = set()
        for gap in gaps:
            aspect, refs = gap['aspect'], gap['requirement_ids']
            identity = (aspect, tuple(refs))
            if identity in seen or len(refs) != len(set(refs)) or any(i not in requirements for i in refs):
                raise ValueError('duplicate/unknown gap requirement reference')
            seen.add(identity)
            if aspect == 'scope':
                valid = set(refs) <= set(r.scope_ids) and all(decisions[i]['status'] != 'supported' for i in refs)
            elif aspect == 'grain':
                valid = set(refs) <= set(r.grain_requirement_ids) and all(decisions[i]['status'] != 'supported' for i in refs)
            elif aspect == 'population':
                valid = refs == [rid] and r.kind == 'population'
            elif aspect == 'mapping':
                valid = refs == [rid] and not mappings
            else:
                valid = refs == [rid] and decision['contract_path'] is None
            if not valid:
                raise ValueError('gap aspect contradicts evidence or dependencies: ' + aspect)
            rendered.append(json.dumps(dict(statement='契約未證明以下責任完整可用', aspect=aspect,
                requirements=[dict(requirement_id=i, quote=requirements[i].quote,
                    status=decisions[i]['status']) for i in refs]), ensure_ascii=False))
        entries.append(dict(requirement_id=rid, status=status, mappings=mappings,
                            contract_path=decision['contract_path'], missing_requirements=rendered))
    referenced = ReferencedViewCoverage.model_validate(dict(view=policy['view'], entries=entries,
        grain=contract_text(policy, '/grain/description'), keys=policy['grain']['keys'],
        population=contract_text(policy, '/summary'), contract_path='/summary'))
    return materialize_references(referenced, recall, request, catalog)


# Preserve the original types and constraints while making every wire field required.
def _required(name, base, **annotations):
    from pydantic_core import PydanticUndefined
    fields = {}
    for key, field in base.model_fields.items():
        required = deepcopy(field)
        required.default = PydanticUndefined
        required.default_factory = None
        fields[key] = (annotations.get(key, field.annotation), required)
    return create_model(name, __base__=base, **fields)


RequiredFilter = _required('RequiredFilter', PlanningFilter)
RequiredConditionalMetric = _required('RequiredConditionalMetric', ConditionalMetric, conditions=list[RequiredFilter])
RequiredTask = _required('RequiredTask', PlanningTask, filters=list[RequiredFilter], conditional_metrics=list[RequiredConditionalMetric])
RequiredPreparation = _required('RequiredPreparation', Preparation)
RequiredEdge = _required('RequiredEdge', IntegrationEdge)
RequiredIntegration = _required('RequiredIntegration', IntegrationPlan, edges=list[RequiredEdge], preparation=list[RequiredPreparation])
RequiredDraft = _required('RequiredDraft', DecompositionDraft, tasks=list[RequiredTask], integration=RequiredIntegration | None)


class ReadyDraft(RequiredDraft):
    status: Literal['ready']
    integration: RequiredIntegration


class NonreadyDraft(RequiredDraft):
    status: Literal['needs_clarification', 'unsupported', 'error']

    @model_validator(mode='after')
    def non_executable(self):
        if self.tasks or self.integration is not None or not (self.clarifications or self.unsupported_reasons):
            raise ValueError('nonready draft requires reasons and no executable plan')
        return self


class AssignmentRef(PlanningModel):
    requirement_id: str
    view: str
    task_id: str


class ExclusionRef(PlanningModel):
    kind: Literal['gap', 'redundant']
    requirement_ids: list[str] = Field(min_length=1)
    selected_view: str | None


class ExclusionWire(PlanningModel):
    view: str
    refs: list[ExclusionRef] = Field(min_length=1)


class SelectionWire(PlanningModel):
    selected_views: list[str]
    assignments: list[AssignmentRef]
    exclusions: list[ExclusionWire]
    draft: ReadyDraft | NonreadyDraft = Field(discriminator='status')


def materialize_selection(wire, recall, coverages, request, catalog):
    entries = {(c.view, e.requirement_id): e for c in coverages for e in c.entries}
    requirements = {r.requirement_id: r for r in recall.requirements}
    candidates = {c.view for c in recall.candidate_views}
    assignments = []
    for assignment in wire.assignments:
        entry = entries.get((assignment.view, assignment.requirement_id))
        if entry is None or entry.status != 'supported':
            raise ValueError('assignment lacks supported same-source mapping')
        r = requirements[assignment.requirement_id]
        refs = [assignment.requirement_id, *r.scope_ids, *r.grain_requirement_ids]
        reason = json.dumps(dict(statement='選擇本來源已驗證責任', view=assignment.view,
            task_id=assignment.task_id, evidence=[dict(requirement_id=i,
                **entries[(assignment.view, i)].model_dump(exclude={'requirement_id'})) for i in refs]), ensure_ascii=False)
        assignments.append(Assignment(**assignment.model_dump(), reason=reason))
    exclusions = []
    for exclusion in wire.exclusions:
        if exclusion.view not in candidates or exclusion.view in wire.selected_views:
            raise ValueError('exclusion must identify an unselected candidate')
        reasons = []
        seen = set()
        for ref in exclusion.refs:
            ids = ref.requirement_ids
            identity = (ref.kind, tuple(ids), ref.selected_view)
            if identity in seen or len(ids) != len(set(ids)) or any(i not in requirements for i in ids):
                raise ValueError('invalid exclusion requirement refs')
            seen.add(identity)
            own = [entries[(exclusion.view, i)] for i in ids]
            if ref.kind == 'gap':
                if ref.selected_view is not None or any(e.status == 'supported' for e in own):
                    raise ValueError('exclusion gap must refer to this source non-supported responsibilities')
                reasons.append(dict(kind='gap', view=exclusion.view, evidence=[e.model_dump() for e in own]))
            else:
                if ref.selected_view not in wire.selected_views or any(e.status != 'supported' for e in own):
                    raise ValueError('redundancy requires supported own and selected source')
                other = [entries.get((ref.selected_view, i)) for i in ids]
                if any(e is None or e.status != 'supported' for e in other):
                    raise ValueError('redundancy lacks selected supported evidence')
                def capabilities(entry):
                    return sorted(json.dumps(dict(role=m.role, aggregation=m.aggregation, operator=m.operator,
                        value=m.value, conditions=[dict(operator=c.operator, value=c.value) for c in m.conditions]),
                        sort_keys=True, ensure_ascii=False) for m in entry.mappings)
                if any(capabilities(a) != capabilities(b) for a, b in zip(own, other)):
                    raise ValueError('redundancy source capabilities differ')
                # Same requirement identity is mandatory; never borrow another source's capability.
                if any(any(entries[(ref.selected_view, s)].status != 'supported'
                           for s in [*requirements[i].scope_ids, *requirements[i].grain_requirement_ids]) for i in ids):
                    raise ValueError('redundancy lacks selected dependency evidence')
                reasons.append(dict(kind='redundant', view=exclusion.view, selected_view=ref.selected_view,
                    own=[e.model_dump() for e in own], selected=[e.model_dump() for e in other]))
        exclusions.append(Exclusion(view=exclusion.view, reason=json.dumps(reasons, ensure_ascii=False)))
    result = SelectionResult.model_validate(dict(selected_views=wire.selected_views, assignments=assignments,
        exclusions=exclusions, draft=wire.draft.model_dump()))
    finish_selection(result, recall, coverages, request, catalog)
    return result


def messages(phase, schema, request, **context):
    if phase == 'recall':
        context.update(request_length=len(request), request_characters=request_index(request))
    return [SystemMessage(content=(PROMPTS / (phase + '.md')).read_text(encoding='utf-8')),
        HumanMessage(content=json.dumps(dict(request=request, **context,
            response_schema=schema.model_json_schema()), ensure_ascii=False))]
