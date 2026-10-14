"""Central configuration for the local SQL/RAG assistant."""

from __future__ import annotations

import os
import math
from dataclasses import dataclass, field, replace
from contextvars import ContextVar
from pathlib import Path
from urllib.parse import urlparse

from dotenv import dotenv_values
from cpea.config.database import SQLServerSettings

_ENV_LAYERS = ContextVar('cpea_env_layers', default=None)

def _layers():
    return _ENV_LAYERS.get() or (os.environ,)

def _get_env(name):
    for layer in _layers():
        if name in layer:
            return layer[name]
    return None



def _first_env(*names: str, default: str) -> str:
    for layer in _layers():
        for name in names:
            value = layer.get(name)
            if value is not None and value.strip() != "":
                return value.strip()
    return default


def _env_bool(name: str, default: bool) -> bool:
    value = _get_env(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean value")


def _env_int(*names: str, default: int, minimum: int = 0) -> int:
    raw = _first_env(*names, default=str(default))
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{names[0]} must be an integer") from None
    if value < minimum:
        raise ValueError(f"{names[0]} must be >= {minimum}")
    return value


def _env_float(*names: str, default: str) -> float:
    try:
        value = float(_first_env(*names, default=default))
    except ValueError:
        raise ValueError(f'{names[0]} must be numeric') from None
    if not math.isfinite(value):
        raise ValueError(f'{names[0]} must be finite')
    return value


def _normalize_provider(value: str) -> str:
    normalized = value.strip().lower().replace("-", "").replace("_", "")
    aliases = {"ollama": "ollama", "llamacpp": "llamacpp", "azure": "azure", "gcp": "gcp", "google": "gcp"}
    try:
        return aliases[normalized]
    except KeyError as exc:
        raise ValueError("LLM_PROVIDER must be 'ollama', 'llamacpp', 'azure', or 'gcp'") from exc


def _validate_url(name: str, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"{name} must be an absolute HTTP(S) URL")
    return value.rstrip("/")


@dataclass(frozen=True)
class AssistantSettings:
    llm_provider: str
    llm_base_url: str
    llm_model: str
    llm_api_key: str = field(repr=False)
    temperature: float
    seed: int
    context_window: int
    max_output_tokens: int
    context_safety_tokens: int
    request_timeout_seconds: float
    embedding_provider: str
    embedding_base_url: str
    embedding_model: str
    embedding_api_key: str = field(repr=False)
    retrieval_mode: str
    retrieval_k: int
    reranker_enabled: bool
    reranker_provider: str
    reranker_model: str
    rerank_top_k: int
    history_token_budget: int
    history_recent_turns: int
    max_rows: int
    sql_generation_mode: str
    token_count_endpoint: str | None
    token_count_encoding: str

    integration_path: str | None = None
    deployment_file: str | None = None
    datasource_id: str | None = None
    top_p: float = 1.0
    gcp_project: str | None = None
    gcp_location: str = "global"
    llm_reasoning: bool = False
    sqlserver: SQLServerSettings = field(default_factory=SQLServerSettings)

    @property
    def output_token_reserve(self) -> int:
        return 512 if self.max_output_tokens == -1 else self.max_output_tokens

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> AssistantSettings:
        selected = env_file or os.environ.get('CPEA_ENV_FILE')
        values = {}
        base = Path.cwd()
        if selected is not None:
            path = Path(selected).resolve()
            if not path.is_file():
                raise ValueError('selected env file does not exist')
            values = dotenv_values(path, interpolate=False, encoding='utf-8')
            base = path.parent
        token = _ENV_LAYERS.set((os.environ, values))
        try:
            result = cls._from_values()
            for name in ('integration_path', 'deployment_file'):
                value = getattr(result, name)
                if value:
                    object.__setattr__(result, name, str((base / value).resolve()))
            if result.sqlserver.freetds_config_file:
                object.__setattr__(result, 'sqlserver', replace(result.sqlserver,
                    freetds_config_file=str((base / result.sqlserver.freetds_config_file).resolve())))
            return result
        finally:
            _ENV_LAYERS.reset(token)

    @classmethod
    def _from_values(cls) -> AssistantSettings:
        provider = _normalize_provider(
            _first_env("ASSISTANT_LLM_PROVIDER", "LLM_PROVIDER", default="ollama")
        )
        default_base_url = {
            "ollama": "http://localhost:11434",
            "llamacpp": "http://localhost:8080/v1",
            "azure": "https://example.invalid/openai/v1",
            "gcp": "https://generativelanguage.googleapis.com",
        }[provider]
        base_url = _validate_url(
            "LLM_BASE_URL",
            _first_env(
                "ASSISTANT_LLM_BASE_URL",
                "LLM_BASE_URL",
                default=default_base_url,
            ),
        )
        default_model = "gemma4" if provider == "ollama" else "local-model"
        embedding_provider = _first_env(
            "ASSISTANT_EMBEDDING_PROVIDER",
            "EMBEDDING_PROVIDER",
            default="ollama",
        ).lower()
        if embedding_provider not in {"ollama", "openai"}:
            raise ValueError("EMBEDDING_PROVIDER must be 'ollama' or 'openai'")
        embedding_base_url = _validate_url(
            "EMBEDDING_BASE_URL",
            _first_env(
                "ASSISTANT_EMBEDDING_BASE_URL",
                "EMBEDDING_BASE_URL",
                default=(
                    base_url.removesuffix("/v1")
                    if provider == "ollama"
                    else "http://localhost:11434"
                ),
            ),
        )
        retrieval_mode = _first_env(
            "ASSISTANT_RETRIEVAL_MODE", "RETRIEVAL_MODE", default="vector"
        ).lower()
        if retrieval_mode not in {"vector", "lexical"}:
            raise ValueError("RETRIEVAL_MODE must be 'vector' or 'lexical'")
        reranker_provider = _first_env(
            "ASSISTANT_RERANKER_PROVIDER", "RERANKER_PROVIDER", default="lexical"
        ).lower()
        if reranker_provider not in {"lexical", "cross_encoder", "none"}:
            raise ValueError(
                "RERANKER_PROVIDER must be 'lexical', 'cross_encoder', or 'none'"
            )
        sql_generation_mode = _first_env(
            "ASSISTANT_SQL_GENERATION_MODE", default="compiler"
        ).lower()
        if sql_generation_mode != "compiler":
            raise ValueError("ASSISTANT_SQL_GENERATION_MODE supports only compiler; legacy is unsupported")
        token_endpoint = _first_env(
            "ASSISTANT_TOKEN_COUNT_ENDPOINT", "TOKEN_COUNT_ENDPOINT", default=""
        )
        result = cls(
            llm_provider=provider,
            llm_base_url=base_url,
            llm_model=_first_env(
                "ASSISTANT_LLM_MODEL", "LLM_MODEL", default=default_model
            ),
            llm_api_key=_first_env(
                "ASSISTANT_LLM_API_KEY", "LLM_API_KEY", default="not-needed"
            ),
            temperature=_env_float(
                    "ASSISTANT_LLM_TEMPERATURE", "LLM_TEMPERATURE", default="0.0"
                ),
            top_p=_env_float("ASSISTANT_LLM_TOP_P", "LLM_TOP_P", default="1.0"),
            llm_reasoning=_env_bool("ASSISTANT_LLM_REASONING", False),
            gcp_project=_first_env("CPEA_GCP_PROJECT", "GOOGLE_CLOUD_PROJECT", default="") or None,
            gcp_location=_first_env("CPEA_GCP_LOCATION", "GOOGLE_CLOUD_LOCATION", default="global"),
            seed=_env_int("ASSISTANT_LLM_SEED", "LLM_SEED", default=42),
            context_window=_env_int(
                "ASSISTANT_LLM_NUM_CTX",
                "LLM_CONTEXT_WINDOW",
                default=4096,
                minimum=1024,
            ),
            max_output_tokens=_env_int(
                "ASSISTANT_LLM_NUM_PREDICT",
                "LLM_MAX_OUTPUT_TOKENS",
                default=512,
                minimum=-1,
            ),
            context_safety_tokens=_env_int(
                "ASSISTANT_CONTEXT_SAFETY_TOKENS", default=128, minimum=0
            ),
            request_timeout_seconds=_env_float("ASSISTANT_LLM_TIMEOUT_SECONDS", default="120"),
            embedding_provider=embedding_provider,
            embedding_base_url=embedding_base_url,
            embedding_model=_first_env(
                "ASSISTANT_EMBEDDING_MODEL",
                "EMBEDDING_MODEL",
                default="nomic-embed-text",
            ),
            embedding_api_key=_first_env(
                "ASSISTANT_EMBEDDING_API_KEY",
                "EMBEDDING_API_KEY",
                default="not-needed",
            ),
            retrieval_mode=retrieval_mode,
            retrieval_k=_env_int(
                "ASSISTANT_RETRIEVAL_K", "RETRIEVAL_K", default=15, minimum=1
            ),
            reranker_enabled=_env_bool("ASSISTANT_RERANKER_ENABLED", True),
            reranker_provider=reranker_provider,
            reranker_model=_first_env(
                "ASSISTANT_RERANKER_MODEL",
                "RERANKER_MODEL",
                default="BAAI/bge-reranker-base",
            ),
            rerank_top_k=_env_int(
                "ASSISTANT_RERANK_TOP_K", "RERANK_TOP_K", default=4, minimum=1
            ),
            history_token_budget=_env_int(
                "ASSISTANT_HISTORY_TOKEN_BUDGET", default=512, minimum=0
            ),
            history_recent_turns=_env_int(
                "ASSISTANT_HISTORY_RECENT_TURNS", default=4, minimum=0
            ),
            max_rows=_env_int("ASSISTANT_MAX_ROWS", default=200, minimum=1),
            sql_generation_mode=sql_generation_mode,
            token_count_endpoint=(
                _validate_url("TOKEN_COUNT_ENDPOINT", token_endpoint)
                if token_endpoint
                else None
            ),
            token_count_encoding=_first_env(
                "ASSISTANT_TOKEN_COUNT_ENCODING",
                "TOKEN_COUNT_ENCODING",
                default="cl100k_base",
            ),
            integration_path=_first_env('CPEA_PROFILE_PATH', default='') or None,
            deployment_file=_first_env('CPEA_DEPLOYMENT_FILE', default='') or None,
            datasource_id=(_get_env('CPEA_DATASOURCE_ID') or '').strip() or None,
            sqlserver=SQLServerSettings(
                connection_string=(_get_env('CPEA_SQLSERVER_CONNECTION_STRING') or '').strip(),
                connect_timeout_seconds=_db_timeout('CPEA_SQLSERVER_CONNECT_TIMEOUT_SECONDS', 5),
                query_timeout_seconds=_db_timeout('CPEA_SQLSERVER_QUERY_TIMEOUT_SECONDS', 30),
                freetds_config_file=_first_env('FREETDSCONF', 'FREETDS', default='') or None,
            ),
        )

        if result.request_timeout_seconds <= 0:
            raise ValueError('ASSISTANT_LLM_TIMEOUT_SECONDS must be positive')
        if not 0 < result.top_p <= 1:
            raise ValueError('ASSISTANT_LLM_TOP_P must be > 0 and <= 1')
        if result.max_output_tokens != -1 and result.max_output_tokens < 64:
            raise ValueError('ASSISTANT_LLM_NUM_PREDICT must be -1 or >= 64')
        if result.output_token_reserve + result.context_safety_tokens >= result.context_window:
            raise ValueError('output and safety tokens must be less than context window')
        return result


def _db_timeout(name: str, default: int) -> int:
    raw = _get_env(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f'{name} must be a positive integer') from None
    if value <= 0:
        raise ValueError(f'{name} must be a positive integer')
    return value
