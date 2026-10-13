"""Repeat-run, no-database evaluation of the single-query planning pipeline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from importlib.resources import files
from cpea.bootstrap import AssistantRuntime
from evaluations.metadata import run_metadata, default_output, write_jsonl

from pydantic import BaseModel, Field

from cpea.application.services.sql_generation import SQLGenerationService
from cpea.infrastructure.llm.factory import get_llm_config


class QueryReliabilityCase(BaseModel):
    question: str
    expected_supported: bool
    expected_view: str | None = None
    expected_filters: dict[str, str] = Field(default_factory=dict)
    allow_extra_filters: bool = False
    expected_filter_operators: dict[str, str] = Field(default_factory=dict)
    forbidden_filters: list[str] = Field(default_factory=list)
    expected_select_columns: list[str] = Field(default_factory=list)
    expected_group_by: list[str] = Field(default_factory=list)
    expected_aggregations: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


def evaluate_cases(cases: list[QueryReliabilityCase], service: Any, runs: int = 3) -> list[dict[str, Any]]:
    if runs < 1:
        raise ValueError("runs must be positive")
    records = []
    for case in cases:
        for run in range(1, runs + 1):
            try:
                result = service.generate(case.question)
                trace = result.query_trace
                failures = []
                if result.supported != case.expected_supported:
                    failures.append("support_mismatch")
                if case.expected_view and result.supported and case.expected_view not in result.selected_views:
                    failures.append("view_mismatch")
                plan = result.query_plan
                if result.supported and plan:
                    for column, value in case.expected_filters.items():
                        if not any(item.column == column and str(item.value) == value for item in plan.filters):
                            failures.append(f"filter_mismatch:{column}")
                    if not case.allow_extra_filters:
                        for item in plan.filters:
                            if item.column not in case.expected_filters:
                                failures.append(f"unexpected_filter:{item.column}")
                    for column, operator in case.expected_filter_operators.items():
                        if not any(item.column == column and item.operator == operator for item in plan.filters):
                            failures.append(f"filter_operator_mismatch:{column}")
                    for column in case.forbidden_filters:
                        if any(item.column == column for item in plan.filters):
                            failures.append(f"forbidden_filter:{column}")
                    for column in case.expected_select_columns:
                        if column not in plan.select_columns:
                            failures.append(f"select_mismatch:{column}")
                    for column in case.expected_group_by:
                        if column not in plan.group_by:
                            failures.append(f"group_by_mismatch:{column}")
                    for column, aggregation in case.expected_aggregations.items():
                        if plan.aggregations.get(column) != aggregation:
                            failures.append(f"aggregation_mismatch:{column}")
                records.append({
                    "question": case.question, "run": run, "passed": not failures,
                    "failure_reasons": [*failures, *(trace.validation_errors if trace and failures else [])],
                    "rejection_stage": trace.rejection_stage if trace else None,
                    "candidate_attempts": [attempt.model_dump(mode="json") for attempt in trace.candidate_attempts] if trace else [],
                    "request_facts": [fact.model_dump(mode="json") for fact in trace.request_facts] if trace else [],
                    "unmatched_items": sorted({item for attempt in trace.candidate_attempts
                                               for item in attempt.unresolved}) if trace else [],
                    "retrieval_latency_ms": result.retrieval_latency_ms,
                    "reranker_latency_ms": result.reranker_latency_ms,
                    "result": result.model_dump(mode="json"),
                })
            except Exception as exc:  # noqa: BLE001 - retain stage-level evaluation failures
                records.append({"question": case.question, "run": run, "passed": False,
                                "failure_reasons": [f"exception:{type(exc).__name__}:{exc}"],
                                "rejection_stage": "exception", "result": None})
    return records


def main(argv=None, *, runtime=None, kind='real-model') -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default=str(files("evaluations").joinpath("datasets/query_reliability.jsonl")))
    parser.add_argument("--output", help="New private output path")
    parser.add_argument("--env-file")
    parser.add_argument("--runs", type=int, default=3)
    args = parser.parse_args(argv)
    runtime = runtime if runtime is not None else AssistantRuntime.from_env(args.env_file)
    cases = [QueryReliabilityCase.model_validate_json(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    metadata = run_metadata(runtime, cases, kind=kind)
    records = evaluate_cases(cases, runtime.generation_service(), runs=args.runs)
    for record in records:
        record["run_metadata"] = metadata
    write_jsonl(args.output or default_output(metadata, "query-reliability"), records)
    print(json.dumps({"total": len(records), "passed": sum(record["passed"] for record in records),
                      "by_stage": {stage: sum(record["rejection_stage"] == stage for record in records)
                                   for stage in {record["rejection_stage"] for record in records}}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # cpea-query-eval --runs 5
    raise SystemExit(main())
