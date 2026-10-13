# quality-tooling Specification

## Purpose

Define reproducible offline regression, model evaluation, asset distribution and delivery documentation practices for the standalone refactor.

## Requirements

### Requirement: Frozen deterministic behavior baseline

Before broad module migration, the project SHALL record reproducible offline cases for the established compiler, field/scope/time policies, supported/unsupported requests, trace, injected execution, row truncation and execution failure. Tests SHALL use stub LLMs, synthetic contracts and fake executors, without live DB or ERP API connections. Known broken entry points SHALL be recorded as explicit repair targets.

#### Scenario: Offline regression gate
- **WHEN** the migrated deterministic suite runs without model, database or ERP API services
- **THEN** preserved cases validate equivalent behavior and intentional entry-point repairs and unavailable-executor behavior are separately identifiable

### Requirement: Evaluation assets and outputs separated

The project SHALL separate tests, model evaluation runners, fixed datasets, retained baselines and generated evaluation outputs. Generated outputs, secrets, local environments and bytecode SHALL be excluded from routine source/distribution artifacts by the documented ignore and packaging rules.

#### Scenario: Evaluation output location
- **WHEN** a runner executes with its documented default output configuration
- **THEN** it writes a run-specific output under the configured artifact location without overwriting the fixed dataset or retained baseline

### Requirement: Reproducible evaluation metadata

Evaluation outputs SHALL record run ID, timestamp, product version or source fingerprint, model/provider identity, non-secret configuration identity, contract version/fingerprint and dataset fingerprint. Live model evaluation SHALL be opt-in. DB-dependent evaluation SHALL report missing injected dependencies at preflight, and fake-generated records MUST NOT be presented as real-model baselines.

#### Scenario: Metadata without credential exposure
- **WHEN** an evaluation record is produced with settings containing credentials
- **THEN** the record identifies relevant non-secret settings and versions while omitting credential values

#### Scenario: Model service unavailable
- **WHEN** a real-model run is not performed because its service is unavailable
- **THEN** the delivery report records that limitation and relies on the offline regression gate without claiming a real-model pass rate

### Requirement: Customer asset distribution boundary

The project SHALL inventory existing contracts, samples and historical results before migration, distinguishing approved private assets from distributable synthetic fixtures. Customer samples, raw prompts, result rows and secret-bearing settings MUST NOT be included in the general product wheel. Authorized private assets and meaningful historical baselines SHALL have a documented preservation destination and provenance.

#### Scenario: Inspect built distribution
- **WHEN** the wheel and documented private-asset inventory are inspected
- **THEN** the wheel contains only approved code and synthetic resources, and retained private baseline assets have an explicit preservation record

### Requirement: Refactoring delivery documentation

The project SHALL provide `docs/refactoring_plan.md` with scope, dependency-ordered phases, acceptance gates, migration commands, breaking changes and deferred work. Architecture and enterprise design SHALL be linked from it. `docs/dev_plan.md` SHALL remain the existing functional PoC plan and MUST NOT implicitly authorize its feature work within this change.

#### Scenario: Scope and status review
- **WHEN** a maintainer reads the refactoring plan
- **THEN** they can distinguish preserved existing functionality, completed structural work, design-only enterprise capabilities and deferred DB/API implementation
