## ADDED Requirements

### Requirement: Separate validated evaluation inputs

The evaluation system SHALL read versioned JSON case data independently from versioned JSON model configuration. Each case MUST contain a unique `case_id`, a category from `simple`, `complex`, `ambiguous`, `security`, a difficulty from `easy`, `medium`, `hard`, a question, and explicit expected behavior. Case status MUST be produced by execution rather than stored as fixed input. The model matrix SHALL represent the four local and two cloud targets described in the proposal without embedding credentials.

#### Scenario: Valid independent inputs
- **WHEN** a valid case file and model matrix are supplied to comparison mode
- **THEN** the runner builds one evaluation target for each selected case/model combination without changing the case expectations

#### Scenario: Invalid input fails before calls
- **WHEN** a case ID is duplicated, an enum or expectation is invalid, or a model entry is incomplete
- **THEN** preflight reports the specific input error and issues no model call

### Requirement: Comparison and single-model stability modes

The evaluation system SHALL support end-to-end comparison across configured models and repeated stability evaluation of one model selected from an explicit `.env` file. Both modes SHALL use the same case checks and result format. Live model calls MUST require an explicit opt-in. The obsolete frozen-final-prompt comparison CLI and modules SHALL be removed, and its former results MUST NOT be reported as end-to-end scores.

#### Scenario: Stability run from environment
- **WHEN** a maintainer selects a case file, an `.env` file, and three repetitions
- **THEN** the runner selects the environment model and produces three independent result records per case with consistent run and model identity

#### Scenario: Offline verification
- **WHEN** the evaluation tests use injected stub models and fake execution dependencies
- **THEN** input parsing, grading, call capture, and report generation complete without contacting local or cloud model services

#### Scenario: Live mode not requested
- **WHEN** a runner is invoked without the live opt-in or an injected offline model factory
- **THEN** it makes no model request and clearly explains how to select an execution mode

#### Scenario: Retired comparison entry point
- **WHEN** the installed package scripts and evaluation modules are inspected
- **THEN** `cpea-model-eval` and the old fixed-prompt comparison modules are absent, while `cpea-governance-eval compare` remains available

### Requirement: Local and cloud model identity

The runner SHALL support configurable local Ollama models, Azure-hosted model deployments, and Google-hosted models through provider adapters. It MUST distinguish provider family from transport and record requested and resolved model identity where available. It MUST NOT fabricate quantization, token usage, or unsupported generation settings.

#### Scenario: Planned model matrix
- **WHEN** the supplied matrix contains `gemma4:e4b`, `qwen3:4b`, `gemma4:latest`, `qwen3:8b`, Azure `DeepSeek-V4.1-Flash`, and Google `Gemini 3.8 Flash`
- **THEN** every entry is parsed as an independent target with its declared provider and its deployment-specific identity is checked at live preflight

#### Scenario: Optional provider unavailable
- **WHEN** a selected cloud provider lacks a required optional dependency or deployment setting
- **THEN** preflight identifies that model and the missing capability without silently substituting another provider

### Requirement: Complete call-level provenance

The runner SHALL record every LLM request attempt, including structured schema-matching calls, retries, final-answer calls, optional warmups, and failures. Each record MUST link to a run, case, model, repetition, logical `node_name`, and unique call ID. It MUST include provider, requested/resolved model name, quantization or an explicit unavailable marker, request/response or error, input/output tokens with source, elapsed time, configured and observed concurrency, effective `num_ctx`, `max_token`, temperature, top_p, and full Git SHA. Unavailable measurements SHALL be null and SHALL NOT be represented as zero.

#### Scenario: Structured-output retry
- **WHEN** a schema-matching call fails validation and is retried
- **THEN** the trace contains separate ordered records for both attempts, including the first failure and each attempt's effective request and response

#### Scenario: Provider omits usage
- **WHEN** a provider response has no token or quantization metadata
- **THEN** those fields remain null with provenance explaining the absence, and aggregate reports do not invent a measured value

### Requirement: Clean and private run provenance

Before a live run, the runner MUST require a clean Git index and worktree, including no untracked non-ignored files, and MUST capture the full `HEAD` SHA. It MUST verify that its newly created run output is Git-ignored, create run-specific paths without overwrite, and exclude credential values from metadata and shareable reports. Raw request/response artifacts SHALL be treated as private data.

#### Scenario: Dirty worktree
- **WHEN** a tracked file is changed or a non-ignored untracked file exists
- **THEN** live preflight stops before any model request and identifies the clean-worktree requirement

#### Scenario: Output not ignored
- **WHEN** the chosen output location is not ignored by Git
- **THEN** the runner stops before recording any raw prompt or response there

### Requirement: Case grading and reproducible reports

The runner SHALL evaluate each case/model/repetition against explicit checks and assign a final status of exactly one of `pass`, `fail`, or `error`. A completed but incorrect response SHALL be `fail`; a transport, timeout, parsing, or infrastructure failure SHALL be `error`. Cases needing human judgment SHALL have a null final status and a separate pending-review state until reviewed, rather than receiving a fabricated pass. Security cases SHALL inspect both expected refusal or constraint and absence of forbidden SQL or data access. The runner SHALL derive a UTF-8 CSV summary, Markdown overview, and per-case Markdown reports from private machine-readable records, with pass, error, and pending-review denominators stated separately.

#### Scenario: Safety failure with fluent answer
- **WHEN** a response sounds plausible but violates a forbidden SQL or access expectation
- **THEN** the case fails with the violated check and the report links to the relevant call and execution evidence

#### Scenario: Model request error
- **WHEN** a model request times out after earlier calls succeeded
- **THEN** the repetition is `error`, earlier call records are retained, and the error is counted separately from incorrect completions

#### Scenario: Report regeneration
- **WHEN** the reporter is rerun against existing normalized call and result records
- **THEN** it reproduces the same CSV and Markdown findings without model requests or overwriting unrelated runs

### Requirement: Retire obsolete legacy evaluation files

The implementation SHALL remove the obsolete ignored JSONL files under `evaluations/private/legacy/` while preserving the separately archived original PoC backup and its manifest. Documentation SHALL identify the retained archive rather than claim that the removed working files remain in place. Existing supported query reliability evaluation and its distributable synthetic dataset SHALL continue to work.

#### Scenario: Legacy cleanup
- **WHEN** the new evaluation suite is delivered
- **THEN** the obsolete private legacy working files are absent, the documented original archive remains, and the existing query reliability runner still accepts its synthetic dataset
