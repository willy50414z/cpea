## ADDED Requirements

### Requirement: Single-call candidate mapping

The workflow SHALL supply the complete original request and existing View policy, including available samples, field descriptions, aliases, capabilities and term mappings, directly to the linking LLM. It MUST NOT call an independent FactDraft extraction stage. A successful first candidate SHALL require one model invocation; bounded repair and candidate fallback remain allowed.

#### Scenario: Successful direct mapping
- **WHEN** the first candidate receives a valid complete model result
- **THEN** it produces the approved plan using one model call and no preliminary fact extraction

### Requirement: View-satisfied requirements

SchemaLinkDraft SHALL contain original request facts, SQL links, View-satisfied time facts with explanations, ambiguity and unresolved facts. The LLM SHALL decide whether a time requirement is satisfied by the View without a SQL filter. Python MUST NOT discard facts based on fixed current-time words.

#### Scenario: Current inventory
- **WHEN** the model maps a current inventory request to a current snapshot View
- **THEN** the current-time fact is recorded as View-satisfied with a reason and generates no invented date filter

#### Scenario: Unsupported historical request
- **WHEN** the model identifies that a historical snapshot cannot be answered by the supplied current-only View
- **THEN** it reports unresolved requirements and the workflow returns no SQL

### Requirement: Preserve deterministic guards

The workflow SHALL verify that facts and link references occur in the request, every returned required fact is linked or legitimately recorded as View-satisfied, columns and roles satisfy the existing contract, and filters are grounded in the corresponding request fact or a triggered catalog mapping. It MUST preserve scope rules, conflict rejection, QueryPlan and SQL validation, single-View compilation and bounded retries. It MUST NOT inject or replace links using business keywords, fixed column sets or identifier/year/quarter regex. View-satisfied records MUST NOT bypass entity, metric or dimension requirements.

#### Scenario: Invalid or incomplete model output
- **WHEN** a draft invents a fact or filter, omits a returned required fact, uses an invalid column/operator, or retains unresolved requirements
- **THEN** it is repaired within the existing bounded retry policy or rejected without partial SQL

#### Scenario: Renamed columns
- **WHEN** a contract uses different physical names but supplies sufficient descriptions and samples
- **THEN** the model can map to those columns without workflow code changes or fixed business-name rules

#### Scenario: Cross-View links
- **WHEN** a draft requires a JOIN or references a different View
- **THEN** it is rejected and no executable cross-View SQL is produced

### Requirement: Minimal contract and trace changes

The change SHALL reuse existing catalog formats, QueryFact, SchemaLink and state/trace mechanisms. It MUST NOT require new sample IDs, evidence unions, semantic metadata migrations or independent evaluation tools. Samples SHALL inform model interpretation but MUST NOT alone authorize invented values absent from the request or explicit catalog mappings.

#### Scenario: Existing profile
- **WHEN** an existing valid profile is loaded after this change
- **THEN** it requires no migration and its existing policy is supplied to the model

#### Scenario: Trace inspection
- **WHEN** mapping succeeds
- **THEN** the trace includes the model's facts, links and View-satisfied explanation without a separate evidence subsystem
