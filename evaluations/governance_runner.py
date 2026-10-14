"""End-to-end and repeat-run model governance evaluation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter
from urllib.parse import urlparse
from uuid import uuid4
from types import SimpleNamespace
from dotenv import dotenv_values

from cpea.bootstrap import AssistantRuntime
from cpea.application.services.sql_execution import SQLExecutionResult
from cpea.infrastructure.llm.factory import get_llm_config
from evaluations.governance_inputs import GovernanceCase, ModelTarget, load_cases, load_models
from evaluations.governance_trace import CallRecorder, TracedModel
from evaluations.governance_reports import regenerate, write_reports
from evaluations.metadata import run_metadata
from evaluations.runners.query_reliability import evaluate_cases


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def preflight(root: Path, output: Path, *, live: bool) -> str:
    root = root.resolve()
    output = output.resolve()
    try:
        output.relative_to(root / "artifacts" / "evaluations")
    except ValueError:
        raise ValueError("output must be under artifacts/evaluations") from None
    if output.exists():
        raise FileExistsError(output)
    if subprocess.run(["git", "check-ignore", "-q", str(output / "calls.jsonl")], cwd=root).returncode != 0:
        raise ValueError("output must be Git-ignored")
    if live and _git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("live evaluation requires a clean Git worktree")
    return _git(root, "rev-parse", "HEAD")


def _target_settings(base, target: ModelTarget, env_values=None):
    env_values = env_values or {}
    def env(name):
        return os.environ.get(name) or env_values.get(name) if name else None
    return replace(base,
                   llm_provider={"local": target.transport, "azure": "azure", "gcp": "gcp"}[target.provider],
                   llm_model=target.deployment or target.model,
                   context_window=target.num_ctx or base.context_window,
                   max_output_tokens=target.max_token or base.max_output_tokens,
                   temperature=target.temperature if target.temperature is not None else base.temperature,
                   top_p=target.top_p if target.top_p is not None else base.top_p,
                   llm_base_url=env(target.endpoint_env) or base.llm_base_url,
                   llm_api_key=env(target.api_key_env) or base.llm_api_key,
                   gcp_project=env(target.project_env) or base.gcp_project,
                   gcp_location=env(target.location_env) or base.gcp_location)


def _provider_preflight(target: ModelTarget, settings, env_values=None) -> None:
    env_values = env_values or {}
    if target.endpoint_env and not (os.environ.get(target.endpoint_env) or env_values.get(target.endpoint_env)):
        raise ValueError(f"{target.model}: configure {target.endpoint_env}")
    if target.provider == "azure":
        if find_spec("langchain_openai") is None:
            raise ValueError(f"{target.model}: install optional langchain-openai")
        if settings.llm_api_key == "not-needed" or "example.invalid" in settings.llm_base_url:
            raise ValueError(f"{target.model}: configure Azure endpoint and API key")
        endpoint = urlparse(settings.llm_base_url)
        if endpoint.scheme != "https" or not endpoint.netloc:
            raise ValueError(f"{target.model}: Azure endpoint must be an HTTPS URL")
    if target.provider == "gcp":
        if find_spec("langchain_google_genai") is None:
            raise ValueError(f"{target.model}: install optional langchain-google-genai")
        if not settings.gcp_project:
            raise ValueError(f"{target.model}: configure GCP project")


def _identity(target: ModelTarget, settings, *, live: bool) -> tuple[str | None, str | None]:
    if not live or target.transport != "ollama":
        return None, None
    import requests
    base = settings.llm_base_url.rstrip("/")
    try:
        response = requests.post(f"{base}/api/show", json={"model": target.model}, timeout=10)
        response.raise_for_status()
        details = response.json().get("details", {})
        quantization = details.get("quantization_level")
        tags = requests.get(f"{base}/api/tags", timeout=10)
        tags.raise_for_status()
        digest = next((item.get("digest") for item in tags.json().get("models", [])
                       if item.get("name") == target.model), None)
        return quantization, digest
    except (requests.RequestException, ValueError, KeyError):
        return None, None


def grade(case: GovernanceCase, generation, answer: str | None, citations: list[str],
          *, execution_error: str | None = None) -> tuple[str | None, str | None, list[str]]:
    if case.reliability_case is not None:
        record = evaluate_cases([case.reliability_case],
                                SimpleNamespace(generate=lambda question: generation), runs=1)[0]
        return ("pass" if record["passed"] else "fail"), None, record["failure_reasons"]
    expected = case.expected_result
    failures: list[str] = []
    if expected.supported is not None and generation.supported != expected.supported:
        failures.append("support_mismatch")
    if expected.view and expected.view not in generation.selected_views:
        failures.append("view_mismatch")
    for view in expected.forbidden_views:
        if view in generation.selected_views:
            failures.append(f"forbidden_view:{view}")
    plan = generation.query_plan
    if expected.filters or expected.forbidden_filters or expected.group_by or expected.aggregations:
        if plan is None:
            failures.append("missing_query_plan")
        else:
            for column, value in expected.filters.items():
                if not any(item.column == column and str(item.value) == value for item in plan.filters):
                    failures.append(f"filter_mismatch:{column}")
            for column in expected.forbidden_filters:
                if any(item.column == column for item in plan.filters):
                    failures.append(f"forbidden_filter:{column}")
            for column in expected.group_by:
                if column not in plan.group_by:
                    failures.append(f"group_by_mismatch:{column}")
            for column, operation in expected.aggregations.items():
                if plan.aggregations.get(column) != operation:
                    failures.append(f"aggregation_mismatch:{column}")
    sql = generation.sql or ""
    for token in expected.sql_forbidden:
        if token.casefold() in sql.casefold():
            failures.append(f"forbidden_sql:{token}")
    if case.category == "security" and expected.supported is False and sql:
        failures.append("security_sql_generated")
    if expected.clarification:
        trace = generation.query_trace
        unresolved = any(attempt.unresolved for attempt in trace.candidate_attempts) if trace else False
        if generation.supported or not generation.limitations or not unresolved:
            failures.append("missing_clarification")
    if execution_error:
        return "error", None, [*failures, f"execution:{execution_error}"]
    if expected.answer_contains or expected.answer_excludes or expected.require_citation:
        if answer is None:
            return "error", None, [*failures, "answer_unavailable"]
        for text in expected.answer_contains:
            if text.casefold() not in answer.casefold():
                failures.append(f"answer_missing:{text}")
        for text in expected.answer_excludes:
            if text.casefold() in answer.casefold():
                failures.append(f"answer_forbidden:{text}")
        if expected.require_citation and not citations:
            failures.append("missing_citation")
    if failures:
        return "fail", None, failures
    if expected.human_review:
        return None, "pending", []
    return "pass", None, []


def _run_one(case: GovernanceCase, target: ModelTarget, repetition: int, base: AssistantRuntime,
             recorder: CallRecorder, model_factory, env_values, warmup: bool, identity) -> dict:
    settings = _target_settings(base.settings, target, env_values)
    started = perf_counter()
    quantization, digest = identity
    generation = None
    answer = None
    citations: list[str] = []
    error = None
    try:
        model = model_factory(target, settings) if model_factory else get_llm_config(settings=settings)
        traced = TracedModel(model, recorder, case_id=case.case_id, repetition=repetition,
                             target=target, settings=settings, quantization=quantization, model_digest=digest)
        if warmup:
            traced.at("warmup").invoke('只回傳 JSON：{"ready": true}')
        runtime = AssistantRuntime(settings, catalog=base.catalog, llm=traced,
                                   executor=base.executor, datasource_id=base.datasource_id,
                                   retriever=base.retriever, context_packer=base.context_packer)
        generation = runtime.generate(case.question)
        needs_answer = bool(case.expected_result.answer_contains or case.expected_result.answer_excludes
                            or case.expected_result.require_citation)
        if generation.supported and needs_answer:
            if runtime.executor is None or not runtime.datasource_id:
                error = "answer requires an injected SQL executor and datasource"
            else:
                columns, rows = runtime.executor(runtime.datasource_id, generation.sql)
                bounded = rows[:settings.max_rows]
                execution = SQLExecutionResult(generation, columns, bounded, 1, False,
                                               rows_truncated=len(rows) > len(bounded))
                response = runtime.answer_service(traced.at("answer_synthesis")).synthesize(case.question, execution)
                answer, citations = response.answer, response.citations
    except Exception as exc:  # retain partial call trace on failures
        error = f"{type(exc).__name__}: {exc}"
    if generation is None:
        status, review_state, failures = "error", None, [error or "generation_unavailable"]
    elif error:
        status, review_state, failures = "error", None, [error]
    else:
        status, review_state, failures = grade(case, generation, answer, citations)
    # Call records are correlated by key; this works even with concurrent runs.
    return {
        "run_id": recorder.run_id, "case_id": case.case_id,
        "category": case.category, "difficulty": case.difficulty,
        "question": case.question, "expected_result": case.expected_result.model_dump(mode="json"),
        "provider": target.provider, "model": target.model, "repetition": repetition,
        "status": status, "review_state": review_state, "failure_reasons": failures,
        "generation": generation.model_dump(mode="json") if generation else None,
        "answer": answer, "citations": citations, "call_ids": [],
        "elapsed_ms": (perf_counter() - started) * 1000,
    }


def evaluate(cases: list[GovernanceCase], targets: list[ModelTarget], *, runtime: AssistantRuntime,
             output: Path, runs: int = 1, concurrency: int = 1, live: bool = False,
             model_factory=None, repo_root: Path | None = None, env_values=None,
             warmup: bool = False, max_failures: int | None = None) -> tuple[list[dict], list[dict]]:
    if not live and model_factory is None:
        raise ValueError("select --live or inject an offline model factory")
    if runs < 1 or concurrency < 1:
        raise ValueError("runs and concurrency must be positive")
    if max_failures is not None and (max_failures < 1 or concurrency != 1):
        raise ValueError("max_failures must be positive and requires concurrency 1")
    root = repo_root or Path(__file__).resolve().parents[1]
    sha = preflight(root, output, live=live)
    if live:
        for target in targets:
            _provider_preflight(target, _target_settings(runtime.settings, target, env_values), env_values)
    identities = {(target.provider, target.model, target.deployment):
                  _identity(target, _target_settings(runtime.settings, target, env_values), live=live)
                  for target in targets}
    metadata = run_metadata(runtime, cases, kind="real-model" if live else "offline-synthetic")
    metadata.update({"run_id": output.name, "git_sha": sha, "mode": "live" if live else "offline-synthetic",
                     "runs": runs, "planned_total": len(cases) * len(targets) * runs,
                     "max_failures": max_failures,
                     "targets": [target.model_dump(mode="json") for target in targets]})
    output.mkdir(parents=True, exist_ok=False)
    (output / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    recorder = CallRecorder(run_id=output.name, git_sha=sha, concurrency=concurrency,
                            path=output / "calls.jsonl")
    work = [(case, target, repetition) for case in cases for target in targets
            for repetition in range(1, runs + 1)]
    results = []
    with (output / "results.jsonl").open("x", encoding="utf-8") as stream:
        def persist(result):
            result["call_ids"] = [call["call_id"] for call in recorder.calls
                                  if (call["case_id"], call["model"], call["repetition"]) ==
                                  (result["case_id"], result["model"], result["repetition"])]
            results.append(result)
            stream.write(json.dumps(result, ensure_ascii=False, default=str) + "\n")
            stream.flush()
        if concurrency == 1:
            failures = {}
            for item in work:
                key = (item[1].provider, item[1].model, item[1].deployment)
                if max_failures is not None and failures.get(key, 0) >= max_failures:
                    continue
                result = _run_one(*item, runtime, recorder, model_factory, env_values, warmup,
                                  identities[key])
                persist(result)
                failures[key] = failures.get(key, 0) + (result["status"] in {"fail", "error"})
        else:
            with ThreadPoolExecutor(max_workers=concurrency) as pool:
                futures = [pool.submit(_run_one, *item, runtime, recorder, model_factory, env_values, warmup,
                                       identities[(item[1].provider, item[1].model, item[1].deployment)])
                           for item in work]
                for future in as_completed(futures):
                    persist(future.result())
    write_reports(output, results, recorder.calls)
    return results, recorder.calls


def main(argv=None, *, runtime=None, model_factory=None) -> int:
    arguments = list(argv) if argv is not None else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    sub.add_parser("report", help="Regenerate CSV and Markdown from private JSONL").add_argument("run_dir")
    for mode in ("compare", "stability"):
        command = sub.add_parser(mode)
        command.add_argument("--cases", required=True)
        command.add_argument("--env-file")
        command.add_argument("--runs", type=int, default=1 if mode == "compare" else 3)
        command.add_argument("--concurrency", type=int, default=1)
        command.add_argument("--output-dir")
        command.add_argument("--live", action="store_true")
        command.add_argument("--warmup", action="store_true")
        command.add_argument("--max-failures", type=int, help="Stop each model after this many failures (concurrency 1)")
        if mode == "compare":
            command.add_argument("--models", required=True)
    args = parser.parse_args(arguments)
    if args.mode == "report":
        regenerate(Path(args.run_dir))
        return 0
    cases = load_cases(args.cases).cases
    base = runtime or AssistantRuntime.from_env(args.env_file)
    if args.mode == "compare":
        targets = load_models(args.models).models
    else:
        provider = {"ollama": "local", "llamacpp": "local", "azure": "azure", "gcp": "gcp"}[base.settings.llm_provider]
        transport = {"gcp": "google"}.get(base.settings.llm_provider, base.settings.llm_provider)
        targets = [ModelTarget(provider=provider, transport=transport, model=base.settings.llm_model,
                               deployment=base.settings.llm_model if provider != "local" else None)]
    root = Path(__file__).resolve().parents[1]
    output = Path(args.output_dir) if args.output_dir else root / "artifacts" / "evaluations" / uuid4().hex
    env_values = dotenv_values(args.env_file, interpolate=False) if args.env_file else {}
    results, _ = evaluate(cases, targets, runtime=base, output=output, runs=args.runs,
                          concurrency=args.concurrency, live=args.live, model_factory=model_factory,
                          repo_root=root, env_values=env_values, warmup=args.warmup,
                          max_failures=args.max_failures)
    print(json.dumps({"run_id": output.name, "results": len(results), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
