# erp-integration-contracts Specification

## Purpose

Define configurable, versioned ERP integration contracts and external executor boundaries that preserve governed SQL generation behavior without adding database or ERP API implementations.

## Requirements

### Requirement: Configurable versioned integration profiles

The product SHALL load an explicit integration profile containing a manifest, contract version and allowlisted catalog. Enterprise deployment configuration SHALL bind a profile and datasource identifier. Physical schema names MAY remain in profile data, but shared catalog and retrieval code MUST NOT require `gms2` or assume the schema name identifies an enterprise.

#### Scenario: Alternate physical schema
- **WHEN** the product loads a valid synthetic profile whose physical schema differs from `gms2`
- **THEN** its resources are available to both lexical and vector retrieval according to that profile's allowlist
- **AND** core code changes are not required to select the alternate profile

### Requirement: Preserve governed view policies

The product SHALL preserve each migrated View's allowlist membership, field capabilities, aggregations, filter operators, term mappings, scope rules and temporal semantics. Existing single-View MSSQL compilation and rejection rules MUST remain the behavior baseline. Unconfirmed grain or business meanings MUST NOT be silently reinterpreted during migration.

#### Scenario: Existing policy rejection
- **WHEN** a plan uses a disallowed field capability or violates a preserved scope or temporal rule
- **THEN** it is rejected with traceable validation information and no executable SQL is returned

#### Scenario: Cross-view request
- **WHEN** a request requires a cross-View JOIN unsupported by the current generation capability
- **THEN** the migrated workflow remains unsupported rather than introducing a new JOIN behavior

### Requirement: Bounded contract resources and cache identity

The catalog loader SHALL resolve resources within the explicitly configured profile root and reject references escaping it after path and link resolution. API request payloads MUST NOT control arbitrary resource file paths. Retrieval indexes and cache identity SHALL include profile identity, contract version or content fingerprint, and relevant retrieval/embedding settings.

#### Scenario: Profile path escape
- **WHEN** a catalog references a relative path or symlink whose resolved target lies outside its authorized profile root
- **THEN** the loader rejects the resource before reading it

#### Scenario: Profile or contract change
- **WHEN** two profiles use identical model settings but different resources, or a profile contract changes
- **THEN** retrieval does not reuse an index for the other profile or stale contract contents

### Requirement: External SQL executor boundary

Application services SHALL consume a catalog port and an externally supplied SQL executor contract instead of a concrete original-project database module. The execution contract SHALL preserve datasource, compiled SQL, columns and rows semantics, existing single-attempt behavior, row bounding and trace propagation. This change MUST NOT add a database driver, connection pool, transaction layer, new execution implementation, schema or migration.

#### Scenario: Injected executor behavior preservation
- **WHEN** an offline test injects a fake executor and explicit datasource binding
- **THEN** the executor receives the binding and approved SQL once, and returned rows retain existing truncation and trace behavior

#### Scenario: Executor failure
- **WHEN** the injected fake executor fails
- **THEN** the application records the execution failure in the established trace and does not ask an LLM to repair or re-execute SQL

### Requirement: ERP API integration design

The design documentation SHALL define the future ERP read-operation boundary, operation allowlist, input validation, paging, credentials reference and result/provenance mapping. This change MUST NOT implement a real ERP API adapter, runtime operation registry or generic ERP query language.

#### Scenario: API design scope review
- **WHEN** reviewers inspect the integration design and task list
- **THEN** SQL and API responsibilities are explicit, API implementation is marked deferred, and no task requires calling a customer's ERP API
