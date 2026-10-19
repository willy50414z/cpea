"""Versioned retrieval-only experiments using the production retrieval node."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import math
from pathlib import Path
import subprocess
from time import perf_counter

from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.llm.context_budget import ContextPacker
from cpea.infrastructure.retrieval.schema import SchemaRetriever
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from evaluations.governance_inputs import load_cases
from evaluations.view_matching_cases import validate_view_case


ROOT = Path(__file__).resolve().parents[1]
CHALLENGE = ROOT / "evaluations/data/retail_retrieval_challenge.jsonl"
CATEGORIES = ("exact_match", "synonym", "colloquial", "ambiguous", "multi_concept")
REVIEW_KEYS = {"review_status", "reviewer", "reviewed_at", "reviewed_case_sha256",
               "reviewed_contract_fingerprint"}


def fingerprint(value) -> str:
    return sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def challenge_content_sha256(case: dict) -> str:
    return fingerprint({key: value for key, value in case.items() if key not in REVIEW_KEYS})


def load_challenge(path: Path, catalog) -> list[dict]:
    cases = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len({case["case_id"] for case in cases}) != len(cases):
        raise ValueError("challenge case_id must be unique")
    known = {view.name for view in catalog.views()}
    for case in cases:
        if case["contract_fingerprint"] != catalog.fingerprint:
            raise ValueError(f"{case['case_id']}: stale challenge contract fingerprint")
        gold, valid = set(case["gold_views"]), set(case["valid_views"])
        if not gold <= valid <= known or case["category"] not in CATEGORIES:
            raise ValueError(f"{case['case_id']}: invalid challenge labels")
        groups = case["interpretations"]
        if any(not group["views"] or not group["description"] for group in groups):
            raise ValueError("interpretations require views and business semantics")
        if set().union(*(set(group["views"]) for group in groups)) != valid:
            raise ValueError("interpretations must cover exactly the valid views")
        if case["requires_clarification"] != (len(groups) > 1):
            raise ValueError("clarification labels must reflect distinct business interpretations")
        if not valid and not case["unsupported_requirements"]:
            raise ValueError("unsupported cases require contract evidence")
        if set(case["required_columns"]) != valid:
            raise ValueError("required columns must be labeled for every valid view")
        for view, columns in case["required_columns"].items():
            if not columns or not set(columns) <= set(catalog.columns(view)):
                raise ValueError(f"{case['case_id']}: required column outside contract")
        status = case["review_status"]
        if status not in {"pending", "approved", "rejected"}:
            raise ValueError("invalid review status")
        if status == "approved" and not (
            case.get("reviewer") and case.get("reviewed_at")
            and case.get("reviewed_case_sha256") == challenge_content_sha256(case)
            and case.get("reviewed_contract_fingerprint") == catalog.fingerprint
        ):
            raise ValueError("stale or incomplete human approval")
    return cases


def evaluation_cases(regression: Path, challenge: Path, catalog, *, exploratory: bool) -> list[dict]:
    rows = []
    for wrapped in load_cases(regression).cases:
        case = wrapped.view_matching_case
        if case is None:
            raise ValueError("expected View Matching regression cases")
        validate_view_case(case, catalog)
        rows.append({"case_id": case.case_id, "request": case.request,
                     "dataset": "regression", "category": case.category,
                     "gold_views": [case.target_view], "valid_views": None,
                     "interpretations": None, "requires_clarification": None,
                     "review_status": case.review_status,
                     "approved": case.approved_for(catalog.fingerprint)})
    for case in load_challenge(challenge, catalog):
        rows.append({**case, "dataset": "challenge", "approved": case["review_status"] == "approved"})
    if len({case["case_id"] for case in rows}) != len(rows):
        raise ValueError("case_id must be unique across datasets")
    if not exploratory and any(not case["approved"] for case in rows):
        raise ValueError("human review is pending; use --exploratory for non-acceptance diagnostics")
    if any(case["review_status"] == "rejected" for case in rows):
        raise ValueError("rejected cases cannot be benchmarked")
    return rows


class RecordingRetriever(SchemaRetriever):
    """Observe full rankings before the production selector truncates them."""

    def _rerank(self, query, candidates):
        self.raw = list(candidates)
        self.ranked = super()._rerank(query, self.raw)
        return self.ranked


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(len(ordered) * fraction) - 1)]


def summarize(rows: list[dict]) -> dict:
    gold_count = sum(len(row["gold_views"]) for row in rows)
    valid_count = sum(len(row["valid_views"] or []) for row in rows)
    ambiguity = [row for row in rows if row["requires_clarification"]]
    def recall(key, cutoff=None):
        hits = 0
        for row in rows:
            views = row[key] if cutoff is None else [item["view"] for item in row[key][:cutoff]]
            hits += len(set(row["gold_views"]) & set(views))
        return hits / gold_count if gold_count else None
    return {
        "cases": len(rows), "gold_view_count": gold_count,
        **{f"gold_recall_at_{k}": recall("retrieved_views", k) for k in (1, 3, 5)},
        "gold_selected_recall": recall("selected_views"),
        "gold_selected_hits": sum(len(set(row["gold_views"]) & set(row["selected_views"])) for row in rows),
        "valid_view_count": valid_count,
        "valid_view_recall": (sum(len(set(row["valid_views"] or []) & set(row["selected_views"]))
                                  for row in rows) / valid_count if valid_count else None),
        "ambiguity_cases": len(ambiguity),
        "ambiguity_coverage": (sum(row["interpretation_coverage"] for row in ambiguity) / len(ambiguity)
                               if ambiguity else None),
        "ambiguity_complete_cases": sum(row["interpretation_coverage"] == 1 for row in ambiguity),
        "clarification_precision": None, "clarification_recall": None, "sql_correctness": None,
        "avg_candidate_count": sum(len(row["selected_views"]) for row in rows) / len(rows) if rows else None,
        "extra_candidate_count": sum(row["extra_candidate_count"] for row in rows),
        "avg_llm_calls": 0,
        "retrieval_latency_p50_ms": percentile([row["retrieval_latency_ms"] for row in rows], .5),
        "retrieval_latency_p95_ms": percentile([row["retrieval_latency_ms"] for row in rows], .95),
        "end_to_end_latency_p50_ms": None, "end_to_end_latency_p95_ms": None,
    }


def measure(cases, settings, catalog, strategy, metadata, output: Path) -> list[dict]:
    # Retrieve every catalog entry for diagnostics; never silently hide rank 6+.
    if settings.retrieval_k < len(catalog.views()):
        raise ValueError("baseline requires retrieval_k >= catalog size to record every View")
    configured = replace(settings, retrieval_mode=strategy,
                         reranker_enabled=settings.reranker_enabled if strategy == "lexical" else False)
    retriever = RecordingRetriever(configured, catalog)
    packer = ContextPacker(configured)
    workflow = SQLGenerationWorkflow(object(), catalog, settings=configured,
                                     retriever=retriever, context_packer=packer)
    top_k = max(5, configured.rerank_top_k)
    index_ready_ms = None
    if strategy == "vector":
        started = perf_counter()
        # This index is rebuilt from this catalog, using one embedding model for
        # both documents and queries. Index build is reported separately.
        retriever.vector_store
        index_ready_ms = (perf_counter() - started) * 1000
    rows = []
    with (output / f"{strategy}.jsonl").open("x", encoding="utf-8") as stream:
        for case in cases:
            state = workflow._retrieve_schema({"request": case["request"], "history": []})
            ranked = retriever.ranked
            selected = [item.document.metadata["document_id"] for item in state.get("candidates", [])]
            offered = [item.document_id for item in state.get("retrieved_candidates", [])]
            if len(ranked) != len(catalog.views()):
                raise ValueError("retriever did not return the full catalog")
            groups = case["interpretations"]
            coverage = (sum(bool(set(group["views"]) & set(selected)) for group in groups) / len(groups)
                        if groups else None)
            raw_ranks = {item.document.metadata["document_id"]: index
                         for index, item in enumerate(retriever.raw, 1)}
            row = {
                "experiment_id": metadata["experiment_id"], "git_sha": metadata["git_sha"],
                "dataset_version": metadata["dataset_versions"][case["dataset"]],
                "contract_version": catalog.contract_version, "contract_fingerprint": catalog.fingerprint,
                "strategy": strategy, "top_k": top_k, "question_id": case["case_id"],
                "request": case["request"], "dataset": case["dataset"], "category": case["category"],
                "review_status": case["review_status"], "gold_views": case["gold_views"],
                "valid_views": case["valid_views"], "requires_clarification": case["requires_clarification"],
                "interpretations": groups, "interpretation_coverage": coverage,
                "retrieved_views": [{"view": item.document.metadata["document_id"], "rank": rank,
                    "raw_rank": raw_ranks[item.document.metadata["document_id"]],
                    "retrieval_score": item.retrieval_score, "reranker_score": item.reranker_score,
                    "source": strategy} for rank, item in enumerate(ranked, 1)],
                "offered_views": offered, "selected_views": selected,
                "selection_reasons": [{"view": view, "reason": "within_top_k" if view in [
                    item.document.metadata["document_id"] for item in ranked[:top_k]] else "cutoff_tie"}
                    for view in offered],
                "extra_candidate_count": max(0, len(offered) - top_k),
                "context_dropped_views": [view for view in offered if view not in selected],
                "retrieval_latency_ms": state.get("retrieval_latency_ms", 0) + state.get("reranker_latency_ms", 0),
                "llm_calls": 0, "tokens_in": 0, "tokens_out": 0,
                "sql_correct": None, "sql_validation": None,
            }
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
            stream.flush()
            rows.append(row)
    metadata["strategies"][strategy] = {
        "reranker_enabled": configured.reranker_enabled,
        "reranker_provider": configured.reranker_provider if configured.reranker_enabled else "none",
        "index_build_latency_ms": index_ready_ms,
        "index_version": fingerprint({"documents": metadata["catalog_documents_sha256"],
                                      "embedding": metadata.get("embedding")}) if strategy == "vector" else None,
    }
    return rows


def comparison(rows_by_strategy: dict[str, list[dict]]) -> dict:
    if not {"lexical", "vector"} <= rows_by_strategy.keys():
        return {}
    by_strategy = {name: {row["question_id"]: row for row in rows}
                   for name, rows in rows_by_strategy.items()}
    differences = {"lexical_only": [], "vector_only": [], "both_miss": []}
    for question, lexical in by_strategy["lexical"].items():
        vector = by_strategy["vector"][question]
        for gold in lexical["gold_views"]:
            left, right = gold in lexical["selected_views"], gold in vector["selected_views"]
            key = "lexical_only" if left and not right else "vector_only" if right and not left else "both_miss"
            if not (left and right):
                differences[key].append({"question_id": question, "view": gold})
    return differences


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", type=Path, default=ROOT / "projects/retail")
    parser.add_argument("--cases", type=Path, default=ROOT / "projects/retail/evaluations/cases.jsonl")
    parser.add_argument("--challenge", type=Path, default=CHALLENGE)
    parser.add_argument("--env-file", type=Path, default=ROOT / "projects/retail/.env")
    parser.add_argument("--strategies", nargs="+", choices=("lexical", "vector"), default=["lexical", "vector"])
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--exploratory", action="store_true")
    args = parser.parse_args()
    def git(*values):
        return subprocess.check_output(["git", *values], cwd=ROOT, text=True, encoding="utf-8").strip()
    if git("status", "--porcelain", "--untracked-files=all"):
        raise ValueError("retrieval benchmark requires a clean Git worktree")
    sha = git("rev-parse", "HEAD")
    catalog = SchemaCatalog(args.profile, allow_drafts=True)
    cases = evaluation_cases(args.cases, args.challenge, catalog, exploratory=args.exploratory)
    settings = AssistantSettings.from_env(args.env_file)
    if not settings.integration_path or Path(settings.integration_path).resolve() != args.profile.resolve():
        raise ValueError("environment profile differs from benchmark profile")
    from cpea.infrastructure.retrieval.documents import build_documents
    documents = build_documents(catalog)
    metadata = {
        "experiment_id": args.experiment_id, "git_sha": sha, "worktree_clean": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_status": "exploratory" if args.exploratory else "reviewed",
        "review_counts": dict(Counter(case["review_status"] for case in cases)),
        "dataset_versions": {"regression": sha256(args.cases.read_bytes()).hexdigest(),
                             "challenge": sha256(args.challenge.read_bytes()).hexdigest()},
        "contract_version": catalog.contract_version, "contract_fingerprint": catalog.fingerprint,
        "catalog_documents_sha256": fingerprint([{"id": doc.metadata["document_id"], "text": doc.page_content}
                                                   for doc in documents]),
        "retrieval_k": settings.retrieval_k, "top_k": max(5, settings.rerank_top_k),
        "embedding": {"provider": settings.embedding_provider, "model": settings.embedding_model,
                      "model_digest": None},
        "strategies": {}, "status": "running",
        "limitations": ["Retrieval only; SQL, clarification decisions and end-to-end cost are unmeasured.",
                        "Regression target_view for rejection cases is nominal; valid views are unlabeled.",
                        "Pure vector disables lexical reranking to isolate retrieval strategy."],
    }
    # Ollama tags bind a mutable model alias to the installed model weights.
    if "vector" in args.strategies and settings.embedding_provider == "ollama":
        import requests
        response = requests.get(settings.embedding_base_url.rstrip("/") + "/api/tags", timeout=10)
        response.raise_for_status()
        model = settings.embedding_model
        matches = [item for item in response.json()["models"]
                   if item["name"] in {model, model if ":" in model else model + ":latest"}]
        if len(matches) != 1 or not matches[0].get("digest"):
            raise ValueError("cannot verify embedding model digest")
        metadata["embedding"]["model_digest"] = matches[0]["digest"]
    output = args.profile / "artifacts/retrieval" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + sha[:8])
    output.mkdir(parents=True, exist_ok=False)
    def save():
        (output / "run.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save()
    rows_by_strategy = {}
    try:
        for strategy in dict.fromkeys(args.strategies):
            print(f"{strategy}: {len(cases)} cases", flush=True)
            rows_by_strategy[strategy] = measure(cases, settings, catalog, strategy, metadata, output)
        metadata["status"] = "completed"
    except Exception as exc:
        metadata["status"] = "failed"
        metadata["failure_type"] = type(exc).__name__
        raise
    finally:
        metadata["summary"] = {strategy: {dataset: summarize([row for row in rows if row["dataset"] == dataset])
                                          for dataset in ("regression", "challenge")}
                               for strategy, rows in rows_by_strategy.items()}
        metadata["comparison"] = comparison(rows_by_strategy)
        save()
        print(output)


if __name__ == "__main__":
    main()
