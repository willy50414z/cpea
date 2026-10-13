## ADDED Requirements

### Requirement: Installable standalone product

The product SHALL provide `pyproject.toml`, a dependency lockfile, a documented supported Python version, and an installable `cpea` package under `src/`. Runtime imports and packaged resources MUST be usable without the original project's `assistant` or `app` packages and without adding the source checkout to PYTHONPATH.

#### Scenario: Clean installed execution
- **WHEN** the built wheel is installed into a clean environment with documented dependencies and imported from a working directory outside the checkout
- **THEN** the package, API app factory, CLI and configured graph factory are importable without the original project
- **AND** authorized bundled synthetic resources are available, while external integration paths are resolved through explicit configuration

### Requirement: Explicit configuration sources

The product SHALL load configuration at startup with the order process environment, explicitly selected env file, and documented defaults. It MUST NOT load an ancestor `.env` or establish network connections as an import side effect. Invalid values and missing profile configuration SHALL produce actionable diagnostics without secret values.

#### Scenario: Environment precedence
- **WHEN** both the process environment and an explicitly selected env file define the same supported setting
- **THEN** the process environment value takes precedence and the documented legacy variable aliases retain their specified order

#### Scenario: Ancestor environment is ignored
- **WHEN** an ancestor directory contains a `.env` and no env file has been explicitly selected
- **THEN** its values are not loaded and importing the package sends no model or database request

### Requirement: Composition of existing services

The product SHALL provide a bootstrap boundary for injecting settings, catalog, retrieval, LLM and the optional externally supplied SQL executor. The API and CLI MUST use this boundary instead of choosing a fixed enterprise datasource within the core. SQL generation SHALL remain available when no executor is configured.

#### Scenario: Explicit injected dependencies
- **WHEN** bootstrap receives a synthetic profile, stub LLM and fake executor in an offline test
- **THEN** API and CLI use those supplied dependencies without importing `app.core.external_db` or defaulting to `JHD`

### Requirement: Unconfigured execution is explicit

An execution-dependent entry point SHALL detect a missing SQL executor or datasource binding before issuing generation or execution calls. HTTP query mode MUST return HTTP 503 with a stable dependency-unavailable diagnostic, CLI execution mode MUST exit nonzero, and DB-dependent evaluation MUST fail its preflight clearly. A fake executor MUST NOT be used as a production default.

#### Scenario: Generation-only deployment
- **WHEN** a standalone deployment has a valid generation configuration and no SQL executor
- **THEN** SQL generation can run, but query execution returns the documented unavailable diagnostic before calling the LLM or executor

### Requirement: Documented usable entry points

The product SHALL expose independently usable API app, CLI and LangGraph factory entry points, with commands and settings documented for the installed package. The LangGraph configuration MUST reference an existing factory and product-local dependencies and explicit env configuration.

#### Scenario: Graph factory resolution
- **WHEN** the documented graph configuration is inspected and its factory is imported with offline injected dependencies
- **THEN** the configured callable exists and builds the current SQL-generation graph without requiring an ancestor project or a live model request
