"""Managed-only fixed requirement slots; immutable source facts come from policy."""
from hashlib import sha256
import json
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import Field, create_model

from cpea.application.models.decomposition import PlanningModel
from evaluations.referenced_view_coverage import (
    ReferencedMapping, ReferencedViewCoverage, contract_text, materialize_coverage,
)

VERSION = 'coverage-slots-1'
PROMPT = Path('evaluations/prompts/coverage_slots.md')
SLOT_SOURCES = [Path(__file__), PROMPT, Path('tests/unit/test_slotted_view_coverage.py')]


class SlotDecision(PlanningModel):
    status: Literal['supported', 'partial', 'unsupported', 'uncertain']
    mappings: list[ReferencedMapping]
    contract_path: str | None = None
    missing_requirements: list[str]


def coverage_schema(recall):
    """Use aliases so arbitrary external IDs never become Python attribute names."""
    ids = [r.requirement_id for r in recall.requirements]
    if not ids or any(not i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError('slots require nonempty unique requirement IDs')
    suffix = sha256(json.dumps(ids, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
    entries = create_model('RequirementSlots_' + suffix, __base__=PlanningModel,
        **{f'slot_{i}': (SlotDecision, Field(alias=identifier)) for i, identifier in enumerate(ids)})
    return create_model('SlottedViewCoverage_' + suffix, __base__=PlanningModel, entries=(entries, ...))


def parse_slots(raw, schema):
    """Reject duplicate keys at every level before Pydantic can lose information."""
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result

    def invalid_constant(value):
        raise ValueError('invalid JSON constant: ' + value)

    value = json.loads(raw.content, object_pairs_hook=unique_object, parse_constant=invalid_constant)
    return schema.model_validate(value)


def materialize_slots(slotted, recall, request, catalog, policy):
    """Restore only known identity/source fields, then reuse every strict guard."""
    admitted = next((v.policy for v in catalog.views() if v.name == policy.get('view')), None)
    if admitted is None or policy != admitted:
        raise ValueError('slots require the exact admitted source policy')
    decisions = slotted.entries.model_dump(by_alias=True)
    ids = [r.requirement_id for r in recall.requirements]
    if len(ids) != len(set(ids)) or set(decisions) != set(ids):
        raise ValueError('slots must exactly match recall requirement IDs')
    referenced = ReferencedViewCoverage.model_validate(dict(
        view=policy['view'], entries=[dict(requirement_id=i, **decisions[i]) for i in ids],
        grain=contract_text(policy, '/grain/description'), keys=policy['grain']['keys'],
        population=contract_text(policy, '/summary'), contract_path='/summary'))
    return materialize_coverage(referenced, recall, request, catalog)


def slot_messages(schema, request, **context):
    return [SystemMessage(content=PROMPT.read_text(encoding='utf-8')),
        HumanMessage(content=json.dumps(dict(request=request, **context,
            response_schema=schema.model_json_schema()), ensure_ascii=False))]
