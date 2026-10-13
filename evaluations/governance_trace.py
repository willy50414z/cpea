"""Call-level private traces for governance evaluations."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import platform
from threading import Lock
from time import perf_counter
from typing import Any
from uuid import uuid4


def _plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


class CallRecorder:
    def __init__(self, *, run_id: str, git_sha: str | None, concurrency: int = 1,
                 path: Path | None = None):
        self.run_id = run_id
        self.git_sha = git_sha
        self.concurrency = concurrency
        self.calls: list[dict[str, Any]] = []
        self._lock = Lock()
        self._active = 0
        self.path = path
        if self.path is not None:
            self.path.open("x", encoding="utf-8").close()

    def begin(self) -> int:
        with self._lock:
            self._active += 1
            return self._active

    def finish(self, record: dict[str, Any]) -> None:
        with self._lock:
            self._active -= 1
            self.calls.append(record)
            if self.path is not None:
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class TracedModel:
    """Wrap invoke, stream, and structured invoke without changing workflow APIs."""

    def __init__(self, model: Any, recorder: CallRecorder, *, case_id: str,
                 repetition: int, target: Any, settings: Any, node_name: str = "schema_match",
                 quantization: str | None = None, model_digest: str | None = None):
        self.model = model
        self.recorder = recorder
        self.case_id = case_id
        self.repetition = repetition
        self.target = target
        self.settings = settings
        self.node_name = node_name
        self.quantization = quantization
        self.model_digest = model_digest
        self._attempts: dict[str, int] = {}

    def at(self, node_name: str) -> "TracedModel":
        return TracedModel(self.model, self.recorder, case_id=self.case_id,
                           repetition=self.repetition, target=self.target,
                           settings=self.settings, node_name=node_name,
                           quantization=self.quantization, model_digest=self.model_digest)

    def _call(self, request: Any, action, *, stream: bool = False):
        node = self.node_name
        self._attempts[node] = self._attempts.get(node, 0) + 1
        attempt = self._attempts[node]
        active = self.recorder.begin()
        started = perf_counter()
        first_at = None
        raw = None
        error = None
        try:
            if stream:
                chunks = []
                for chunk in action():
                    if first_at is None:
                        first_at = perf_counter()
                    chunks.append(chunk)
                    yield chunk
                raw = chunks
            else:
                raw = action()
                yield raw
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            ended = perf_counter()
            usage_source = "unavailable"
            input_tokens = output_tokens = None
            metadata = {}
            response = raw
            if isinstance(raw, dict) and "raw" in raw:
                response = raw["raw"]
                if raw.get("parsing_error"):
                    error = f"structured_parse:{raw['parsing_error']}"
            if isinstance(response, list) and response:
                response = response[-1]
            if response is not None:
                usage = getattr(response, "usage_metadata", None) or {}
                metadata = getattr(response, "response_metadata", None) or {}
                input_tokens = usage.get("input_tokens", metadata.get("prompt_eval_count"))
                output_tokens = usage.get("output_tokens", metadata.get("eval_count"))
                if input_tokens is not None or output_tokens is not None:
                    usage_source = "provider"
            record = {
                "call_id": uuid4().hex, "run_id": self.recorder.run_id,
                "case_id": self.case_id, "repetition": self.repetition,
                "node_name": node, "attempt_index": attempt,
                "runner_node": platform.node(), "model_node": self.target.node_name,
                "provider": self.target.provider, "transport": self.target.transport,
                "model": self.target.model,
                "resolved_model": metadata.get("model_name") or metadata.get("model") or self.target.deployment or self.target.model,
                "model_digest": self.model_digest,
                "quantization": self.quantization,
                "quantization_reason": None if self.quantization else "provider_did_not_report",
                "request": _plain(request), "response": _plain(raw), "error": error,
                "input_tokens": input_tokens, "output_tokens": output_tokens,
                "token_source": usage_source,
                "elapsed_ms": (ended - started) * 1000,
                "ttft_ms": (first_at - started) * 1000 if first_at is not None else None,
                "concurrency": self.recorder.concurrency,
                "observed_concurrency": active,
                "num_ctx": self.settings.context_window if self.target.transport == "ollama" else None,
                "max_token": self.settings.max_output_tokens,
                "temperature": self.settings.temperature, "top_p": self.settings.top_p,
                "git_sha": self.recorder.git_sha,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            self.recorder.finish(record)

    def invoke(self, messages):
        return list(self._call(messages, lambda: self.model.invoke(messages)))[0]

    def stream(self, messages):
        yield from self._call(messages, lambda: self.model.stream(messages), stream=True)

    def with_structured_output(self, schema, **kwargs):
        try:
            runnable = self.model.with_structured_output(schema, include_raw=True, **kwargs)
        except (TypeError, ValueError):
            runnable = self.model.with_structured_output(schema, **kwargs)
        parent = self

        class Structured:
            def invoke(self, messages):
                value = list(parent._call(messages, lambda: runnable.invoke(messages)))[0]
                if isinstance(value, dict) and "parsed" in value and "raw" in value:
                    if value.get("parsing_error"):
                        raise ValueError(str(value["parsing_error"]))
                    return value["parsed"]
                return value

        return Structured()
