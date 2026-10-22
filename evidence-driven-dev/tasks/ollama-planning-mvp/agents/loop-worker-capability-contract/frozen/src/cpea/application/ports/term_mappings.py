"""Scope-bound vocabulary records and repository boundary."""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Literal, Protocol
from pydantic import BaseModel, ConfigDict, Field, model_validator


def normalize_term(term: str) -> str:
    return term.strip().translate(str.maketrans('ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'))


def view_fingerprint(catalog, view: str) -> str:
    definition = next(item for item in catalog.views() if item.name == view)
    contract = {'view': definition.name, 'summary': definition.summary, 'policy': definition.policy}
    return sha256(json.dumps(contract, sort_keys=True, ensure_ascii=False,
                             separators=(',', ':')).encode('utf-8')).hexdigest()


class MappingScope(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    profile_id: str = Field(min_length=1)
    datasource_id: str | None


class TermMapping(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    id: str = Field(min_length=1)
    term: str = Field(min_length=1)
    normalized_term: str
    view: str
    column: str
    view_contract_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    status: Literal['active', 'revoked'] = 'active'
    relation: Literal['user_confirmed_column_mapping'] = 'user_confirmed_column_mapping'
    confirmed_at: str
    confirmed_by: str | None = None

    @model_validator(mode='after')
    def normalized(self):
        if not self.normalized_term or self.normalized_term != normalize_term(self.term):
            raise ValueError('invalid normalized_term')
        if datetime.fromisoformat(self.confirmed_at.replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('confirmed_at requires timezone')
        return self

    @property
    def key(self):
        return self.normalized_term, self.view


class MappingSnapshot(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    schema_version: Literal[1] = 1
    revision: int = Field(default=0, ge=0)
    scope: MappingScope
    mappings: list[TermMapping] = Field(default_factory=list)

    @model_validator(mode='after')
    def unique(self):
        ids = [m.id for m in self.mappings]
        active = [m.key for m in self.mappings if m.status == 'active']
        if len(ids) != len(set(ids)) or len(active) != len(set(active)):
            raise ValueError('duplicate mapping id or active term')
        return self

    def active(self):
        return {m.key: m for m in self.mappings if m.status == 'active'}


class MappingStoreError(ValueError):
    pass


class MappingConflict(Exception):
    def __init__(self, records: list[TermMapping]):
        super().__init__('term_mapping_changed')
        self.records = records


class TermMappingRepository(Protocol):
    def read(self) -> MappingSnapshot: ...
    def commit(self, proposals: list[TermMapping], *, used: list[TermMapping],
               replacements: dict[tuple[str, str], str]) -> list[TermMapping]: ...
