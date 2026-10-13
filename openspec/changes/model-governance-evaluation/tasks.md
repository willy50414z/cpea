## 1. Inputs and execution modes

- [x] 1.1 Define and validate versioned JSON case and model schemas, including unique IDs, allowed categories/difficulties, typed expectations, provider identity, and credential-free configuration.
- [x] 1.2 Add a distributable synthetic governance case file and a separate six-model configuration file using the corrected `qwen3:4b` target.
- [x] 1.3 Add comparison and `.env`-selected repeated stability CLI modes with explicit live opt-in, injectable offline model factory, and shared result schema.

## 2. Providers and provenance

- [x] 2.1 Extend provider configuration/factory for optional Azure and Google adapters, effective top_p and generation parameters, and clear preflight diagnostics without exposing credentials.
- [x] 2.2 Implement clean-worktree/HEAD-SHA preflight and verify new run output paths are Git-ignored and never overwritten.
- [x] 2.3 Capture every LLM attempt across structured schema matching, repairs, warmup, and answer synthesis with node, provider/model identity, effective parameters, token provenance, request/response, duration, concurrency, and error.
- [x] 2.4 Normalize available provider usage and local quantization/model digest while leaving unavailable metrics null and recording why.

## 3. Grading and reporting

- [x] 3.1 Implement deterministic expectation checks for supported/rejected queries, plan/SQL constraints, ambiguity, answer evidence, and security, with `pass`/`fail`/`error` and pending human review kept distinct.
- [x] 3.2 Persist correlated private call/result JSONL and derive UTF-8 CSV, Markdown overview, and per-case Markdown reports with separate denominators and redacted shareable content.
- [x] 3.3 Add report regeneration from existing JSONL without model requests or overwrite of unrelated runs.

## 4. Cleanup and offline verification

- [x] 4.1 Confirm the original PoC archive and manifest, remove the five ignored `evaluations/private/legacy/*.jsonl` working files, and update documentation that cites their old location.
- [x] 4.2 Add stub/fake-executor tests for both CLI modes, invalid input, clean/ignored preflight, retries, missing provider usage, safety grading, and report output; run only offline checks.
- [x] 4.3 Verify existing `cpea-query-eval` remains intact, remove the obsolete frozen-prompt comparison CLI and modules, document the live-run command, and explicitly state that no real model was called for this delivery.
