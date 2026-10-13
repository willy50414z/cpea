from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator

from cpea.application.models.query import ConversationTurn

class SQLGenerationRequest(BaseModel):
    request: str = Field(
        min_length=1, max_length=4000, description="使用者的自然語言需求"
    )
    history: list[ConversationTurn] = Field(default_factory=list, max_length=50)
