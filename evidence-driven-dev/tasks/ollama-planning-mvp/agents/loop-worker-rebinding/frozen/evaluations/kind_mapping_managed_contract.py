"""Kind-specific managed mappings; compile only already-verified invariants."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, StrictBool, create_model

from cpea.application.models.decomposition import PlanningModel
from evaluations import own_responsibility_managed_contract as previous
from evaluations.evidence_bound_managed_contract import RequiredFilter
from evaluations.own_responsibility_managed_contract import (
    RecallWire, SelectionWire, materialize_recall, materialize_selection, parse_wire,
)

VERSION = 'managed-kind-mapping-1'
PROMPTS = Path('evaluations/prompts/kind_mapping')
SOURCES = [*previous.SOURCES, Path(__file__),
           Path('tests/unit/test_kind_mapping_managed_contract.py'),
           Path('tests/unit/test_kind_mapping_managed_runner.py'), *sorted(PROMPTS.glob('*.md'))]


class ColumnMapping(PlanningModel):
    column: str = Field(min_length=1)


class MetricMapping(ColumnMapping):
    aggregation: Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max']
    conditions: list[RequiredFilter]


class OwnDecision(PlanningModel):
    status: Literal['supported', 'partial', 'unsupported', 'uncertain']
    own_gap: StrictBool


def coverage_schema(recall):
    identities = [(r.requirement_id, r.kind) for r in recall.requirements]
    ids = [rid for rid, _ in identities]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('coverage requires unique IDs')
    suffix = sha256(json.dumps(identities, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
    fields = {}
    for i, (rid, kind) in enumerate(identities):
        mapping = MetricMapping if kind == 'metric' else RequiredFilter if kind == 'filter' else ColumnMapping
        decision_fields = dict(mappings=(list[mapping], ...))
        if kind != 'grain':
            decision_fields['contract_path'] = (str | None, ...)
        decision = create_model('KindDecision_' + kind + '_' + suffix,
                                __base__=OwnDecision, **decision_fields)
        fields[f'slot_{i}'] = (decision, Field(alias=rid))
    entries = create_model('KindSlots_' + suffix, __base__=PlanningModel, **fields)
    return create_model('KindCoverage_' + suffix, __base__=PlanningModel, entries=(entries, ...))


def compile_coverage(wire, recall):
    # Revalidate against these IDs AND kinds, even when called outside the runner.
    decisions = coverage_schema(recall).model_validate(wire.model_dump(by_alias=True)).entries.model_dump(by_alias=True)
    for r in recall.requirements:
        decision = decisions[r.requirement_id]
        if r.kind == 'grain':
            decision['contract_path'] = '/grain/description'
        role = 'key' if r.kind in ('grain', 'population') else r.kind
        decision['mappings'] = [dict(column=m['column'], role=role,
            aggregation=m['aggregation'] if r.kind == 'metric' else None,
            operator=m['operator'] if r.kind == 'filter' else None,
            value=m['value'] if r.kind == 'filter' else None,
            conditions=m['conditions'] if r.kind == 'metric' else []) for m in decision['mappings']]
    return previous.coverage_schema(recall).model_validate(dict(entries=decisions))


def materialize_coverage(wire, recall, request, catalog, policy):
    return previous.materialize_coverage(compile_coverage(wire, recall), recall, request, catalog, policy)


def messages(phase, schema, request, **context):
    if phase != 'coverage':
        return previous.messages(phase, schema, request, **context)
    return [SystemMessage(content=(PROMPTS / 'coverage.md').read_text(encoding='utf-8')),
        HumanMessage(content=json.dumps(dict(request=request, **context,
            response_schema=schema.model_json_schema()), ensure_ascii=False))]
