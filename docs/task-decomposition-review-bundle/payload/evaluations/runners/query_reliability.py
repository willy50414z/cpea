"""Repeat-run, no-database evaluation of the single-query planning pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from cpea.bootstrap import AssistantRuntime
from evaluations.metadata import run_metadata, default_output

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
    expected_group_by: list[str] | None = None
    expected_order_by: list[str] | None = None
    expected_aggregations: dict[str, str] = Field(default_factory=dict)
    notes: str = ""


def evaluate_cases(cases: list[QueryReliabilityCase], service: Any, runs: int = 3, *,
                   max_failures: int | None = None,
                   on_record: Callable[[dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    if runs < 1:
        raise ValueError("runs must be positive")
    if max_failures is not None and max_failures < 1:
        raise ValueError("max_failures must be positive")
    records = []
    failed = 0
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
                    if case.expected_group_by is not None and plan.group_by != case.expected_group_by:
                        failures.append("group_by_mismatch")
                    if case.expected_order_by is not None and plan.order_by != case.expected_order_by:
                        failures.append("order_by_mismatch")
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
            if on_record is not None:
                on_record(records[-1])
            failed += not records[-1]['passed']
            if max_failures is not None and failed >= max_failures:
                return records
    return records


def main(argv=None, *, runtime=None, kind='real-model') -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", help="New private output path")
    parser.add_argument("--env-file")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--max-failures", type=int, help="Stop after this many failed cases")
    parser.add_argument("--progress", action="store_true", help="Print per-case progress to stderr")
    args = parser.parse_args(argv)
    if args.runs < 1 or (args.max_failures is not None and args.max_failures < 1):
        parser.error("runs and max-failures must be positive")
    runtime = runtime if runtime is not None else AssistantRuntime.from_env(args.env_file)
    cases = [QueryReliabilityCase.model_validate_json(line) for line in Path(args.dataset).read_text(encoding="utf-8").splitlines() if line.strip()]
    metadata = run_metadata(runtime, cases, kind=kind)
    target = Path(args.output or default_output(metadata, "query-reliability"))
    target.parent.mkdir(parents=True, exist_ok=True)
    completed = 0
    with target.open('x', encoding='utf-8') as output:
        def emit(record):
            nonlocal completed
            record['run_metadata'] = metadata
            output.write(json.dumps(record, ensure_ascii=False, default=str) + '\n')
            output.flush()
            completed += 1
            if args.progress:
                print(json.dumps({'event': 'case_complete', 'completed': completed,
                                  'passed': record['passed'], 'rejection_stage': record['rejection_stage']},
                                 ensure_ascii=False), file=sys.stderr, flush=True)

        records = evaluate_cases(cases, runtime.generation_service(), runs=args.runs,
                                 max_failures=args.max_failures, on_record=emit)
    print(json.dumps({"total": len(records), "passed": sum(record["passed"] for record in records),
                      "failed": sum(not record['passed'] for record in records),
                      "planned_total": len(cases) * args.runs,
                      "stopped_early": len(records) < len(cases) * args.runs,
                      "max_failures": args.max_failures,
                      "by_stage": {stage: sum(record["rejection_stage"] == stage for record in records)
                                   for stage in {record["rejection_stage"] for record in records}}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    # cpea-query-eval --runs 5
    raise SystemExit(main())
