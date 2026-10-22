"""Typed view contract identity, independent of files and LLM frameworks."""
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class ViewDefinition:
    name: str
    summary: str
    detail_path: str
    policy: dict[str, Any]
