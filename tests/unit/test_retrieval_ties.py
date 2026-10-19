from dataclasses import replace
import math
from pathlib import Path
from types import SimpleNamespace

from langchain_core.documents import Document
import pytest

from cpea.config.settings import AssistantSettings
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, SchemaRetriever, select_with_ties


def candidates(scores):
    return [RetrievalCandidate(Document(page_content="", metadata={"document_id": f"v{index}"}), score)
            for index, score in enumerate(scores)]


@pytest.mark.parametrize("scores,expected", [
    ([1, .9, .8, .7, .6, .5], 5),
    ([1, .9, .8, .7, .6, .6], 6),
    ([1, .9, .8, .7, .6, .6, .6], 7),
    ([1, .9], 2), ([], 0), ([0] * 7, 7),
    ([1, .9, .8, .7, .6, math.nextafter(.6, -math.inf)], 5),
])
def test_selection_preserves_prefix_and_all_exact_boundary_ties(scores, expected):
    items = candidates(scores)
    selected = select_with_ties(items)
    assert selected == items[:expected]
    assert selected[:5] == items[:5]


def test_cutoff_uses_reranker_score_and_rejects_invalid_inputs():
    items = [replace(item, reranker_score=.5) for item in candidates([1, .9, .8, .7, .6, .4])]
    assert len(select_with_ties(items)) == 6
    with pytest.raises(ValueError, match="positive"):
        select_with_ties(items, 0)
    for score in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValueError, match="finite"):
            select_with_ties(candidates([score]))


def retail_retriever(**overrides):
    root = Path(__file__).resolve().parents[2] / "projects/retail"
    settings = replace(AssistantSettings.from_env(), retrieval_mode="lexical", retrieval_k=7,
                       rerank_top_k=5, reranker_enabled=False, **overrides)
    return SchemaRetriever(settings, SchemaCatalog(root, allow_drafts=True))


def test_shuffled_same_score_candidates_keep_versioned_catalog_order():
    retriever = retail_retriever()
    original = [RetrievalCandidate(doc, .5) for doc in retriever.documents]
    assert retriever._rerank("query", reversed(original)) == retriever._rerank("query", original)
    assert [item.document for item in retriever._rerank("query", original)] == retriever.documents


def test_known_sixth_place_order_view_survives_both_cutoffs():
    retriever = retail_retriever()
    retriever.settings = replace(retriever.settings, retrieval_k=5, reranker_enabled=True,
                                  reranker_provider="lexical")
    request = "我想看逐筆的從哪個管道成交、賺到的毛利，條件是會員叫什麼 LIKE 王%。"
    selected = retriever.retrieve(request).candidates
    assert len(selected) == 6
    assert selected[4].document.metadata["document_id"] == "demo_retail.v_daily_sales"
    assert selected[5].document.metadata["document_id"] == "demo_retail.v_order_summary"
    assert selected[4].reranker_score == selected[5].reranker_score


def test_vector_search_does_not_truncate_a_tie_before_reranking():
    retriever = retail_retriever()
    retriever.settings = replace(retriever.settings, retrieval_mode="vector", retrieval_k=5)
    scores = [1, .9, .8, .7, .6, .6, .5]
    def search(query, *, k, filter):
        assert k == 7
        return list(reversed([(doc, score) for doc, score in zip(retriever.documents, scores, strict=True)]))
    retriever.__dict__["vector_store"] = SimpleNamespace(similarity_search_with_score=search)
    assert len(retriever.retrieve("query").candidates) == 6
