# workflow-boundaries Specification

## Purpose

Define the existing SQL generation workflow, model ownership, API compatibility and shared parsing boundaries without introducing additional business workflows.

## Requirements

### Requirement: Named SQL generation workflow

The product SHALL place the existing SQL generation workflow under `workflows/text_to_sql/sql_generation.py` and preserve its retrieve-schema, match-candidates, compile-query and finalize node responsibilities. The workflow MUST NOT directly execute database queries or add new task orchestration, business workflows or cross-View JOIN capability.

#### Scenario: Generation-only responsibility
- **WHEN** the workflow processes an existing supported single-View case using offline dependencies
- **THEN** it returns the generation response, approved plan and trace without calling a database executor

### Requirement: Models separated by responsibility

The product SHALL keep core query concepts in domain models, HTTP request DTOs in the API interface, LLM draft models in workflow schemas, and service response/read models and traces in application models. Application and domain modules MUST NOT import API interface modules. Existing Pydantic validation semantics SHALL be preserved where model fields are migrated.

#### Scenario: Model dependency direction
- **WHEN** the migrated model dependency graph is inspected
- **THEN** API schemas can reference application/domain types while application/domain code has no reverse dependency on API schemas

### Requirement: HTTP and generation behavior compatibility

The product SHALL preserve `/api/assistant/sql` and `/api/assistant/query`, existing request fields and successful response serialization, and existing supported/unsupported and trace semantics. Internal namespace and command changes SHALL be documented. The explicitly unconfigured query-execution case SHALL follow standalone-runtime's unavailable contract.

#### Scenario: Existing API caller with injected executor
- **WHEN** an existing valid request is sent to the migrated API with offline injected dependencies
- **THEN** the route and successful payload retain the established request/response fields and trace information

#### Scenario: Unsupported generation
- **WHEN** the current workflow cannot satisfy all required request facts
- **THEN** the migrated generation response remains unsupported and retains rejection-stage and candidate diagnostics rather than returning partial SQL

### Requirement: Supported shared parsing boundary

The product SHALL provide the existing required JSON response parsing through an accessible, tested LLM parsing boundary used by answering and model evaluation. Evaluation MUST NOT invoke a missing or private graph parser.

#### Scenario: Existing answer draft parsing
- **WHEN** the evaluation runner processes an offline representative streamed answer response
- **THEN** it parses the established AnswerDraft format through the shared boundary without relying on `SQLGenerationWorkflow._parse_model`
