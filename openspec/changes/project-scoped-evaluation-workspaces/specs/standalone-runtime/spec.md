## MODIFIED Requirements

### Requirement: Installable standalone product

The product SHALL provide `pyproject.toml`, a dependency lockfile, a documented supported Python version, and an installable `cpea` package under `src/`. Runtime imports MUST be usable without the original project's `assistant` or `app` packages and without adding the source checkout to PYTHONPATH. The general wheel MUST NOT bundle customer projects or silently select a synthetic profile; tests and examples SHALL select an external synthetic profile explicitly.

#### Scenario: Clean installed execution
- **WHEN** the built wheel is installed into a clean environment with documented dependencies and imported from a working directory outside the checkout
- **THEN** the package, API app factory, CLI and configured graph factory are importable without the original project
- **AND** customer project data is absent from the wheel, and starting a runtime without an explicit profile produces an actionable diagnostic

### Requirement: Explicit configuration sources

The product SHALL load configuration at startup with the order process environment, explicitly selected env file, and documented defaults. It MUST NOT load an ancestor `.env` or establish network connections as an import side effect. A production runtime without an explicitly selected valid integration profile MUST fail with an actionable diagnostic instead of silently loading the bundled synthetic demo. Invalid values and missing profile configuration SHALL produce actionable diagnostics without secret values. Synthetic profiles MAY be supplied explicitly for tests and examples.

#### Scenario: Environment precedence
- **WHEN** both the process environment and an explicitly selected env file define the same supported non-identity setting
- **THEN** the process environment value takes precedence and the documented legacy variable aliases retain their specified order

#### Scenario: Ancestor environment is ignored
- **WHEN** an ancestor directory contains a `.env` and no env file has been explicitly selected
- **THEN** its values are not loaded and importing the package sends no model or database request

#### Scenario: Missing profile selection
- **WHEN** a production entry point starts without an explicit profile or project binding
- **THEN** it fails before model or database access with a diagnostic describing how to select a profile

#### Scenario: Explicit synthetic example
- **WHEN** a test or example explicitly supplies an approved synthetic profile
- **THEN** the runtime can load it without relying on an implicit production fallback
