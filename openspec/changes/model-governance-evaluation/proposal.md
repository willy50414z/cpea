## Why

The existing evaluation tools cannot compare complete model-driven query flows across local and cloud providers or explain each model call behind a result. A repeatable, private evaluation suite is needed to assess correctness, security, stability, and efficiency before selecting models for the next PoC phase.

## What Changes

- Introduce separate JSON case and model configuration files. Cases carry stable IDs, category (`simple`, `complex`, `ambiguous`, `security`), difficulty (`easy`, `medium`, `hard`), and machine-checkable expected outcomes.
- Add end-to-end multi-model evaluation and `.env`-selected single-model repeat-run stability evaluation; retire the old frozen-prompt comparison runner and CLI.
- Support the planned matrix: local `gemma4:e4b`, `qwen3:4b`, `gemma4:latest`, `qwen3:8b`; Azure `DeepSeek-V4.1-Flash`; and Google `Gemini 3.8 Flash`. Treat cloud names as configurable deployment/model identifiers verified at execution preflight.
- Record each LLM attempt with provider, node, effective model and quantization identity when available, request/response, token usage, timing, concurrency, effective generation settings, and clean-worktree Git SHA. Produce case/model results with `pass`, `fail`, or `error`, plus CSV and Markdown reports.
- Require private, Git-ignored run output and redact secrets in shareable reports. Remove the obsolete ignored files under `evaluations/private/legacy/` and update references, while retaining the separately documented archival backup and provenance.
- Validate the implementation with offline stubs and fixtures only. Do not invoke a live local or cloud model as part of this change's delivery checks.

## Capabilities

### New Capabilities

- `model-governance-evaluation`: Case/model inputs, provider selection, repeatable runs, call-level provenance, grading, and private reports.

### Modified Capabilities

- None. The existing quality-tooling separation and provenance requirements remain in force.

## Impact

The change affects `evaluations/` datasets, runners, metadata and documentation; the LLM factory/settings and call instrumentation; provider-specific optional dependencies; and offline evaluation tests. It does not add a production database driver or authorize live customer-data evaluation. Generated artifacts remain under the ignored `artifacts/` tree.
