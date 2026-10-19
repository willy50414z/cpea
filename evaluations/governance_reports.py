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


def model_metrics(records: list[dict], calls: list[dict], runs: int) -> dict:
    counts = _totals(records)
    completed = counts["pass"] + counts["fail"]
    groups = defaultdict(list)
    for record in records:
        groups[record["case_id"]].append(record)
    repeated = [items for items in groups.values()
                if runs >= 2 and len(items) == runs
                and len({item["repetition"] for item in items}) == runs
                and all(item["status"] in {"pass", "fail"} for item in items)]
    valid = [items for items in repeated if all(item.get("generation") for item in items)]
    def signature(item):
        generation = item["generation"]
        return json.dumps({key: generation.get(key) for key in
                           ("supported", "selected_views", "query_plan", "sql")},
                          ensure_ascii=False, sort_keys=True)
    def token_total(field):
        return sum(call[field] for call in calls) if calls and all(call.get(field) is not None for call in calls) else None
    return {
        "total": len(records), "completed": len(records) - counts["skipped"],
        "pass": counts["pass"], "fail": counts["fail"],
        "error": counts["error"], "pending": counts["pending"], "skipped": counts["skipped"],
        "mapping_pass": sum(r.get("mapping_status") == "pass" for r in records),
        "sql_pass": sum(r.get("sql_status") == "pass" for r in records),
        "pass_rate_total": round(counts["pass"] / len(records), 4) if records else None,
        "pass_rate_completed": round(counts["pass"] / completed, 4) if completed else None,
        "error_rate_total": round(counts["error"] / len(records), 4) if records else None,
        "elapsed_p50_ms": _percentile([r["elapsed_ms"] for r in records], .5),
        "elapsed_p95_ms": _percentile([r["elapsed_ms"] for r in records], .95),
        "elapsed_total_ms": round(sum(r["elapsed_ms"] for r in records), 3),
        "llm_calls": len(calls), "llm_total_ms": round(sum(c["elapsed_ms"] for c in calls), 3),
        "input_tokens": token_total("input_tokens"), "output_tokens": token_total("output_tokens"),
        "usage_complete_calls": sum(c.get("input_tokens") is not None and c.get("output_tokens") is not None for c in calls),
        "complete_repeated_cases": len(repeated),
        "all_pass_cases": sum(all(r["status"] == "pass" for r in items) for items in repeated),
        "all_pass_rate": round(sum(all(r["status"] == "pass" for r in items) for items in repeated) / len(repeated), 4) if repeated else None,
        "status_consistent_cases": sum(len({r["status"] for r in items}) == 1 for items in repeated),
        "generation_comparable_cases": len(valid),
        "generation_consistent_cases": sum(len({signature(r) for r in items}) == 1 for items in valid),
    }


