"""Immutable, versioned prompt resources for the single-View workflow."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
import json

from cpea.workflows.text_to_sql.schemas import SQLClauseMapping, SQLClauseMappingV3


HUMAN_TEMPLATE = "需求: {request} table定義: {schema_context}"


@dataclass(frozen=True)
class MatchPrompt:
    version: str
    system: str
    human: str
    response_schema_version: str = "sql-clause-mapping-v2"

    @property
    def response_model(self):
        return SQLClauseMappingV3 if self.version in {"v3", "v4", "v5", "v6"} else SQLClauseMapping

    @property
    def system_sha256(self) -> str:
        return sha256(self.system.encode("utf-8")).hexdigest()

    @property
    def human_sha256(self) -> str:
        return sha256(self.human.encode("utf-8")).hexdigest()

    @property
    def response_schema_sha256(self) -> str:
        payload = json.dumps(self.response_model.model_json_schema(), sort_keys=True, ensure_ascii=False)
        return sha256(payload.encode("utf-8")).hexdigest()


def load_match_prompt(version: str = "v6") -> MatchPrompt:
    if version not in {"v1", "v2", "v3", "v4", "v5", "v6"}:
        raise ValueError(f"unknown MATCH_PROMPT version: {version}")
    system = files("cpea.workflows.text_to_sql").joinpath("prompts", "match", f"{version}.txt").read_text(encoding="utf-8")
    return MatchPrompt(version=version, system=system, human=HUMAN_TEMPLATE,
                       response_schema_version=f"sql-clause-mapping-{version}")
