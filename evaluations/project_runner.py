"""Run one project's fixed cases against its configured real model."""
from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess

from dotenv import dotenv_values

from cpea.bootstrap import AssistantRuntime
from cpea.config.deployment import DeploymentSettings
from cpea.config.database import SQLServerSettings
from cpea.config.projects import ProjectWorkspace, resolve_project
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from evaluations.governance_inputs import ModelTarget, ProjectCase, load_cases
from evaluations.view_matching_cases import validate_view_case
from evaluations.governance_runner import evaluate


def _runtime_for_project(workspace: ProjectWorkspace, *, allow_draft_profile: bool = False) -> AssistantRuntime:
    settings = AssistantSettings.from_env(workspace.env_file)
    if settings.integration_path and Path(settings.integration_path).resolve() != workspace.root:
        raise ValueError("CPEA_PROFILE_PATH conflicts with the selected project")
    if settings.deployment_file and not Path(settings.deployment_file).resolve().is_relative_to(workspace.root):
        raise ValueError("CPEA_DEPLOYMENT_FILE must remain inside the selected project")
    deployment = DeploymentSettings.load(settings.deployment_file,
        profile_path=str(workspace.root), datasource_id=settings.datasource_id)
    # Project evaluation grades SQL generation only; configured DB credentials
    # must not force a driver load or an accidental execution dependency.
    settings = replace(settings, sqlserver=SQLServerSettings())
    catalog = SchemaCatalog(workspace.root, allow_drafts=allow_draft_profile)
    return AssistantRuntime(settings, deployment=deployment, catalog=catalog,
                            match_prompt=load_match_prompt())


def _cases_for_project(workspace: ProjectWorkspace, runtime: AssistantRuntime):
    cases = load_cases(workspace.cases_file).cases
    raw_lines = [json.loads(line) for line in workspace.cases_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not cases:
        raise ValueError("selected project has no evaluation cases")
    allowed = {view.name: set(view.policy["columns"]) for view in runtime.catalog.views()}
    for wrapped, raw in zip(cases, raw_lines):
        if wrapped.view_matching_case is not None:
            validate_view_case(wrapped.view_matching_case, runtime.catalog)
            prompt = runtime.match_prompt or load_match_prompt()
            if wrapped.view_matching_case.prompt_sha256 != prompt.system_sha256:
                raise ValueError(f"{wrapped.case_id}: case prompt differs from active workflow prompt")
            continue
        case = ProjectCase.model_validate(raw)
        if case.profile_id != runtime.catalog.profile_id:
            raise ValueError(f"{case.case_id}: case profile_id does not match selected project")
        if case.expected_supported and not case.expected_view:
            raise ValueError(f"{case.case_id}: supported case requires expected_view")
        if case.expected_view:
            if case.expected_view not in allowed:
                raise ValueError(f"{case.case_id}: expected_view is outside the selected catalog")
            named = (set(case.expected_filters) | set(case.expected_filter_operators) |
                     set(case.forbidden_filters) | set(case.expected_select_columns) |
                     set(case.expected_group_by or []) | set(case.expected_order_by or []) |
                     set(case.expected_aggregations))
            if not named <= allowed[case.expected_view]:
                raise ValueError(f"{case.case_id}: expected column is outside the selected view")
    return cases


def _single_target(runtime: AssistantRuntime) -> ModelTarget:
    provider = {"ollama": "local", "llamacpp": "local", "azure": "azure", "gcp": "gcp"}[
        runtime.settings.llm_provider]
    transport = {"gcp": "google"}.get(runtime.settings.llm_provider, runtime.settings.llm_provider)
    return ModelTarget(provider=provider, transport=transport, model=runtime.settings.llm_model,
                       deployment=runtime.settings.llm_model if provider != "local" else None)


def evaluate_project(project_id: str, *, runs: int = 3, concurrency: int = 1,
                     projects_root: str | Path | None = None,
                     repo_root: str | Path | None = None,
                     runtime: AssistantRuntime | None = None,
                     model_factory=None,
                     timestamp: datetime | None = None,
                     allow_draft_profile: bool = False, exploratory: bool = False,
                     max_model_calls: int | None = None, call_ledger: str | Path | None = None):
    if runs < 1 or concurrency < 1:
        raise ValueError("runs and concurrency must be positive")
    workspace = resolve_project(project_id, projects_root=projects_root)
    runtime = runtime or _runtime_for_project(workspace, allow_draft_profile=allow_draft_profile)
    if runtime.catalog.root != workspace.root:
        raise ValueError("runtime profile conflicts with the selected project")
    if runtime.catalog.status == "draft" and not allow_draft_profile:
        raise ValueError("draft profile requires --allow-draft-profile")
    cases = _cases_for_project(workspace, runtime)
    if exploratory:
        cases = [case for case in cases if case.view_matching_case is None
                 or (case.view_matching_case.validation_status == "validated"
                     and case.view_matching_case.review_status != "rejected")]
    else:
        cases = [case for case in cases if case.view_matching_case is None
                 or case.view_matching_case.approved_for(runtime.catalog.fingerprint)]
        if not cases:
            raise ValueError("no approved cases for formal evaluation; use --exploratory for pending cases")
    root = Path(repo_root).resolve() if repo_root else Path(__file__).resolve().parents[1]
    sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True,
                         capture_output=True, check=True).stdout.strip()
    created = timestamp or datetime.now(timezone.utc)
    run_id = created.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + sha[:8]
    output = workspace.evaluations_root / run_id
    case_digest = sha256(workspace.cases_file.read_bytes()).hexdigest()
    env_values = dotenv_values(workspace.env_file, interpolate=False, encoding="utf-8")
    results, calls = evaluate(cases, [_single_target(runtime)], runtime=runtime,
        output=output, runs=runs, concurrency=concurrency, live=model_factory is None,
        model_factory=model_factory, repo_root=root, env_values=env_values,
        allowed_output_root=workspace.evaluations_root,
        max_model_calls=max_model_calls, call_ledger=call_ledger,
        extra_metadata={"project_id": workspace.project_id,
                        "project_casefile_sha256": case_digest,
                        "profile_status": runtime.catalog.status,
                        "allow_draft_profile": allow_draft_profile,
                        "exploratory": exploratory})
    run_path = output / "run.json"
    metadata = json.loads(run_path.read_text(encoding="utf-8"))
    # The shared runner writes final completed/skipped totals before reporting.
    return {"project": project_id, "run_id": run_id, "output": str(output),
            "planned_total": len(cases) * runs, "completed_total": metadata["completed_total"],
            "skipped_total": metadata["skipped_total"],
            "calls": len(calls), "mode": metadata["mode"]}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--allow-draft-profile", action="store_true")
    parser.add_argument("--exploratory", action="store_true")
    parser.add_argument("--max-model-calls", type=int)
    parser.add_argument("--call-ledger")
    args = parser.parse_args(argv)
    try:
        result = evaluate_project(args.project, runs=args.runs, concurrency=args.concurrency,
                                  allow_draft_profile=args.allow_draft_profile,
                                  exploratory=args.exploratory,
                                  max_model_calls=args.max_model_calls, call_ledger=args.call_ledger)
    except (ValueError, FileNotFoundError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
