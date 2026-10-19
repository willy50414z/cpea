import json
from collections import Counter
from pathlib import Path
import sys

import pytest

from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from evaluations import retrieval_benchmark as benchmark


PROFILE = Path(__file__).resolve().parents[2] / "projects/retail"


def test_challenge_has_fifty_contract_bound_pending_cases():
    catalog = SchemaCatalog(PROFILE, allow_drafts=True)
    cases = benchmark.load_challenge(benchmark.CHALLENGE, catalog)
    assert Counter(case["category"] for case in cases) == dict.fromkeys(benchmark.CATEGORIES, 10)
    assert all(case["review_status"] == "pending" for case in cases)
    assert any(not case["valid_views"] for case in cases)
    assert any(case["requires_clarification"] for case in cases)
    assert any(len(case["valid_views"]) > 1 and not case["requires_clarification"] for case in cases)
    with pytest.raises(ValueError, match="human review"):
        benchmark.evaluation_cases(PROFILE / "evaluations/cases.jsonl", benchmark.CHALLENGE,
                                   catalog, exploratory=False)
    assert len(benchmark.evaluation_cases(PROFILE / "evaluations/cases.jsonl", benchmark.CHALLENGE,
                                          catalog, exploratory=True)) == 445


def test_human_approval_is_bound_to_labels_and_contract(tmp_path):
    catalog = SchemaCatalog(PROFILE, allow_drafts=True)
    case = benchmark.load_challenge(benchmark.CHALLENGE, catalog)[0]
    case.update(review_status="approved", reviewer="human-reviewer", reviewed_at="2026-10-19T00:00:00Z",
                reviewed_contract_fingerprint=catalog.fingerprint)
    case["reviewed_case_sha256"] = benchmark.challenge_content_sha256(case)
    path = tmp_path / "challenge.jsonl"
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    assert benchmark.load_challenge(path, catalog)[0]["review_status"] == "approved"
    case["request"] += " changed"
    path.write_text(json.dumps(case, ensure_ascii=False) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="human approval"):
        benchmark.load_challenge(path, catalog)


def test_selected_recall_is_separate_from_strict_top_five():
    row = {"gold_views": ["gold"], "valid_views": ["gold", "v1"],
           "retrieved_views": [{"view": name} for name in ["v1", "v2", "v3", "v4", "v5", "gold"]],
           "selected_views": ["v1", "v2", "v3", "v4", "v5", "gold"],
           "extra_candidate_count": 1, "requires_clarification": True,
           "interpretation_coverage": 1, "retrieval_latency_ms": 10}
    metrics = benchmark.summarize([row])
    assert metrics["gold_recall_at_5"] == 0
    assert metrics["gold_selected_recall"] == metrics["valid_view_recall"] == 1
    assert metrics["ambiguity_coverage"] == 1
    assert metrics["avg_candidate_count"] == 6
    assert metrics["clarification_precision"] is metrics["sql_correctness"] is None
    assert metrics["end_to_end_latency_p95_ms"] is None
    assert benchmark.summarize([])["gold_selected_recall"] is None


def test_dirty_worktree_is_rejected_before_reading_cases_or_calling_models(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["benchmark", "--experiment-id", "test", "--exploratory"])
    monkeypatch.setattr(benchmark.subprocess, "check_output", lambda *args, **kwargs: " M source.py\n")
    with pytest.raises(ValueError, match="clean Git worktree"):
        benchmark.main()