def write_reports(run_dir: Path, results: list[dict], calls: list[dict]) -> None:
    run_dir = Path(run_dir)
    hilp = [r for r in results if r.get('hilp_phases')]
    if hilp:
        grouped = defaultdict(list)
        for row in hilp:
            grouped[(row['provider'], row['model'], row['case_id'])].append(row)
        summary = {'completed_repetitions': len(hilp),
                   'semantic_false_accepts': sum('semantic_false_accept' in r['failure_reasons'] for r in hilp),
                   'unnecessary_confirmations': sum('unnecessary_confirmation' in r['failure_reasons'] for r in hilp),
                   'script_or_sql_failures': sum(bool(r['failure_reasons']) for r in hilp),
                   'cases_with_at_least_three_repetitions': sum(len(rows) >= 3 for rows in grouped.values()),
                   'cases_stable_and_passing_three_repetitions': sum(len(rows) >= 3 and all(r['status'] == 'pass' for r in rows)
                                                                      for rows in grouped.values())}
        (run_dir / 'hilp_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    by_key = defaultdict(list)
    for call in calls:
        by_key[(call["case_id"], call["model"], call["repetition"])].append(call)
    def usage(record, field):
        matched = by_key[(record["case_id"], record["model"], record["repetition"])]
        return sum(call[field] for call in matched) if matched and all(call[field] is not None for call in matched) else None
    with (run_dir / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["run_id", "case_id", "category", "difficulty",
                                                    "provider", "model", "repetition", "status",
                                                    "review_state", "target_view", "sql_difficulty", "semantic_difficulty",
                                                    "mapping_status", "sql_status", "failure_reasons", "llm_calls",
                                                    "input_tokens", "output_tokens", "llm_ms", "elapsed_ms"])
        writer.writeheader()
        for record in results:
            matched = by_key[(record["case_id"], record["model"], record["repetition"])]
            writer.writerow({
                **{field: record.get(field) for field in ("run_id", "case_id", "category", "difficulty",
                     "provider", "model", "repetition", "status", "review_state", "target_view",
                     "sql_difficulty", "semantic_difficulty", "mapping_status", "sql_status", "elapsed_ms")},
                "failure_reasons": _reason_codes(record),
                "llm_calls": len(matched),
                "input_tokens": usage(record, "input_tokens") if usage(record, "input_tokens") is not None else "",
                "output_tokens": usage(record, "output_tokens") if usage(record, "output_tokens") is not None else "",
                "llm_ms": round(sum(c["elapsed_ms"] for c in matched), 3),
            })
    per_model = defaultdict(list)
    for record in results:
        per_model[(record["provider"], record["model"])].append(record)
    metadata_path = run_dir / "run.json"
    runs = json.loads(metadata_path.read_text(encoding="utf-8")).get("runs", 0) if metadata_path.exists() else 0
    with (run_dir / "model_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["provider", "model", *model_metrics(results, calls, runs)]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for (provider, model), records in sorted(per_model.items()):
            matched = [c for c in calls if (c["provider"], c["model"]) == (provider, model)]
            writer.writerow({"provider": provider, "model": model, **model_metrics(records, matched, runs)})
    per_category = defaultdict(list)
    for record in results:
        per_category[(record["category"], record["provider"], record["model"])].append(record)
    with (run_dir / "category_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["category", "provider", "model", *model_metrics(results, calls, runs)]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for (category, provider, model), records in sorted(per_category.items()):
            case_ids = {record["case_id"] for record in records}
            matched = [call for call in calls if call["case_id"] in case_ids
                       and call["provider"] == provider and call["model"] == model]
            writer.writerow({"category": category, "provider": provider, "model": model,
                             **model_metrics(records, matched, runs)})
    per_grid = defaultdict(list)
    for record in results:
        if record.get("target_view"):
            per_grid[(record["target_view"], record.get("sql_difficulty"),
                      record.get("semantic_difficulty"), record["category"],
                      record["provider"], record["model"])].append(record)
    with (run_dir / "view_grid_summary.csv").open("w", encoding="utf-8", newline="") as stream:
        fields = ["target_view", "sql_difficulty", "semantic_difficulty", "category",
                  "provider", "model", *model_metrics(results, calls, runs)]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for key, records in sorted(per_grid.items(), key=lambda item: str(item[0])):
            ids = {record["case_id"] for record in records}
            matched = [call for call in calls if call["case_id"] in ids and
                       (call["provider"], call["model"]) == key[-2:]]
            writer.writerow({**dict(zip(fields[:6], key)), **model_metrics(records, matched, runs)})
    totals = _totals(results)
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    planned = metadata.get("planned_total", len(results))
    overview = ["# 模型治理評估", "", f"執行：`{run_dir.name}`", "",
                f"預定：{planned}；已完成：{len(results) - totals['skipped']}；略過：{totals['skipped']}；未記錄：{max(0, planned - len(results))}；通過：{totals['pass']}；失敗：{totals['fail']}；錯誤：{totals['error']}；待審：{totals['pending']}。",
                "", "pass_rate_total 以所有已執行次數為分母；pass_rate_completed 僅計通過與失敗，錯誤與待審另列。未完成題目不視為通過。",
                "", "各模型、分類與 View 九宮格的通過率、token、耗時見 `model_summary.csv`、`category_summary.csv`、`view_grid_summary.csv`。缺少 provider 用量時保留空值。"]
    if runs >= 2:
        overview.append("完整重複題目的穩定性也見上述 CSV；一致失敗不代表正確。")
    else:
        overview.append("本次每題僅執行一次，不提供重複執行穩定性結論。")
    overview.extend(["", "| 分類 | 模型 | 已執行 | 通過 | 失敗 | 錯誤 |",
                     "|---|---|---:|---:|---:|---:|"])
    for (category, _provider, model), records in sorted(per_category.items()):
        counts = _totals(records)
        overview.append(f"| {_safe(category)} | {_safe(model)} | {len(records)} | {counts['pass']} | {counts['fail']} | {counts['error']} |")
    overview.extend(["", "| 案例 | 分類 | 模型 | 次數 | 狀態 | 原因 |", "|---|---|---|---:|---|---|"])
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
        lines = [f"# {case_id}", "", f"分類：`{first['category']}`；難度：`{first['difficulty']}`。", "",
                 "預期檢查種類：" + ", ".join(checks), "",
                 "| 模型 | 次數 | 狀態 | 耗時 ms | 輸入 token | 輸出 token | 原因 | 呼叫 ID |",
                 "|---|---:|---|---:|---:|---:|---|---|"]
        for record in records:
            input_tokens = usage(record, "input_tokens")
            output_tokens = usage(record, "output_tokens")
            lines.append(f"| {_safe(record['model'])} | {record['repetition']} | {_safe(record['status'] or 'pending')} | {record['elapsed_ms']:.3f} | {input_tokens if input_tokens is not None else '—'} | {output_tokens if output_tokens is not None else '—'} | {_safe(_reason_codes(record))} | {_safe(', '.join(record['call_ids']))} |")
        lines.extend(["", "原始請求、回覆、SQL 與資料列保存在私有 JSONL 產物中。"])
        (case_dir / f"{case_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def regenerate(run_dir: Path) -> None:
    run_dir = Path(run_dir)
    def read(name):
        return [json.loads(line) for line in (run_dir / name).read_text(encoding="utf-8").splitlines() if line.strip()]
    write_reports(run_dir, read("results.jsonl"), read("calls.jsonl"))
