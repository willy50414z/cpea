"""Reference-only wire contract; Python derives immutable evidence text."""
from typing import Any, Literal

from pydantic import Field

from cpea.application.models.decomposition import PlanningFilter, PlanningModel
from evaluations.three_stage_view_selection import ViewCoverage, validate_coverage

VERSION = 'coverage-references-1'


class ReferencedMapping(PlanningModel):
    column: str = Field(min_length=1)
    role: Literal['metric', 'attribute', 'filter', 'key', 'metadata']
    aggregation: Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max'] | None = None
    operator: str | None = None
    value: Any = None
    conditions: list[PlanningFilter] = Field(default_factory=list)


class ReferencedEntry(PlanningModel):
    requirement_id: str
    status: Literal['supported', 'partial', 'unsupported', 'uncertain']
    mappings: list[ReferencedMapping]
    contract_path: str | None = Field(default=None, description='One JSON pointer to relevant contract text; grain uses /grain/description only. No quote text.')
    missing_requirements: list[str]


class ReferencedViewCoverage(PlanningModel):
    view: str
    entries: list[ReferencedEntry]
    grain: str
    keys: list[str]
    population: str
    contract_path: str = Field(description='One JSON pointer to source population text, such as /summary. No quote text.')


def contract_text(policy, path):
    value = policy
    try:
        if not isinstance(path, str) or not path.startswith('/'):
            raise KeyError(path)
        for part in path[1:].split('/'):
            key = part.replace('~1', '/').replace('~0', '~')
            if isinstance(value, list):
                if not key.isascii() or not key.isdigit() or (len(key) > 1 and key.startswith('0')):
                    raise KeyError(key)
                value = value[int(key)]
            else:
                value = value[key]
    except (KeyError, IndexError, TypeError):
        raise ValueError(f'invalid contract reference path {path}') from None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f'contract reference must point to nonempty text: {path}')
    return value


def materialize_coverage(referenced, recall, request, catalog):
    policy = next((v.policy for v in catalog.views() if v.name == referenced.view), None)
    if policy is None:
        raise ValueError('unadmitted coverage view')
    requirements = {r.requirement_id: r for r in recall.requirements}

    def evidence(path):
        return dict(path=path, quote=contract_text(policy, path))

    entries = []
    for entry in referenced.entries:
        requirement = requirements.get(entry.requirement_id)
        if requirement is None:
            raise ValueError('unknown coverage requirement')
        if requirement.kind == 'grain' and entry.contract_path != '/grain/description':
            raise ValueError('grain reference must be /grain/description only')
        mappings = []
        for mapping in entry.mappings:
            if mapping.column not in policy['columns']:
                raise ValueError('unadmitted mapping column')
            if requirement.kind in ('grain', 'population') and mapping.role != 'key':
                raise ValueError('grain/population mappings must identify keys, not filter the population')
            # A chosen column identifies exactly one description. This is identity
            # evidence, not proof that a join/filter preserves the requested population.
            own_path = '/columns/' + mapping.column.replace('~', '~0').replace('/', '~1') + '/description'
            mappings.append(dict(**mapping.model_dump(), source_quote=requirement.quote,
                                 contract_evidence=[evidence(own_path)]))
        entries.append(dict(requirement_id=entry.requirement_id, status=entry.status, mappings=mappings,
                            contract_evidence=[evidence(entry.contract_path)] if entry.contract_path else [],
                            missing_requirements=entry.missing_requirements))
    result = ViewCoverage.model_validate(dict(view=referenced.view, entries=entries, grain=referenced.grain,
        keys=referenced.keys, population=referenced.population, contract_evidence=[evidence(referenced.contract_path)]))
    return validate_coverage(result, recall, request, catalog)
