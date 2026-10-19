"""Small real-model probes for the existing grain and confirmation workflow."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace

from cpea.application.models.query import ClarificationChoice
from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.factory import get_llm_config
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from evaluations.call_budget import CallBudget
from evaluations.governance_inputs import ModelTarget
from evaluations.governance_runner import _identity, preflight
from evaluations.governance_trace import CallRecorder, TracedModel
from evaluations.metadata import run_metadata
from evaluations.retrieval_benchmark import ROOT


ORDER = "demo_retail.v_order_summary"
DETAIL = "demo_retail.v_sales_detail"
PROBES = [
    {"case_id": "GRAIN-Q1", "request": "查詢每張訂單的毛利。", "kind": "order"},
    {"case_id": "GRAIN-Q2", "request": "查詢每個商品明細的毛利。", "kind": "detail"},
    {"case_id": "GRAIN-Q3", "request": "查詢逐筆成交管道和毛利。", "kind": "ambiguous"},
    {"case_id": "GRAIN-EQUIVALENT", "request": "計算所有已完成訂單的毛利總和。", "kind": "equivalent"},
    {"case_id": "CONTRACT-COLUMN", "request": "列出會員手機及每張訂單付款銀行和毛利。", "kind": "unsupported"},
    {"case_id": "CONTRACT-OPERATOR", "request": "列出各訂單商品單價，並用 LIKE 12% 篩選 unit_price。", "kind": "unsupported"},
    {"case_id": "CONTRACT-AGGREGATION", "request": "把所有門市每月毛利率直接加總成一個數。", "kind": "unsupported"},
]


def grade_probe(kind, response) -> bool:
    if kind == "unsupported":
        return response.status == "unsupported" and response.sql is None
    if kind == "ambiguous":
        return (response.status == "needs_clarification" and response.sql is None
                and response.clarification is not None
                and {ORDER, DETAIL} <= {option.id for option in response.clarification.options})
    if response.status != "ready" or response.query_plan is None:
        return False
    plan = response.query_plan
    if "gross_profit" not in plan.select_columns:
        return False
    if kind == "order":
        return (plan.source_views == [ORDER] and not plan.aggregations and not plan.group_by
                or plan.source_views == [DETAIL] and plan.aggregations == {"gross_profit": "sum"}
                and bool(set(plan.group_by) & {"order_id", "order_no"})
                and set(plan.group_by) <= {"order_id", "order_no"})
    if kind == "detail":
        return plan.source_views == [DETAIL] and not plan.aggregations and not plan.group_by
    if kind == "equivalent":
        return (plan.source_views[0] in {ORDER, DETAIL, "demo_retail.v_daily_sales",
                                        "demo_retail.v_product_monthly", "demo_retail.v_store_monthly_kpi"}
                and plan.aggregations == {"gross_profit": "sum"} and not plan.group_by and not plan.filters)
    raise ValueError("unknown probe kind")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, default=ROOT / "projects/retail/.env")
    parser.add_argument("--profile", type=Path, default=ROOT / "projects/retail")
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--exploratory", action="store_true", required=True)
    parser.add_argument("--max-model-calls", type=int, default=100)
    parser.add_argument("--case-id", action="append", choices=[case["case_id"] for case in PROBES])
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    output_root = args.profile / "artifacts/grain-probes"
    output = output_root / stamp
    git_sha = preflight(ROOT, output, live=True, allowed_output_root=output_root)
    settings = AssistantSettings.from_env(args.env_file)
    if settings.integration_path and Path(settings.integration_path).resolve() != args.profile.resolve():
        raise ValueError("environment profile differs from probe profile")
    catalog = SchemaCatalog(args.profile, allow_drafts=True)
    provider = "local" if settings.llm_provider in {"ollama", "llamacpp"} else settings.llm_provider
    target = ModelTarget(provider=provider, transport="google" if provider == "gcp" else settings.llm_provider,
                         model=settings.llm_model)
    quantization, digest = _identity(target, settings, live=True)
    model = get_llm_config(settings=settings)
    output.mkdir(parents=True, exist_ok=False)
    probes = [case for case in PROBES if not args.case_id or case["case_id"] in args.case_id]
    metadata = run_metadata(SimpleNamespace(settings=settings, catalog=catalog), probes,
                            kind="real-model-grain-probe")
    metadata.update(experiment_id=args.experiment_id, git_sha=git_sha, review_status="pending",
                    evaluation_status="exploratory", quantization=quantization, model_digest=digest,
                    regression_dataset_sha256=sha256((args.profile / "evaluations/cases.jsonl").read_bytes()).hexdigest(),
                    max_model_calls=args.max_model_calls)
    recorder = CallRecorder(run_id=stamp, git_sha=git_sha, path=output / "calls.jsonl")
    budget = CallBudget(args.max_model_calls)
    results = []
    metadata["status"] = "running"
    def save():
        (output / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    def invoke(case, *, choice=None):
        traced = TracedModel(model, recorder, case_id=case["case_id"], repetition=1,
                             target=target, settings=settings, quantization=quantization,
                             model_digest=digest, budget=budget)
        workflow = SQLGenerationWorkflow(traced, catalog, settings=settings)
        before = len(recorder.calls)
        started = perf_counter()
        response = workflow.invoke(case["request"], clarification_choice=choice)
        calls = recorder.calls[before:]
        def tokens(key):
            values = [call.get(key) for call in calls]
            return sum(values) if values and all(value is not None for value in values) else None
        row = {**case, "git_sha": git_sha, "response": response.model_dump(mode="json"),
               "latency_ms": (perf_counter() - started) * 1000,
               "llm_calls": len(recorder.calls) - before,
               "tokens_in": tokens("input_tokens"), "tokens_out": tokens("output_tokens"),
               "pass": grade_probe(case["kind"], response) if choice is None else (
                   response.status == "ready" and response.selected_views == [choice.option_id]
                   and response.query_plan is not None and not response.query_plan.aggregations
                   and not response.query_plan.group_by
                   and "gross_profit" in response.query_plan.select_columns
                   and "sales_channel" in response.query_plan.select_columns)}
        results.append(row)
        with (output / "results.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{case['case_id']}: {response.status}, pass={row['pass']}, calls={row['llm_calls']}", flush=True)
        return response
    save()
    try:
        for case in probes:
            response = invoke(case)
            if case["kind"] == "ambiguous" and response.clarification:
                options = {option.id for option in response.clarification.options}
                for view in (ORDER, DETAIL):
                    if view in options:
                        invoke({**case, "case_id": case["case_id"] + "-" + view.rsplit(".", 1)[-1]},
                               choice=ClarificationChoice(option_id=view, contract_fingerprint=catalog.fingerprint))
        metadata["status"] = "completed"
    except KeyboardInterrupt:
        metadata.update(status="interrupted", failure_type="KeyboardInterrupt")
        raise
    except Exception as exc:
        metadata.update(status="failed", failure_type=type(exc).__name__)
        raise
    finally:
        metadata.update(completed_cases=len(results), passed_cases=sum(row["pass"] for row in results),
                        actual_llm_calls=len(recorder.calls))
        save()
        print(output)


if __name__ == "__main__":
    main()
