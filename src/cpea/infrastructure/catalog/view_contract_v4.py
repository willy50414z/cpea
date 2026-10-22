"""Validated semantic metadata for existing SQL views; never executable SQL."""
from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic.json_schema import SkipJsonSchema

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Name = Annotated[str, StringConstraints(min_length=1, pattern=r'^\S(?:[\s\S]*\S)?$')]
QualifiedName = Annotated[str, StringConstraints(pattern=r'^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*){1,2}$')]
ColumnNames = Annotated[list[Name], Field(min_length=1)]
Aggregation = Literal['sum', 'count', 'count_distinct', 'avg', 'min', 'max']
Operator = Literal['=', '!=', '<>', '>', '>=', '<', '<=', 'IN', 'LIKE']
Capability = Literal['select', 'filter', 'group_by', 'order_by']


class ContractModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Grain(ContractModel):
    description: Text
    keys: ColumnNames | None


class Source(ContractModel):
    verification: Literal['metadata_verified', 'unknown']
    relations: Annotated[list[QualifiedName], Field(min_length=1)] | None
    definition_sha256: Annotated[str, StringConstraints(pattern=r'^[0-9a-f]{64}$')] | None

    @model_validator(mode='after')
    def verified_requires_evidence(self):
        if self.verification == 'metadata_verified' and (not self.relations or not self.definition_sha256):
            raise ValueError('metadata_verified source requires relations and definition_sha256')
        return self


class Scope(ContractModel):
    population: Text
    included: list[Text]
    excluded: list[Text]
    row_coverage: Text


class TimeRule(ContractModel):
    columns: ColumnNames
    description: Text


class Time(ContractModel):
    kind: Literal['event', 'aggregate', 'snapshot', 'cumulative', 'mixed', 'unknown']
    dimensions: dict[Name, Text]
    coverage: Text | None
    rules: list[TimeRule]


class UnsupportedUse(ContractModel):
    question: Text
    reason: Text


class Usage(ContractModel):
    supported: list[Text]
    unsupported: list[UnsupportedUse]


class Column(ContractModel):
    type: Literal['string', 'number', 'date', 'boolean']
    role: Literal['identifier', 'dimension', 'measure']
    description: Text
    unit: Text | SkipJsonSchema[None] = None
    entity: Text | SkipJsonSchema[None] = None
    disallowed_aggregations: list[Aggregation] = Field(default_factory=list)
    disallowed_operators: list[Operator] = Field(default_factory=list)
    disallowed_capabilities: list[Capability] = Field(default_factory=list)

    @model_validator(mode='after')
    def optional_text_is_not_null(self):
        for field in ('unit', 'entity'):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'{field} must be a nonempty string when present')
        return self


class Metric(ContractModel):
    description: Text
    columns: ColumnNames
    calculation: Text
    aggregation_notes: Text


class ViewContractV4(ContractModel):
    version: Literal[4]
    view: QualifiedName
    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, pattern=r'^[^\r\n]+$')]
    grain: Grain
    source: Source
    scope: Scope
    time: Time
    usage: Usage
    columns: Annotated[dict[Name, Column], Field(min_length=1)]
    metrics: dict[Name, Metric]

    @model_validator(mode='after')
    def validate_references(self):
        def references(names, label):
            unknown = set(names) - self.columns.keys()
            if unknown:
                raise ValueError(f'{label} references unknown columns: {sorted(unknown)}')
        if self.grain.keys is not None:
            references(self.grain.keys, 'grain.keys')
            if len(set(self.grain.keys)) != len(self.grain.keys):
                raise ValueError('grain.keys contains duplicates')
        references(self.time.dimensions, 'time.dimensions')
        if any(self.columns[name].type != 'date' for name in self.time.dimensions):
            raise ValueError('time.dimensions must reference date columns')
        for rule in self.time.rules:
            references(rule.columns, 'time.rules')
        for name, metric in self.metrics.items():
            references(metric.columns, f'metrics.{name}')
        return self


def validate_view_contract_v4(policy: dict) -> None:
    ViewContractV4.model_validate(policy)
