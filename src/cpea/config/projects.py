"""Resolve a private project workspace without accepting arbitrary project paths."""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re
from dotenv import dotenv_values


_PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*\Z")


def configured_projects_root(env_file: str | Path | None = None) -> Path:
    selected = env_file or os.environ.get('CPEA_ENV_FILE')
    base = Path(selected).resolve().parent if selected else Path.cwd()
    values = dotenv_values(selected, interpolate=False, encoding='utf-8') if selected else {}
    value = os.environ.get('CPEA_PROJECTS_ROOT') or values.get('CPEA_PROJECTS_ROOT')
    return (base / value).resolve() if value else (Path.cwd() / 'projects').resolve()


@dataclass(frozen=True)
class ProjectWorkspace:
    project_id: str
    root: Path

    @property
    def env_file(self) -> Path:
        return self.root / ".env"

    @property
    def cases_file(self) -> Path:
        return self.root / "evaluations" / "cases.jsonl"

    @property
    def evaluations_root(self) -> Path:
        return self.root / "artifacts" / "evaluations"


def resolve_project(project_id: str, *, projects_root: str | Path | None = None,
                    require_cases: bool = True) -> ProjectWorkspace:
    if not _PROJECT_ID.fullmatch(project_id):
        raise ValueError("project must be a valid project ID")
    configured_root = projects_root or os.environ.get("CPEA_PROJECTS_ROOT") or Path.cwd() / "projects"
    base = Path(configured_root).resolve()
    root = (base / project_id).resolve()
    if not root.is_relative_to(base) or not root.is_dir():
        raise ValueError("selected project does not exist inside the projects root")
    workspace = ProjectWorkspace(project_id, root)
    if not workspace.evaluations_root.resolve().is_relative_to(root):
        raise ValueError("selected project artifacts must remain inside the project")
    required = [workspace.env_file, root / "manifest.yaml", root / "catalog.yaml"]
    if require_cases:
        required.append(workspace.cases_file)
    for path in required:
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"selected project is missing a valid {path.name} file")
    return workspace
