"""Offline View retrieval diagnostics; no model or database calls."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections import Counter
from pathlib import Path

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.retrieval.documents import build_documents
from cpea.infrastructure.retrieval.schema import _lexical_score, _view_lexical_score


def evaluate(profile: Path, cases_path: Path, run_results_path: Path | None = None) -> dict:
    catalog = SchemaCatalog(profile, allow_drafts=True)
    documents = build_documents(catalog)
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line]
    normal = [case for case in cases if case["category"] == "normal"]
    by_view: dict[str, list[dict]] = defaultdict(list)
    misses: list[dict] = []
    for case in normal:
        ranks = {}
        for label, scorer in (("baseline", _lexical_score), ("current", _view_lexical_score)):
            ordered = sorted(documents, key=lambda document: scorer(case["request"], document), reverse=True)
            ranks[label] = next(index for index, document in enumerate(ordered, 1)
                                if document.metadata["document_id"] == case["target_view"])
        by_view[case["target_view"]].append(ranks)
        if ranks["current"] > 4:
            misses.append({"case_id": case["case_id"], "target_view": case["target_view"], **ranks})

    def counts(rows: list[dict]) -> dict:
        return {label: {f"recall_at_{k}": sum(row[label] <= k for row in rows)
                        for k in (1, 4, 5)} for label in ("baseline", "current")}

    all_ranks = [ranks for rows in by_view.values() for ranks in rows]
    result = {
        "normal_cases": len(normal),
        "stale_contract_fingerprints": sum(case.get("contract_fingerprint") != catalog.fingerprint for case in normal),
        "overall": counts(all_ranks),
        "by_view": {view: {"cases": len(rows), **counts(rows)} for view, rows in by_view.items()},
        "current_top4_misses": misses,
    }
    if run_results_path:
        targets = {case["case_id"]: case["target_view"] for case in cases}
        outcomes = Counter()
        for line in run_results_path.read_text(encoding="utf-8").splitlines():
            run = json.loads(line)
            if run.get("mapping_grade") == run.get("sql_grade") == "pass":
                outcomes["pass"] += 1
                continue
            target = targets.get(run.get("case_id"))
            generation = run.get("generation") or {}
            retrieved = generation.get("retrieved_candidates") or run.get("retrieved_candidates") or []
            candidates = {item["document_id"] for item in retrieved}
            if target and candidates and target not in candidates:
                outcomes["retrieval_miss"] += 1
            elif target and candidates and target not in run.get("selected_views", []):
                outcomes["selection_miss"] += 1
            elif target and candidates:
                outcomes["mapping_or_sql_mismatch"] += 1
            else:
                outcomes["unclassified"] += 1
        result["workflow_outcomes"] = dict(outcomes)
    return result


def markdown(result: dict) -> str:
    lines = ["# Retail View 檢索診斷", "",
             "只評估正常題的正確 View 排名；不呼叫模型、不驗證最終 SQL。", "",
             f"正常題：{result['normal_cases']}；契約指紋與目前 YAML 不一致：{result['stale_contract_fingerprints']}。",
             "指紋差異不影響此處的排名計算，但題庫正式評分前仍需重新審核。", "",
             "| View | 題數 | 原本 top-1 | 目前 top-1 | 原本 top-4 | 目前 top-4 |",
             "|---|---:|---:|---:|---:|---:|"]
    for view, item in result["by_view"].items():
        old, new = item["baseline"], item["current"]
        lines.append(f"| `{view}` | {item['cases']} | {old['recall_at_1']} | {new['recall_at_1']} | {old['recall_at_4']} | {new['recall_at_4']} |")
    old, new = result["overall"]["baseline"], result["overall"]["current"]
    lines.extend([f"| **總計** | **{result['normal_cases']}** | **{old['recall_at_1']}** | **{new['recall_at_1']}** | **{old['recall_at_4']}** | **{new['recall_at_4']}** |",
                  "", "## 目前未進 top-4 的正常題", "",
                  "| 案例 | 目標 View | 原本排名 | 目前排名 |", "|---|---|---:|---:|"])
    for item in result["current_top4_misses"]:
        lines.append(f"| `{item['case_id']}` | `{item['target_view']}` | {item['baseline']} | {item['current']} |")
    if "workflow_outcomes" in result:
        lines.extend(["", "## 流程執行結果分類", "",
                      "依指定的既有執行紀錄分類；與上述離線排名分開統計。", "",
                      "| 分類 | 次數 |", "|---|---:|"])
        for name, count in result["workflow_outcomes"].items():
            lines.append(f"| `{name}` | {count} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("projects/retail"))
    parser.add_argument("--cases", type=Path, default=Path("projects/retail/evaluations/cases.jsonl"))
    parser.add_argument("--run-results", type=Path, help="既有流程執行結果 JSONL；用於失敗階段分類")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = evaluate(args.profile, args.cases, args.run_results)
    print(json.dumps({key: result[key] for key in ("overall", "workflow_outcomes") if key in result},
                     ensure_ascii=False, indent=2))
    if args.report:
        args.report.write_text(markdown(result), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
