"""Offline View retrieval diagnostics; vector mode calls the embedding model."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from collections import Counter
from pathlib import Path

from langchain_core.documents import Document

from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.llm.factory import response_schema_for
from cpea.infrastructure.retrieval.documents import build_documents
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, SchemaRetriever, _lexical_score, _view_lexical_score
from cpea.workflows.text_to_sql.prompt_resources import load_match_prompt
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow, candidate_schema
from evaluations.governance_inputs import load_cases
from evaluations.view_matching_cases import validate_view_case


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


def evaluate_vector(profile: Path, cases_path: Path, env_file: Path) -> dict:
    settings = AssistantSettings.from_env(env_file)
    if settings.retrieval_mode != "vector":
        raise ValueError("profile retrieval mode is not vector")
    catalog = SchemaCatalog(profile, allow_drafts=True)
    retriever = SchemaRetriever(settings, catalog)
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line]
    normal = [case for case in cases if case["category"] == "normal"]
    by_view: dict[str, list[dict]] = defaultdict(list)
    misses: list[dict] = []
    for case in normal:
        vector = retriever._vector_candidates(case["request"])
        reranked = retriever._rerank(case["request"], vector)
        ranks = {}
        for label, candidates in (("vector", vector), ("rerank", reranked)):
            ranks[label] = next((index for index, item in enumerate(candidates, 1)
                                 if item.document.metadata["document_id"] == case["target_view"]), None)
        by_view[case["target_view"]].append(ranks)
        if ranks["rerank"] is None or ranks["rerank"] > settings.rerank_top_k:
            misses.append({"case_id": case["case_id"], "target_view": case["target_view"], **ranks})

    def counts(rows: list[dict]) -> dict:
        return {label: {f"recall_at_{k}": sum(row[label] is not None and row[label] <= k for row in rows)
                        for k in (1, 4, 5)} for label in ("vector", "rerank")}

    return {
        "normal_cases": len(normal),
        "views": len(retriever.documents),
        "retrieval_k": settings.retrieval_k,
        "rerank_top_k": settings.rerank_top_k,
        "embedding_model": settings.embedding_model,
        "stale_contract_fingerprints": sum(case.get("contract_fingerprint") != catalog.fingerprint for case in normal),
        "overall": counts([ranks for rows in by_view.values() for ranks in rows]),
        "by_view": {view: {"cases": len(rows), **counts(rows)} for view, rows in by_view.items()},
        "rerank_top4_misses": misses,
    }


def markdown_vector(result: dict) -> str:
    lines = ["# Retail Vector View 檢索診斷", "",
             "使用目前 Retail 設定；只比較初步 vector 排名與 lexical rerank 排名，不呼叫生成模型或資料庫。", "",
             f"正常題：{result['normal_cases']}；View：{result['views']}；初步候選上限：{result['retrieval_k']}；rerank 輸出上限：{result['rerank_top_k']}。",
             f"Embedding 模型：`{result['embedding_model']}`；契約指紋與目前 YAML 不一致：{result['stale_contract_fingerprints']}。", "",
             "| View | 題數 | vector top-1 | rerank top-1 | vector top-4 | rerank top-4 |",
             "|---|---:|---:|---:|---:|---:|"]
    for view, item in result["by_view"].items():
        vector, rerank = item["vector"], item["rerank"]
        lines.append(f"| `{view}` | {item['cases']} | {vector['recall_at_1']} | {rerank['recall_at_1']} | {vector['recall_at_4']} | {rerank['recall_at_4']} |")
    vector, rerank = result["overall"]["vector"], result["overall"]["rerank"]
    lines.extend([f"| **總計** | **{result['normal_cases']}** | **{vector['recall_at_1']}** | **{rerank['recall_at_1']}** | **{vector['recall_at_4']}** | **{rerank['recall_at_4']}** |",
                  "", "## Rerank 後未進候選的正常題", "",
                  "| 案例 | 目標 View | vector 排名 | rerank 排名 |", "|---|---|---:|---:|"])
    for item in result["rerank_top4_misses"]:
        lines.append(f"| `{item['case_id']}` | `{item['target_view']}` | {item['vector'] or '未召回'} | {item['rerank'] or '未召回'} |")
    return "\n".join(lines) + "\n"


def evaluate_review(profile: Path, cases_path: Path, env_file: Path) -> dict:
    """Measure candidate coverage without changing the production workflow."""
    settings = AssistantSettings.from_env(env_file)
    catalog = SchemaCatalog(profile, allow_drafts=True)
    retriever = SchemaRetriever(settings, catalog)
    packer = ContextPacker(settings)
    prompt = load_match_prompt()
    cases = [json.loads(line) for line in cases_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = []
    for case in cases:
        request = case["request"]
        vector = retriever._vector_candidates(request)
        lexical = retriever._lexical_candidates(request)
        merged = {item.document.metadata["document_id"]: item for item in lexical}
        merged.update({item.document.metadata["document_id"]: item for item in vector})
        rankings = {
            "vector_rerank": retriever._rerank(request, vector),
            "lexical": lexical,
            "hybrid_rerank": retriever._rerank(request, merged.values()),
        }
        expected = set(case["expected_views"])
        strategies = {}
        for name, ranked in rankings.items():
            ranks = {item.document.metadata["document_id"]: index
                     for index, item in enumerate(ranked, 1)}
            coverage = {}
            for k in (4, 5, 7):
                selected = ranked[:k]
                packed = packer.pack_documents(system_prompt=prompt.system, question=request,
                                               history_text="", candidates=selected)
                admitted = {source.document_id for source in packed.sources}
                individually_admitted = {
                    item.document.metadata["document_id"] for item in selected
                    if packer.pack_documents(system_prompt=prompt.system, question=request,
                                             history_text="", candidates=[item]).sources
                }
                coverage[str(k)] = {
                    "ranked": expected <= {item.document.metadata["document_id"] for item in selected},
                    "batch_admitted": expected <= admitted,
                    "individual_admitted": expected <= individually_admitted,
                    "context_tokens": packed.context_tokens,
                    "dropped": packed.dropped_document_ids,
                }
            strategies[name] = {"ranks": {view: ranks.get(view) for view in expected}, "coverage": coverage}
        rows.append({"case_id": case["case_id"], "kind": case["kind"],
                     "expected_views": sorted(expected), "strategies": strategies})
    return {"cases": len(rows), "views": len(retriever.documents), "rows": rows}


def markdown_review(result: dict) -> str:
    lines = ["# Retail View 候選隔離實驗", "",
             "依目前 YAML 核對的明確及歧義問題；只測候選覆蓋與 context budget，不呼叫生成模型或資料庫。", "",
             f"案例：{result['cases']}；View：{result['views']}。", "",
             "| 策略 | top 4 排名涵蓋 | top 5 排名涵蓋 | top 7 排名涵蓋 | top 7 批次 context | top 7 逐 View context |",
             "|---|---:|---:|---:|---:|---:|"]
    for strategy in ("vector_rerank", "lexical", "hybrid_rerank"):
        counts = [sum(row["strategies"][strategy]["coverage"][str(k)]["ranked"] for row in result["rows"])
                  for k in (4, 5, 7)]
        batch_admitted = sum(row["strategies"][strategy]["coverage"]["7"]["batch_admitted"]
                             for row in result["rows"])
        individual_admitted = sum(row["strategies"][strategy]["coverage"]["7"]["individual_admitted"]
                                  for row in result["rows"])
        lines.append(f"| {strategy} | {counts[0]}/{result['cases']} | {counts[1]}/{result['cases']} | "
                     f"{counts[2]}/{result['cases']} | {batch_admitted}/{result['cases']} | "
                     f"{individual_admitted}/{result['cases']} |")
    lines.extend(["", "## 案例", "", "| 案例 | 種類 | 目標 View 排名（vector rerank） |",
                  "|---|---|---|"])
    for row in result["rows"]:
        ranks = row["strategies"]["vector_rerank"]["ranks"]
        lines.append(f"| `{row['case_id']}` | {row['kind']} | "
                     + "、".join(f"`{view}`：{rank or '未召回'}" for view, rank in ranks.items()) + " |")
    return "\n".join(lines) + "\n"


def evaluate_workflow_retrieval(profile: Path, cases_path: Path, env_file: Path) -> dict:
    """Run the production retrieval node for every Retail benchmark case, without an LLM."""
    settings = AssistantSettings.from_env(env_file)
    catalog = SchemaCatalog(profile, allow_drafts=True)
    packer = ContextPacker(settings)
    workflow = SQLGenerationWorkflow(
        object(), catalog, settings=settings,
        retriever=SchemaRetriever(settings, catalog), context_packer=packer)
    schemas = {view.name: candidate_schema(view) for view in catalog.views()}
    prompt = workflow.match_prompt
    rows = []
    full_contract_checks = 0
    full_contract_fit = 0
    for wrapped in load_cases(cases_path).cases:
        case = wrapped.view_matching_case
        if case is None:
            raise ValueError(f"{wrapped.case_id}: expected a View Matching case")
        validate_view_case(case, catalog)
        state = workflow._retrieve_schema({"request": case.request, "history": []})
        ranked = [item.document_id for item in state.get("retrieved_candidates", [])]
        admitted = [item.document.metadata["document_id"] for item in state.get("candidates", [])]
        rank = ranked.index(case.target_view) + 1 if case.target_view in ranked else None
        target_contract_fit = False
        for candidate in state.get("candidates", []):
            view = str(candidate.document.metadata["document_id"])
            schema = schemas[view]
            constrained = response_schema_for(
                prompt.response_model, column_names=set(schema["columns"]), view_names={view})
            detailed = RetrievalCandidate(document=Document(
                id=candidate.document.id, page_content=json.dumps(schema, ensure_ascii=False),
                metadata=candidate.document.metadata),
                retrieval_score=candidate.retrieval_score, reranker_score=candidate.reranker_score)
            extra = (json.dumps({"candidates": [], "response_schema": constrained}, ensure_ascii=False)
                     if prompt.version != "v4" else "")
            packed = packer.pack_documents(system_prompt=prompt.system, question=case.request,
                                           history_text="", candidates=[detailed],
                                           additional_prompt_text=extra)
            fits = bool(packed.sources)
            full_contract_checks += 1
            full_contract_fit += fits
            if view == case.target_view:
                target_contract_fit = fits
        rows.append({"case_id": case.case_id, "category": case.category,
                     "target_view": case.target_view, "request": case.request,
                     "rank": rank, "admitted": case.target_view in admitted,
                     "target_contract_fit": target_contract_fit,
                     "ranked": ranked})

    def counts(subset: list[dict]) -> dict:
        return {"cases": len(subset), "top1": sum(row["rank"] == 1 for row in subset),
                "top4": sum(row["rank"] is not None and row["rank"] <= 4 for row in subset),
                "top5": sum(row["rank"] is not None and row["rank"] <= 5 for row in subset),
                "admitted": sum(row["admitted"] for row in subset),
                "target_contract_fit": sum(row["target_contract_fit"] for row in subset)}

    categories = sorted({row["category"] for row in rows})
    return {"mode": settings.retrieval_mode, "reranker": settings.reranker_provider,
            "candidate_limit": max(5, settings.rerank_top_k),
            "contract_fingerprint": catalog.fingerprint,
            "full_contract_checks": full_contract_checks,
            "full_contract_fit": full_contract_fit,
            "summary": {"all": counts(rows), **{category: counts([
                row for row in rows if row["category"] == category]) for category in categories}},
            "misses": [row for row in rows if not row["admitted"]]}


def markdown_workflow_retrieval(result: dict) -> str:
    lines = ["# Retail 395 題 View 篩選測試", "",
             "使用正式流程的 `retrieve_schema` 節點與目前專案設定，並模擬後續單一 View 的完整契約打包；不呼叫 SQL 生成模型或資料庫。",
             "`target_view` 對拒絕類題目只代表題目所屬 View，不代表應產生 SQL。", "",
             f"檢索：`{result['mode']}`；reranker：`{result['reranker']}`；"
             f"候選上限：{result['candidate_limit']}；契約指紋：`{result['contract_fingerprint']}`。", "",
             f"完整契約可容納：{result['full_contract_fit']}/{result['full_contract_checks']} 次候選打包。", "",
             "| 題目類別 | 題數 | top 1 | top 4 | top 5 | 檢索摘要可容納 | 完整契約可容納 |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for category, values in result["summary"].items():
        lines.append(f"| {category} | {values['cases']} | {values['top1']} | "
                     f"{values['top4']} | {values['top5']} | {values['admitted']} | "
                     f"{values['target_contract_fit']} |")
    lines.extend(["", "## 未進入候選的題目", ""])
    for row in result["misses"]:
        lines.extend([f"### {row['case_id']}", "", f"- 類別：`{row['category']}`",
                      f"- 目標 View：`{row['target_view']}`",
                      f"- 問題：{row['request']}",
                      "- 前五名：" + "、".join(f"`{name}`" for name in row["ranked"]), ""])
    if not result["misses"]:
        lines.append("無。")
    lines.extend(["", "此結果只量測候選召回與 context 容量；不表示模型最後會選對 View、拒絕不支援需求或產生正確 SQL。", ""])
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=Path("projects/retail"))
    parser.add_argument("--cases", type=Path, default=Path("projects/retail/evaluations/cases.jsonl"))
    parser.add_argument("--mode", choices=("lexical", "vector", "review", "workflow-retrieval"), default="lexical")
    parser.add_argument("--env-file", type=Path, default=Path("projects/retail/.env"))
    parser.add_argument("--run-results", type=Path, help="既有流程執行結果 JSONL；用於失敗階段分類")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.mode == "workflow-retrieval":
        result = evaluate_workflow_retrieval(args.profile, args.cases, args.env_file)
        report = markdown_workflow_retrieval(result)
        output = result
    elif args.mode == "review":
        review_cases = args.cases if args.cases != Path("projects/retail/evaluations/cases.jsonl") else Path(
            "evaluations/data/retail_view_retrieval_review.jsonl")
        result = evaluate_review(args.profile, review_cases, args.env_file)
        report = markdown_review(result)
        output = {key: result[key] for key in ("cases", "views", "rows")}
    elif args.mode == "vector":
        result = evaluate_vector(args.profile, args.cases, args.env_file)
        report = markdown_vector(result)
        output = {key: result[key] for key in ("overall", "views", "retrieval_k", "rerank_top_k")}
    else:
        result = evaluate(args.profile, args.cases, args.run_results)
        report = markdown(result)
        output = {key: result[key] for key in ("overall", "workflow_outcomes") if key in result}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    if args.report:
        args.report.write_text(report, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
