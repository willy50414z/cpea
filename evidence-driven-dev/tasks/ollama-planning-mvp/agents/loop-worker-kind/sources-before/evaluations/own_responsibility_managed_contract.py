"""Managed own decisions with complete, deterministic same-view dependency gaps."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, StrictBool, create_model

from cpea.application.models.decomposition import PlanningModel
from evaluations import evidence_bound_managed_contract as previous
from evaluations.evidence_bound_managed_contract import (
    RecallWire, SelectionWire, materialize_recall, materialize_selection, parse_wire,
)
from evaluations.indexed_requirement_recall import request_index
from evaluations.referenced_view_coverage import ReferencedMapping, ReferencedViewCoverage, contract_text
from evaluations.referenced_view_coverage import materialize_coverage as materialize_references

VERSION = 'managed-own-responsibility-1'
PROMPTS = Path('evaluations/prompts/own_responsibility')
SOURCES = [*previous.SOURCES, Path(__file__),
           Path('tests/unit/test_own_responsibility_managed_contract.py'),
           Path('tests/unit/test_own_responsibility_managed_runner.py'), *sorted(PROMPTS.glob('*.md'))]


class CoverageDecision(PlanningModel):
    status: Literal['supported', 'partial', 'unsupported', 'uncertain']
    mappings: list[ReferencedMapping]
    contract_path: str | None
    own_gap: StrictBool


def coverage_schema(recall):
    ids = [r.requirement_id for r in recall.requirements]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('coverage requires unique IDs')
    suffix = sha256(json.dumps(ids, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
    entries = create_model('OwnSlots_' + suffix, __base__=PlanningModel,
        **{f'slot_{i}': (CoverageDecision, Field(alias=rid)) for i, rid in enumerate(ids)})
    return create_model('OwnCoverage_' + suffix, __base__=PlanningModel, entries=(entries, ...))


def materialize_coverage(wire, recall, request, catalog, policy):
    admitted = next((v.policy for v in catalog.views() if v.name == policy.get('view')), None)
    if admitted is None or policy != admitted:
        raise ValueError('coverage requires exact admitted policy')
    decisions = wire.entries.model_dump(by_alias=True)
    requirements = {r.requirement_id: r for r in recall.requirements}
    if set(decisions) != set(requirements):
        raise ValueError('coverage slots differ from requirements')
    entries = []
    for rid, requirement in requirements.items():
        decision = decisions[rid]
        status, mappings, own_gap = decision['status'], decision['mappings'], decision['own_gap']
        scope = [i for i in requirement.scope_ids if decisions[i]['status'] != 'supported']
        grain = [i for i in requirement.grain_requirement_ids if decisions[i]['status'] != 'supported']
        if (not mappings or decision['contract_path'] is None) and not own_gap:
            raise ValueError('absent mappings/evidence requires own_gap')
        if status == 'supported':
            if own_gap:
                raise ValueError('supported contradicts own_gap')
            if scope:
                raise ValueError('supported requires same-source scope support')
            if grain:
                raise ValueError('supported requires same-source grain support')
            if requirement.kind == 'metric' and requirement.grain_binding == 'unspecified':
                raise ValueError('supported metric requires explicit grain binding')
        elif status == 'partial':
            if not mappings or not (own_gap or scope or grain):
                raise ValueError('partial requires usable mappings and an unfinished responsibility')
        elif not own_gap:
            raise ValueError('unsupported/uncertain requires own_gap')
        rendered = []
        for aspect, refs in [('self', [rid] if own_gap else []), ('scope', scope), ('grain', grain)]:
            if refs:
                rendered.append(json.dumps(dict(statement='契約未證明以下責任完整可用', aspect=aspect,
                    requirements=[dict(requirement_id=i, quote=requirements[i].quote,
                                       status=decisions[i]['status']) for i in refs]), ensure_ascii=False))
        entries.append(dict(requirement_id=rid, status=status, mappings=mappings,
                            contract_path=decision['contract_path'], missing_requirements=rendered))
    referenced = ReferencedViewCoverage.model_validate(dict(view=policy['view'], entries=entries,
        grain=contract_text(policy, '/grain/description'), keys=policy['grain']['keys'],
        population=contract_text(policy, '/summary'), contract_path='/summary'))
    return materialize_references(referenced, recall, request, catalog)


def messages(phase, schema, request, **context):
    if phase == 'selection':
        return previous.messages(phase, schema, request, **context)
    if phase == 'recall':
        context.update(request_length=len(request), request_characters=request_index(request))
    return [SystemMessage(content=(PROMPTS / (phase + '.md')).read_text(encoding='utf-8')),
        HumanMessage(content=json.dumps(dict(request=request, **context,
            response_schema=schema.model_json_schema()), ensure_ascii=False))]
