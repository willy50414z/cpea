from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator
from pydantic import ConfigDict

from cpea.application.models.query import ConversationTurn

class SQLGenerationRequest(BaseModel):
    request: str = Field(
        min_length=1, max_length=4000, description="使用者的自然語言需求"
    )
    history: list[ConversationTurn] = Field(default_factory=list, max_length=0)

    @field_validator('request')
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError('request must not be blank')
        return value

    @field_validator('history', mode='before')
    @classmethod
    def no_history(cls, value):
        if value:
            raise ValueError('history_not_supported')
        return value


class StreamQueryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request: str = Field(min_length=1, max_length=4000)

    @field_validator('request')
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('request must not be blank')
        return value
