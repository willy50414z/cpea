## Context

`cpea-query-eval` already repeats SQL-planning cases with one `.env`-selected runtime. `cpea-model-eval` replays a shared final answer prompt after preparing SQL/context with one model, so its records do not measure each candidate's full flow. `run_metadata` records a source hash, but not the requested Git SHA; model comparison records only final-answer streaming metrics. Product settings currently select Ollama or llama.cpp, and the workflow can make multiple structured schema-matching calls, including repairs, before answer synthesis. Generated results and private legacy data are outside Git; the repo also has a separate archived original PoC backup.

## Goals / Non-Goals

**Goals:**
- One versioned JSON case file and a separate versioned JSON model matrix, with validation before model calls.
- An end-to-end comparison mode and a `.env`-selected single-model stability mode using the same case evaluator, call recorder, and reports.
- Capture every model attempt, including retries, warmups if enabled, failures, and final answers, with reliable provenance and non-fabricated measurements.
- Offline implementation verification without contacting local or cloud model services.

**Non-Goals:**
- Running the proposed live model matrix during implementation or claiming a measured pass rate.
- Adding a production SQL executor or making raw evaluation traces into a durable audit service.

## Decisions

### Inputs and runner modes

Use `evaluations/datasets/governance_cases.json` as a distributable synthetic seed and `evaluations/config/models.json` as a configurable matrix. Cases have a stable `case_id`, category, difficulty, question, expected behavior, and applicable checks; the fixed case file has no run status. The matrix lists provider (`local`, `azure`, `gcp`), model/deployment ID, local transport or cloud adapter, optional node/endpoint reference, and effective generation defaults. Keep credentials in environment variables, never JSON. Validate unique IDs, enums, expected-check schemas, and model entries at preflight. A private case path may replace the synthetic file.

Provide one evaluation entry point with `compare --cases ... --models ...` and `stability --cases ... --env-file ... --runs N`. Stability uses the existing `AssistantSettings.from_env` precedence and a single selected model, like `query_reliability.py`; matrix compare instantiates an isolated runtime/settings per model. Default to serial execution (`concurrency=1`) and require an explicit positive concurrency setting for load experiments. A live model request requires an explicit live-run option; offline stub tests use injected model factories. Retire the old final-prompt replay CLI and modules because the new comparison entry point owns model comparisons.

Alternative considered: combine cases and model configuration in one JSON file. Separation lets the same fixed cases run against both the matrix and a `.env`-selected model without duplicating or silently changing expectations.

### Provider and call boundary

Extend the LLM factory behind the existing `BaseChatModel` boundary for Azure and Google, with optional provider dependencies and provider-specific preflight. Preserve the deployment's endpoint and credential injection rules. Adapt response and usage metadata into one normalized call record; preserve provider-reported raw identity/usage fields where safe. `node_name` is the logical stage (`schema_match`, `answer_synthesis`, `warmup`) and `attempt_index` distinguishes retries. Instrument the model call boundary used by both `with_structured_output(...).invoke(...)` and ordinary `invoke`/`stream`, so validation repairs and provider exceptions are visible. Correlate records using run, case, model, repetition, and call IDs. Do not count embedding or reranking API calls as LLM calls; their duration remains in stage metrics.

Each record stores provider family, transport, requested and resolved model identity, quantization or `null` with an unavailable reason, serialized request/response, input/output tokens with provenance (`provider` or `estimated`), elapsed and optional TTFT time, configured and observed in-flight concurrency, `num_ctx`, `max_token`, temperature, top_p, Git SHA, timing, and error details. Use effective values passed to the provider, not only source config. Missing usage stays `null`; estimated values are clearly marked. Optional cost calculations require a versioned pricing snapshot and are kept separate from provider-billed values.

Alternative considered: instrument only the runner's final `stream` call. It would miss SQL/schema matching, retries, and ordinary answer calls, and would make end-to-end efficiency figures misleading.

### Reproducibility, grading, and reports

Before any live call, require a clean Git worktree, including staged, unstaged, and untracked non-ignored files; record the full `HEAD` SHA and retain the existing source, dataset, profile, and settings fingerprints. Resolve the run directory under ignored `artifacts/evaluations/<run-id>/`, verify it is ignored by Git, and create files without overwriting existing output. The preflight itself must not modify tracked files.

Represent each result as one case/model/repetition record. `pass` means every applicable deterministic check passed; `fail` means a completed response violated an expectation; `error` means the attempt could not be evaluated because of provider, timeout, parse, or infrastructure failure. Checks may inspect support/rejection, allowed view, query plan, SQL safety, answer claims/citations, and expected clarification. Cases requiring judgment retain explicit review fields and cannot be auto-passed. Security cases must verify both the refusal/constraint and absence of forbidden SQL or data access. Aggregate error rate separately from pass rate, and report the denominator. A model does not pass an end-to-end case merely because the final answer sounds correct when the SQL stage failed.

Write private `calls.jsonl` and `results.jsonl` as source data, then derive a UTF-8 CSV summary and a Markdown overview plus one report per `case_id`. CSV includes run/case/model/repetition/status/reasons and available token/timing aggregates. Markdown shows expected behavior, per-model results, evidence and links to call IDs, with credentials and known secret fields redacted. Raw request/response is retained only in ignored private artifacts and documented as sensitive; never include it in a distributable dataset or published report by default.

Alternative considered: write only Markdown. Normalized JSONL preserves failed attempts and supports regeneration of CSV/Markdown without rerunning expensive models.

### Legacy data

Remove the five ignored JSONL files currently under `evaluations/private/legacy/` as authorized. Do not remove `artifacts/baseline/original-poc.zip` or its manifest; update docs that describe the legacy location so the retained archive is the stated provenance source. Existing supported `cpea-query-eval` behavior and the synthetic `evaluations/datasets/query_reliability.jsonl` remain available.

## Risks / Trade-offs

- [Cloud deployment names, token accounting, and parameter support vary] → Treat model identifiers as configured targets; probe capabilities at preflight, store resolved IDs and nullable unsupported settings, and do not infer quantization for cloud models.
- [Instrumented structured output may hide raw provider responses] → Wrap the underlying chat model or callback boundary and verify retry/failure capture with stub tests.
- [Raw prompts and results can contain customer data] → Keep artifacts ignored and private, omit secrets from metadata and shareable reports, and use synthetic fixtures for repository tests.
- [Concurrent local models affect latency and throughput] → Default to serial runs and record both concurrency setting and observed in-flight count; label any load run separately.
- [Deletion of ignored legacy files is not reversible through Git] → Confirm the documented original archive and manifest exist during implementation before removing those five files.

## Migration Plan

Add the new runner and formats without changing existing CLI defaults. Update documentation for the new modes and the legacy archive location. Keep old evaluation output readable; no automatic conversion is required. If a provider adapter is unavailable, its preflight reports an explicit dependency or configuration error without issuing calls to other models.

## Open Questions

The exact Azure deployment name, Google model identifier, provider-supported token usage fields, and deployment-specific price schedule must be verified in the target environments before live evaluation. These do not block offline implementation because the matrix uses configurable identifiers and nullable measurement fields.
