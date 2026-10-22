"""Model-aware token budgets for history and retrieved schema context."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass
from functools import cached_property
from typing import Protocol

import requests
import tiktoken

from cpea.application.models.query import ConversationTurn, SourceReference
from cpea.infrastructure.retrieval.schema import RetrievalCandidate, lexical_relevance
from cpea.config.settings import AssistantSettings

logger = logging.getLogger(__name__)


class TokenCounter(Protocol):
    name: str

    def count(self, text: str) -> int: ...

    def count_messages(self, messages: Sequence[tuple[str, str]]) -> int: ...


class TiktokenCounter:
    """Tokenizer fallback for providers that expose no tokenize endpoint.

    This counts real BPE tokens rather than words or characters. It may not
    exactly match an arbitrary Ollama model, so a separate safety reserve is
    always retained and the counter name is logged with every packed context.
    """

    def __init__(self, encoding_name: str) -> None:
        self.encoding_name = encoding_name
        self.name = f"tiktoken:{encoding_name}"

    @cached_property
    def encoding(self):
        return tiktoken.get_encoding(self.encoding_name)

    def count(self, text: str) -> int:
        return len(self.encoding.encode(text, disallowed_special=()))

    def count_messages(self, messages: Sequence[tuple[str, str]]) -> int:
        # Chat templates add role/control tokens. Eight tokens per message is
        # a conservative allowance without pretending it is model-exact.
        return (
            sum(
                self.count(role) + self.count(content) + 8 for role, content in messages
            )
            + 4
        )


class HttpTokenCounter:
    """Use a llama.cpp-compatible tokenize endpoint for exact model tokens."""

    def __init__(self, endpoint: str, timeout_seconds: float) -> None:
        self.endpoint = endpoint
        self.timeout_seconds = timeout_seconds
        self.name = f"http:{endpoint}"

    def count(self, text: str) -> int:
        response = requests.post(
            self.endpoint,
            json={"content": text},
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        tokens = payload.get("tokens")
        if not isinstance(tokens, list):
            raise TypeError("tokenize endpoint did not return a tokens array")
        return len(tokens)

    def count_messages(self, messages: Sequence[tuple[str, str]]) -> int:
        serialized = "".join(f"<{role}>\n{content}\n" for role, content in messages)
        return self.count(serialized) + (4 * len(messages))


def build_token_counter(settings: AssistantSettings) -> TokenCounter:
    if settings.token_count_endpoint:
        endpoint = settings.token_count_endpoint
    elif settings.llm_provider == "llamacpp":
        endpoint = f"{settings.llm_base_url.removesuffix('/v1')}/tokenize"
    else:
        endpoint = ""
    if endpoint:
        return HttpTokenCounter(endpoint, settings.request_timeout_seconds)
    return TiktokenCounter(settings.token_count_encoding)


@dataclass(frozen=True)
class PackedContext:
    text: str
    sources: list[SourceReference]
    context_tokens: int
    document_budget: int
    dropped_document_ids: list[str]
    token_counter: str


class ContextPacker:
    def __init__(
        self,
        settings: AssistantSettings,
        token_counter: TokenCounter | None = None,
    ) -> None:
        self.settings = settings
        self.token_counter = token_counter or build_token_counter(settings)

    def pack_history(self, question: str, history: Sequence[ConversationTurn]) -> str:
        if not history or self.settings.history_token_budget == 0:
            return ""
        recent_start = max(0, len(history) - self.settings.history_recent_turns)
        ranked_indices = list(range(recent_start, len(history)))
        older_relevant = sorted(
            (
                (lexical_relevance(question, turn.content), index)
                for index, turn in enumerate(history[:recent_start])
            ),
            reverse=True,
        )
        ranked_indices.extend(index for score, index in older_relevant if score > 0.15)
        selected: list[int] = []
        used = 0
        for index in dict.fromkeys(reversed(ranked_indices)):
            turn = history[index]
            rendered = f"{turn.role}: {turn.content}"
            tokens = self.token_counter.count(rendered)
            if used + tokens > self.settings.history_token_budget:
                continue
            selected.append(index)
            used += tokens
        return "\n".join(
            f"{history[index].role}: {history[index].content}"
            for index in sorted(selected)
        )

    def pack_documents(
        self,
        *,
        system_prompt: str,
        question: str,
        history_text: str,
        candidates: Sequence[RetrievalCandidate],
        additional_prompt_text: str = "",
    ) -> PackedContext:
        base_tokens = self.token_counter.count_messages(
            [
                ("system", system_prompt),
                (
                    "user",
                    f"問題：{question}\n歷史：{history_text}\n{additional_prompt_text}",
                ),
            ]
        )
        document_budget = max(
            0,
            self.settings.context_window
            - self.settings.output_token_reserve
            - self.settings.context_safety_tokens
            - base_tokens,
        )
        blocks: list[str] = []
        sources: list[SourceReference] = []
        dropped: list[str] = []
        used = 0
        ordered = sorted(
            candidates,
            key=lambda item: (
                item.reranker_score
                if item.reranker_score is not None
                else item.retrieval_score
            ),
            reverse=True,
        )
        for candidate in ordered:
            metadata = candidate.document.metadata
            source_number = len(sources) + 1
            block = (
                f"[Source {source_number}]\n"
                f"document_id: {metadata['document_id']}\n"
                f"source: {metadata['source']}\n"
                f"section: {metadata.get('section') or 'N/A'}\n\n"
                f"{candidate.document.page_content}"
            )
            tokens = self.token_counter.count(block)
            if used + tokens > document_budget:
                dropped.extend(
                    str(item.document.metadata["document_id"])
                    for item in ordered[len(sources) :]
                )
                break
            blocks.append(block)
            used += tokens
            sources.append(self.source_reference(candidate))
        logger.info(
            "assistant context counter=%s base_tokens=%d document_tokens=%d document_budget=%d packed=%d dropped=%d",
            self.token_counter.name,
            base_tokens,
            used,
            document_budget,
            len(sources),
            len(dropped),
        )
        return PackedContext(
            text="\n\n---\n\n".join(blocks),
            sources=sources,
            context_tokens=used,
            document_budget=document_budget,
            dropped_document_ids=dropped,
            token_counter=self.token_counter.name,
        )

    @staticmethod
    def source_reference(candidate: RetrievalCandidate) -> SourceReference:
        metadata = candidate.document.metadata
        public_metadata = {
            key: value
            for key, value in metadata.items()
            if key
            not in {
                "document_id",
                "source",
                "filename",
                "section",
                "page",
                "chunk_id",
            }
        }
        return SourceReference(
            document_id=str(metadata["document_id"]),
            source=str(metadata["source"]),
            filename=str(metadata["filename"]),
            section=metadata.get("section"),
            page=metadata.get("page"),
            chunk_id=str(metadata["chunk_id"]),
            metadata=public_metadata,
            retrieval_score=candidate.retrieval_score,
            reranker_score=candidate.reranker_score,
        )
