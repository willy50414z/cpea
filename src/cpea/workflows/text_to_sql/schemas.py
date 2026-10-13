from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

from cpea.domain.models import QueryFact, SchemaLink, _normalize_limitations

class AnswerDraft(BaseModel):
    answer: str
    citations: list[str] = Field(default_factory=list)

class FactDraft(BaseModel):
    supported: bool = True
    facts: list[QueryFact] = Field(default_factory=list)
    ambiguity: list[str] = Field(default_factory=list)
    explanation: str = ""

class SchemaLinkDraft(BaseModel):
    supported: bool = False
    links: list[SchemaLink] = Field(default_factory=list)
    unresolved_facts: list[str] = Field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = Field(default_factory=list)

    _normalize_limitations = field_validator("limitations", mode="before")(_normalize_limitations)
