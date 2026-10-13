"""Replayable RAG evaluation records and 4B-vs-8B comparison runner."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any
from cpea.bootstrap import AssistantRuntime
from cpea.infrastructure.llm.parsing import parse_model
from evaluations.metadata import run_metadata, write_jsonl

from pydantic import BaseModel, Field

from cpea.application.services.answering import AnswerSynthesisService
from cpea.application.services.sql_execution import SQLExecutionAgent
from cpea.workflows.text_to_sql.schemas import AnswerDraft
from cpea.application.models.query import SourceReference
from cpea.workflows.text_to_sql.sql_generation import SQLGenerationWorkflow
from cpea.infrastructure.llm.factory import get_llm_config


class EvaluationCase(BaseModel):
    question: str = Field(min_length=1)
    expected_sources: list[str] = Field(default_factory=list)
    notes: str | None = None


class RerankerRecord(BaseModel):
    document_id: str
    retrieval_score: float | None = None
    reranker_score: float | None = None


class QualityReview(BaseModel):
    """Human or external-judge fields; the runner never fabricates scores."""

    completeness: int | None = Field(default=None, ge=0, le=5)
    important_information_omission: int | None = Field(default=None, ge=0, le=5)
    hallucination: int | None = Field(default=None, ge=0, le=5)
    instruction_following: int | None = Field(default=None, ge=0, le=5)
    citation_correctness: int | None = Field(default=None, ge=0, le=5)
    reviewer_notes: str | None = None


class LatencyMetrics(BaseModel):
    retrieval_ms: float
    reranker_ms: float
    preparation_ms: float
    warmup_ms: float | None = None
    llm_ttft_ms: float | None = None
    llm_generation_ms: float | None = None
    provider_load_ms: float | None = None
    provider_prompt_eval_ms: float | None = None
    provider_generation_ms: float | None = None
    total_ms: float
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    tokens_per_second: float | None = None


class ModelEvaluationRecord(BaseModel):
    question: str
    expected_sources: list[str] = Field(default_factory=list)
    model: str
    retrieved_documents: list[SourceReference] = Field(default_factory=list)
    reranker_result: list[RerankerRecord] = Field(default_factory=list)
    final_context: str
    final_prompt: list[dict[str, str]]
    answer: str
    citations: list[str] = Field(default_factory=list)
    retrieval_hit: bool | None = None
    latency: LatencyMetrics
    run_metadata: dict[str, Any] = Field(default_factory=dict)
    quality: QualityReview = Field(default_factory=QualityReview)
    error: str | None = None


def load_cases(path: str | Path) -> list[EvaluationCase]:
    source = Path(path)
    cases: list[EvaluationCase] = []
    for line_number, line in enumerate(
        source.read_text(encoding="utf-8").splitlines(), start=1
    ):
        if not line.strip():
            continue
        try:
            cases.append(EvaluationCase.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(
                f"invalid evaluation JSONL line {line_number}: {exc}"
            ) from exc
    return cases


def write_records(path: str | Path, records: list[ModelEvaluationRecord]) -> None:
    write_jsonl(path, records)


def _chunk_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


def _stream_answer(llm: Any, messages: list[Any]) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    first_token_at: float | None = None
    chunks: list[str] = []
    prompt_tokens: int | None = None
    output_tokens: int | None = None
    load_duration_ns: int | None = None
    prompt_eval_duration_ns: int | None = None
    eval_duration_ns: int | None = None
    for chunk in llm.stream(messages):
        text = _chunk_text(getattr(chunk, "content", ""))
        if text and first_token_at is None:
            first_token_at = time.perf_counter()
        chunks.append(text)
        usage = getattr(chunk, "usage_metadata", None) or {}
        metadata = getattr(chunk, "response_metadata", None) or {}
        prompt_tokens = usage.get("input_tokens", prompt_tokens)
        output_tokens = usage.get("output_tokens", output_tokens)
        prompt_tokens = metadata.get("prompt_eval_count", prompt_tokens)
        output_tokens = metadata.get("eval_count", output_tokens)
        load_duration_ns = metadata.get("load_duration", load_duration_ns)
        prompt_eval_duration_ns = metadata.get(
            "prompt_eval_duration", prompt_eval_duration_ns
        )
        eval_duration_ns = metadata.get("eval_duration", eval_duration_ns)
    finished = time.perf_counter()
    ttft_ms = (first_token_at - started) * 1000 if first_token_at is not None else None
    generation_ms = (
        (finished - first_token_at) * 1000 if first_token_at is not None else None
    )
    tokens_per_second = None
    if output_tokens is not None and generation_ms and generation_ms > 0:
        tokens_per_second = output_tokens / (generation_ms / 1000)
    return "".join(chunks), {
        "ttft_ms": ttft_ms,
        "generation_ms": generation_ms,
        "provider_load_ms": (
            load_duration_ns / 1_000_000 if load_duration_ns is not None else None
        ),
        "provider_prompt_eval_ms": (
            prompt_eval_duration_ns / 1_000_000
            if prompt_eval_duration_ns is not None
            else None
        ),
        "provider_generation_ms": (
            eval_duration_ns / 1_000_000 if eval_duration_ns is not None else None
        ),
        "total_ms": (finished - started) * 1000,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "tokens_per_second": tokens_per_second,
    }


def _warm_model(llm: Any) -> float:
    """Load the selected model before measuring request TTFT.

    A single Ollama server may evict one model while switching to another.
    Keeping this cost separate prevents model load time from being mistaken
    for prompt-processing latency.
    """
    started = time.perf_counter()
    llm.invoke('只回傳 JSON：{"ready": true}')
    return (time.perf_counter() - started) * 1000


def compare_models(
    cases: list[EvaluationCase],
    models: list[str],
    *,
    preparation_model: str | None = None,
    warmup: bool = True,
    runtime: AssistantRuntime | None = None,
    llm_factory=None,
    kind: str = "real-model",
) -> list[ModelEvaluationRecord]:
    """Prepare retrieval/SQL once, then replay identical final prompts."""
    if len(models) < 2:
        raise ValueError("at least two model names are required for comparison")
    runtime = runtime if runtime is not None else AssistantRuntime.from_env()
    runtime.require_execution()
    model_factory = llm_factory or (lambda name: get_llm_config(model=name, settings=runtime.settings))
    records: list[ModelEvaluationRecord] = []
    metadata = run_metadata(runtime, cases, kind=kind)
    preparation_llm = model_factory(preparation_model or models[0])
    for case in cases:
        preparation_started = time.perf_counter()
        execution = SQLExecutionAgent(preparation_llm, runtime.catalog, executor=runtime.executor,
            settings=runtime.settings, retriever=runtime.retriever, context_packer=runtime.context_packer
        ).run(case.question, datasource=runtime.datasource_id)
        answer_service = runtime.answer_service(preparation_llm)
        final_context, source, rows_in_context = answer_service.build_context(
            case.question, execution
        )
        messages = answer_service.build_messages(
            case.question,
            final_context,
            execution.generation.limitations,
        )
        preparation_ms = (time.perf_counter() - preparation_started) * 1000
        final_prompt = [
            {"role": message.type, "content": _chunk_text(message.content)}
            for message in messages
        ]
        reranker_result = [
            RerankerRecord(
                document_id=item.document_id,
                retrieval_score=item.retrieval_score,
                reranker_score=item.reranker_score,
            )
            for item in execution.generation.retrieved_candidates
        ]
        retrieved_ids = {
            item.document_id for item in execution.generation.retrieved_candidates
        }
        retrieval_hit = (
            all(expected in retrieved_ids for expected in case.expected_sources)
            if case.expected_sources
            else None
        )
        for model in models:
            model_llm = model_factory(model)
            generation_metrics = {
                "ttft_ms": None,
                "generation_ms": None,
                "provider_load_ms": None,
                "provider_prompt_eval_ms": None,
                "provider_generation_ms": None,
                "total_ms": 0.0,
                "prompt_tokens": None,
                "output_tokens": None,
                "tokens_per_second": None,
            }
            warmup_ms: float | None = None
            try:
                if warmup:
                    warmup_ms = _warm_model(model_llm)
                raw_answer, generation_metrics = _stream_answer(model_llm, messages)
                raw = type("StreamingMessage", (), {"content": raw_answer})()
                draft = parse_model(raw, AnswerDraft)
                response = answer_service.build_response(
                    draft, source, rows_in_context, execution
                )
                error = None
                answer = response.answer
                citations = response.citations
            except Exception as exc:  # noqa: BLE001 - preserve failed peer metrics
                error = f"{type(exc).__name__}: {exc}"
                answer = ""
                citations = []
            records.append(
                ModelEvaluationRecord(
                    run_metadata={**metadata, "model": model},
                    question=case.question,
                    expected_sources=case.expected_sources,
                    model=model,
                    retrieved_documents=execution.generation.retrieved_candidates,
                    reranker_result=reranker_result,
                    final_context=final_context,
                    final_prompt=final_prompt,
                    answer=answer,
                    citations=citations,
                    retrieval_hit=retrieval_hit,
                    latency=LatencyMetrics(
                        retrieval_ms=execution.generation.retrieval_latency_ms,
                        reranker_ms=execution.generation.reranker_latency_ms,
                        preparation_ms=preparation_ms,
                        warmup_ms=warmup_ms,
                        llm_ttft_ms=generation_metrics["ttft_ms"],
                        llm_generation_ms=generation_metrics["generation_ms"],
                        provider_load_ms=generation_metrics["provider_load_ms"],
                        provider_prompt_eval_ms=generation_metrics[
                            "provider_prompt_eval_ms"
                        ],
                        provider_generation_ms=generation_metrics[
                            "provider_generation_ms"
                        ],
                        total_ms=preparation_ms + generation_metrics["total_ms"],
                        prompt_tokens=generation_metrics["prompt_tokens"],
                        output_tokens=generation_metrics["output_tokens"],
                        tokens_per_second=generation_metrics["tokens_per_second"],
                    ),
                    error=error,
                )
            )
    return records
