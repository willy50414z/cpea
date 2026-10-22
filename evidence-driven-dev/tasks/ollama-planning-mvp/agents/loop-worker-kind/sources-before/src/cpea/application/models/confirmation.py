"""Public confirmation protocol; descriptions are evidence, not model reasoning."""
from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ConfirmationOption(BaseModel):
    id: str
    column: str | None
    description: str


class ConfirmationItem(BaseModel):
    id: str
    term: str
    view: str
    reason: str
    options: list[ConfirmationOption] = Field(min_length=1, max_length=4)


class Clarification(BaseModel):
    confirmation_id: str
    expires_at: str
    kind: Literal['field_mapping', 'replace_mapping'] = 'field_mapping'
    items: list[ConfirmationItem]

    def public_payload(self):
        """Browser state only contains opaque IDs and business language."""
        return {'confirmation_id': self.confirmation_id, 'expires_at': self.expires_at, 'kind': self.kind,
                'items': [{'id': item.id, 'term': item.term, 'reason': item.reason,
                           'options': [{'id': option.id, 'description': option.description,
                                        'rephrase': option.column is None} for option in item.options]}
                          for item in self.items]}


class ConfirmationDecision(BaseModel):
    model_config = ConfigDict(extra='forbid')
    item_id: str
    option_id: str


class ConfirmationRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmation_id: str = Field(min_length=20, max_length=200)
    action: Literal['confirm', 'cancel', 'rephrase']
    decisions: list[ConfirmationDecision] | None = None

    @model_validator(mode='after')
    def validate_action(self):
        if self.action in ('cancel', 'rephrase') and self.decisions is not None:
            raise ValueError('cancel/rephrase must not include decisions')
        if self.action == 'confirm' and not self.decisions:
            raise ValueError('confirm requires all decisions')
        return self


class TermMappingReasoning(BaseModel):
    term: str
    view: str
    column: str
    mapping_id: str | None = None
    source: Literal['confirmed_this_request', 'reused_confirmation', 'automatically_resolved']
    confirmed_at: str | None = None
    description: str = ''
    reason: str


class ConfirmationError(ValueError):
    def __init__(self, code: str, status_code: int = 422):
        super().__init__(code)
        self.code = code
        self.status_code = status_code
