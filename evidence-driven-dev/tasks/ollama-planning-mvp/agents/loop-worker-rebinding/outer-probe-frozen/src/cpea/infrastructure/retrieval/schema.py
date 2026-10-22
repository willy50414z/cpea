"""Two-stage retrieval for the assistant's curated schema knowledge."""

from __future__ import annotations

import logging
import math
import re
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass, replace
from functools import cached_property
from collections import OrderedDict
from threading import RLock
from typing import Any

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.vectorstores import InMemoryVectorStore

from cpea.application.ports.catalog import CatalogProvider
from cpea.infrastructure.catalog.yaml_catalog import SchemaCatalog
from cpea.infrastructure.retrieval.documents import build_documents
from cpea.config.settings import AssistantSettings

logger = logging.getLogger(__name__)

_ASCII_TERM = re.compile(r"[a-z0-9_.-]+", re.IGNORECASE)
_CJK_RUN = re.compile(r"[\u3400-\u9fff]+")
_QUERY_FILLER = {
    "請",
    "查詢",
    "目前",
    "現在",
    "資料",
    "多少",
    "哪些",
    "各個",
}


def preprocess_query(query: str) -> str:
    normalized = unicodedata.normalize("NFKC", query)
    return " ".join(normalized.strip().split())


def explicit_column_references(query: str, catalog: CatalogProvider) -> set[str]:
    """Find exact catalog identifiers, excluding filter values and quoted data."""
    known = {column for view in catalog.views() for column in catalog.columns(view.name)
             if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', column)}
    literals = [m.span() for m in re.finditer(r"'(?:''|[^'])*'", query)]
    for match in re.finditer(
        r"""(?:>=|<=|!=|<>|=|>|<|\bLIKE\b)\s*("[^"]*"|'(?:''|[^'])*'|[^\s，。；、且]+)"""
        r'|\bIN\s*\(([^)]*)\)', query, re.IGNORECASE,
    ):
        literals.append(match.span(1 if match.group(1) is not None else 2))
    return {m.group() for m in re.finditer(r'[A-Za-z_][A-Za-z0-9_]*', query)
            if m.group() in known and not any(a <= m.start() and m.end() <= b for a, b in literals)}


def _lexical_terms(text: str) -> set[str]:
    normalized = preprocess_query(text).lower()
    terms = {term for term in _ASCII_TERM.findall(normalized) if len(term) > 1}
    for run in _CJK_RUN.findall(normalized):
        terms.update(char for char in run if char not in _QUERY_FILLER)
        terms.update(run[index : index + 2] for index in range(len(run) - 1))
    return terms - _QUERY_FILLER


def _lexical_score(query: str, document: Document) -> float:
    query_terms = _lexical_terms(query)
    if not query_terms:
        return 0.0
    title_terms = _lexical_terms(
        " ".join(
            str(document.metadata.get(key, ""))
            for key in ("view_name", "summary", "section")
        )
    )
    content_terms = _lexical_terms(document.page_content)
    title_overlap = len(query_terms & title_terms) / len(query_terms)
    content_overlap = len(query_terms & content_terms) / len(query_terms)
    exact_identifiers = {
        term for term in query_terms if any(char.isdigit() for char in term)
    }
    identifier_boost = 0.0
    if exact_identifiers:
        haystack = document.page_content.lower()
        identifier_boost = sum(term in haystack for term in exact_identifiers) / len(
            exact_identifiers
        )
    return min(
        1.0,
        (0.55 * title_overlap) + (0.35 * content_overlap) + (0.1 * identifier_boost),
    )


def _view_lexical_score(query: str, document: Document) -> float:
    """Rank a View by its summary and best matching fields, not its size."""
    view_name = str(document.metadata.get("view_name", ""))
    if view_name and view_name.lower() in preprocess_query(query).lower():
        return 1.0
    query_terms = _lexical_terms(query)
    if not query_terms:
        return 0.0
    def overlap(text: str) -> float:
        return len(query_terms & _lexical_terms(text)) / len(query_terms)
    summary = overlap(str(document.metadata.get("summary", "")))
    fields = [overlap(line) for line in document.page_content.splitlines() if line.startswith("- ")]
    if not fields:
        return summary
    strongest = sorted(fields, reverse=True)[:3]
    return (0.3 * summary) + (0.7 * sum(strongest) / len(strongest))


def lexical_relevance(query: str, text: str) -> float:
    """Return a lightweight relevance score for non-document context."""
    return _lexical_score(query, Document(page_content=text, metadata={}))


@dataclass(frozen=True)
class RetrievalCandidate:
    document: Document
    retrieval_score: float
    reranker_score: float | None = None


@dataclass(frozen=True)
class RetrievalResult:
    query: str
    candidates: list[RetrievalCandidate]
    retrieval_latency_ms: float
    reranker_latency_ms: float


class SchemaRetriever:
    """Retrieve broad candidates, then rerank a smaller context set."""

    def __init__(
        self,
        settings: AssistantSettings,
        catalog: CatalogProvider | None = None,
        embeddings: Embeddings | None = None,
        cross_encoder: Any | None = None,
    ) -> None:
        self.settings = settings
        self.catalog = catalog or SchemaCatalog()
        self.documents = build_documents(self.catalog)
        self._embeddings = embeddings
        self._cross_encoder = cross_encoder

    @cached_property
    def vector_store(self) -> InMemoryVectorStore:
        store = InMemoryVectorStore(self._embeddings or self._build_embeddings())
        store.add_documents(self.documents)
        return store

    def retrieve(self, query: str) -> RetrievalResult:
        normalized_query = preprocess_query(query)
        retrieval_started = time.perf_counter()

        # 透過2種不同的方式進行views篩選
        if self.settings.retrieval_mode == "vector":
            # 向量比對
            candidates = self._vector_candidates(normalized_query)
        else:
            # 字面量檢索
            candidates = self._lexical_candidates(normalized_query)

        retrieval_ms = (time.perf_counter() - retrieval_started) * 1000

        rerank_started = time.perf_counter()
        reranked = self._rerank(normalized_query, candidates)
        rerank_ms = (time.perf_counter() - rerank_started) * 1000
        selected = reranked[: min(self.settings.rerank_top_k, len(reranked))]
        logger.info(
            "assistant retrieval mode=%s candidates=%d selected=%d retrieval_ms=%.1f reranker_ms=%.1f",
            self.settings.retrieval_mode,
            len(candidates),
            len(selected),
            retrieval_ms,
            rerank_ms,
        )
        return RetrievalResult(
            query=normalized_query,
            candidates=selected,
            retrieval_latency_ms=retrieval_ms,
            reranker_latency_ms=rerank_ms,
        )

    def _vector_candidates(self, query: str) -> list[RetrievalCandidate]:
        required = explicit_column_references(query, self.catalog)
        allowed = {item.name for item in self.catalog.views()
                   if required <= set(self.catalog.columns(item.name))}
        results = self.vector_store.similarity_search_with_score(
            query,
            k=min(self.settings.retrieval_k, len(self.documents)),
            filter=lambda doc: (
                doc.metadata.get("document_type") == "database_view"
                and doc.metadata.get("document_id") in allowed
            ),
        )
        candidates: list[RetrievalCandidate] = []
        for item in results:
            # langchain-core 1.6 currently returns an undocumented third
            # vector element; accepting both shapes keeps this compatible
            # with the documented two-item contract and older releases.
            document, score = item[0], item[1]
            candidates.append(
                RetrievalCandidate(document=document, retrieval_score=float(score))
            )
        return candidates

    def _lexical_candidates(self, query: str) -> list[RetrievalCandidate]:
        required = explicit_column_references(query, self.catalog)
        allowed = {item.name for item in self.catalog.views()
                   if required <= set(self.catalog.columns(item.name))}
        ranked = sorted(
            (
                RetrievalCandidate(
                    document=doc, retrieval_score=_view_lexical_score(query, doc)
                )
                for doc in self.documents if doc.metadata.get('document_id') in allowed
            ),
            key=lambda item: item.retrieval_score,
            reverse=True,
        )
        return ranked[: min(self.settings.retrieval_k, len(ranked))]

    def _rerank(
        self, query: str, candidates: Iterable[RetrievalCandidate]
    ) -> list[RetrievalCandidate]:
        items = list(candidates)
        if (
            not self.settings.reranker_enabled
            or self.settings.reranker_provider == "none"
        ):
            return [
                replace(item, reranker_score=item.retrieval_score) for item in items
            ]
        if self.settings.reranker_provider == "cross_encoder":
            encoder = self._cross_encoder or self._build_cross_encoder()
            scores = encoder.predict(
                [(query, item.document.page_content) for item in items],
                show_progress_bar=False,
            )
            reranked = [
                replace(item, reranker_score=float(score))
                for item, score in zip(items, scores, strict=True)
            ]
        else:
            reranked = []
            for item in items:
                lexical = _view_lexical_score(query, item.document)
                # Preserve dense-retrieval evidence while allowing exact
                # Chinese business terms and product numbers to dominate.
                combined = (0.75 * lexical) + (
                    0.25 * max(0.0, min(1.0, item.retrieval_score))
                )
                reranked.append(replace(item, reranker_score=combined))
        return sorted(
            reranked,
            key=lambda item: (
                -math.inf if item.reranker_score is None else item.reranker_score
            ),
            reverse=True,
        )

    def _build_embeddings(self) -> Embeddings:
        if self.settings.embedding_provider == "ollama":
            from langchain_ollama import OllamaEmbeddings

            return OllamaEmbeddings(
                base_url=self.settings.embedding_base_url,
                model=self.settings.embedding_model,
                client_kwargs={"timeout": self.settings.request_timeout_seconds},
            )
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:  # pragma: no cover - deployment guard
            raise RuntimeError(
                "OpenAI-compatible embeddings require 'langchain-openai'"
            ) from exc
        return OpenAIEmbeddings(
            base_url=self.settings.embedding_base_url,
            api_key=self.settings.embedding_api_key,
            model=self.settings.embedding_model,
            request_timeout=self.settings.request_timeout_seconds,
        )

    def _build_cross_encoder(self) -> Any:
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:
            raise RuntimeError(
                "cross_encoder reranking requires: uv pip install 'sentence-transformers>=5,<6'"
            ) from exc
        # CPU is intentional: the main LLM owns the limited GPU VRAM.
        return CrossEncoder(self.settings.reranker_model, device="cpu")


_RETRIEVERS: OrderedDict[tuple, SchemaRetriever] = OrderedDict()
_RETRIEVER_LOCK = RLock()

def get_schema_retriever(settings: AssistantSettings | None = None,
                         catalog: CatalogProvider | None = None) -> SchemaRetriever:
    settings = settings or AssistantSettings.from_env()
    catalog = catalog or SchemaCatalog(settings.integration_path)
    # Provider implementations need not be hashable. Instance identity also keeps
    # absolute source/provenance paths distinct for identical profiles on disk.
    key = (settings, catalog.profile_id, catalog.contract_version, catalog.fingerprint, id(catalog))
    with _RETRIEVER_LOCK:
        if key not in _RETRIEVERS:
            _RETRIEVERS[key] = SchemaRetriever(settings, catalog=catalog)
        _RETRIEVERS.move_to_end(key)
        while len(_RETRIEVERS) > 4:
            _RETRIEVERS.popitem(last=False)
        return _RETRIEVERS[key]
