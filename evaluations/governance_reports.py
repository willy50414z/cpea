"""Regenerate shareable summaries from private JSONL run records."""
from __future__ import annotations

from collections import Counter, defaultdict
import csv
import json
from pathlib import Path


def _safe(value: object) -> str:
    # Reports use only enumerated summary fields, never raw request/response.
    text = str(value if value is not None else "")
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", " ")


def _reason_codes(record: dict) -> str:
    if record["status"] == "error":
        return "evaluation_error"
    return "; ".join(str(reason).split(":", 1)[0] for reason in record["failure_reasons"])


def _totals(results: list[dict]) -> Counter:
    return Counter(record["status"] if record["status"] is not None else "pending" for record in results)


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return round(ordered[low] + (ordered[high] - ordered[low]) * (position - low), 3)


def write_reports(run_dir: Path, results: list[dict], calls: list[dict]) -> None:
    run_dir = Path(run_dir)
    by_key = defaultdict(list)
    for call in calls:
        by_key[(call["case_id"], call["model"], call["repetition"])].append(call)
    def usage(record, field):
        matched = by_key[(record["case_id"], record["model"], record["repetition"])]
        return sum(call[field] for call in matched) if matched and all(call[field] is not None for call in matched) else None
    with (run_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["run_id", "case_id", "category", "difficulty",
                                                    "provider", "model", "repetition", "status",
                                                    "review_state", "failure_reasons", "llm_calls",
                                                    "input_tokens", "output_tokens", "llm_ms", "elapsed_ms"])
        writer.writeheader()
        for record in results:
            matched = by_key[(record["case_id"], record["model"], record["repetition"])]
            writer.writerow({
                **{field: record.get(field) for field in ("run_id", "case_id", "category", "difficulty",
                     "provider", "model", "repetition", "status", "review_state", "elapsed_ms")},
                "failure_reasons": _reason_codes(record),
                "llm_calls": len(matched),
                "input_tokens": usage(record, "input_tokens") if usage(record, "input_tokens") is not None else "",
                "output_tokens": usage(record, "output_tokens") if usage(record, "output_tokens") is not None else "",
                "llm_ms": round(sum(c["elapsed_ms"] for c in matched), 3),
            })
    per_model = defaultdict(list)
    for record in results:
        per_model[(record["provider"], record["model"])].append(record)
    with (run_dir / "model_summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["provider", "model", "total", "pass", "fail", "error", "pending",
                         "pass_rate_completed", "error_rate_total", "elapsed_p50_ms", "elapsed_p95_ms"])
        for (provider, model), records in sorted(per_model.items()):
            counts = _totals(records)
            completed = counts["pass"] + counts["fail"]
            durations = [record["elapsed_ms"] for record in records]
            writer.writerow([provider, model, len(records), counts["pass"], counts["fail"], counts["error"],
                             counts["pending"], round(counts["pass"] / completed, 4) if completed else "",
                             round(counts["error"] / len(records), 4), _percentile(durations, .5),
                             _percentile(durations, .95)])
    totals = _totals(results)
    overview = ["# Model governance evaluation", "", f"Run: `{run_dir.name}`", "",
                f"Total: {len(results)}; pass: {totals['pass']}; fail: {totals['fail']}; error: {totals['error']}; pending review: {totals['pending']}.",
                "", "Rates use all repetitions as the denominator; errors and pending reviews are separate from completed incorrect responses.",
                "", "Model-level rates and latency percentiles are in `model_summary.csv`.",
                "", "| Case | Category | Model | Run | Status | Reason |", "|---|---|---|---:|---|---|"]
    for record in results:
        case_id = record["case_id"]
        overview.append(f"| [{case_id}](cases/{case_id}.md) | {_safe(record['category'])} | {_safe(record['model'])} | {record['repetition']} | {_safe(record['status'] or 'pending')} | {_safe(_reason_codes(record))} |")
    (run_dir / "overview.md").write_text("\n".join(overview) + "\n", encoding="utf-8")
    case_dir = run_dir / "cases"
    case_dir.mkdir(exist_ok=True)
    grouped = defaultdict(list)
    for record in results:
        grouped[record["case_id"]].append(record)
    for case_id, records in grouped.items():
        first = records[0]
        checks = [key for key, value in first["expected_result"].items()
                  if (key == "supported" and value is not None) or (key != "supported" and value)]
        lines = [f"# {case_id}", "", f"Category: `{first['category']}`; difficulty: `{first['difficulty']}`.", "",
                 "Expected check types: " + ", ".join(checks), "",
                 "| Model | Run | Status | Elapsed ms | Input tokens | Output tokens | Reason | LLM call IDs |",
                 "|---|---:|---|---:|---:|---:|---|---|"]
        for record in records:
            input_tokens = usage(record, "input_tokens")
            output_tokens = usage(record, "output_tokens")
            lines.append(f"| {_safe(record['model'])} | {record['repetition']} | {_safe(record['status'] or 'pending')} | {record['elapsed_ms']:.3f} | {input_tokens if input_tokens is not None else '—'} | {output_tokens if output_tokens is not None else '—'} | {_safe(_reason_codes(record))} | {_safe(', '.join(record['call_ids']))} |")
        lines.extend(["", "Raw requests, responses, SQL, and result rows remain in the private JSONL artifacts."])
        (case_dir / f"{case_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def regenerate(run_dir: Path) -> None:
    run_dir = Path(run_dir)
    def read(name):
        return [json.loads(line) for line in (run_dir / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    write_reports(run_dir, read("results.jsonl"), read("calls.jsonl"))
