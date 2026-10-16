## MODIFIED Requirements

### Requirement: Evaluation assets and outputs separated

The project SHALL separate deterministic tests, shared model evaluation runners, project-scoped fixed datasets, retained baselines and generated evaluation outputs. Each private project SHALL use one fixed case set with stable case IDs and categories; accuracy and repeat-run stability SHALL use that same case set with different run counts. New generated outputs SHALL reside in a unique run directory under the selected project's private artifact location and MUST NOT overwrite cases or prior runs. Generated outputs, secrets, local environments and bytecode SHALL be excluded from routine source/distribution artifacts by the documented ignore and packaging rules.

#### Scenario: Evaluation output location
- **WHEN** a project evaluation runs with its documented default output configuration
- **THEN** it writes a run-specific output under that project's private artifact location without overwriting the fixed dataset or retained baseline

#### Scenario: One case set for accuracy and stability
- **WHEN** a project evaluates the same case set with one run and then with repeated runs
- **THEN** both reports use the same case IDs and expected checks, while only the repeated run reports stability measures

### Requirement: Reproducible evaluation metadata

Evaluation outputs SHALL record a run ID composed of UTC date-time and Git short SHA, product version or source fingerprint, selected project ID, effective model/provider/deployment identity, non-secret configuration identity, contract version/fingerprint, dataset fingerprint, requested and completed repetitions, and per-call latency and provider-reported token usage when available. Missing token usage MUST remain unknown rather than being counted as zero. The project-facing evaluation command SHALL perform real-model evaluation; offline stub results MUST NOT be presented as real-model baselines. DB-dependent evaluation SHALL report missing dependencies at preflight.

#### Scenario: Metadata without credential exposure
- **WHEN** an evaluation record is produced with settings containing credentials
- **THEN** the record identifies relevant non-secret settings and versions while omitting credential values

#### Scenario: Missing provider token usage
- **WHEN** a provider does not return token counts for a call
- **THEN** per-call usage remains unknown and aggregate usage is marked incomplete instead of estimating zero

#### Scenario: Model service unavailable
- **WHEN** a real-model run is not performed because its service is unavailable
- **THEN** the delivery report records that limitation and relies on the offline regression gate without claiming a real-model pass rate

## ADDED Requirements

### Requirement: Project evaluation command and report

The product SHALL provide a project evaluation command whose routine user inputs are project ID, run count and concurrency. The command SHALL select the project's `.env`, profile and single case set, execute against the configured real model, and create private run records plus summary reports in the project's artifact directory. Reports SHALL distinguish planned and completed attempts, pass, fail and error outcomes, category summaries and repeat-run consistency. Raw prompts, responses and result rows MUST NOT be embedded in shareable summary reports.

#### Scenario: Three-argument project run
- **WHEN** an operator invokes the documented command with a valid project, positive runs and positive concurrency
- **THEN** no separate dataset, env-file, model, live-mode or output-directory argument is required

#### Scenario: One-run report
- **WHEN** the project runs each case once
- **THEN** the report provides correctness outcomes and does not claim repeated-run stability

#### Scenario: Private report generation
- **WHEN** a live project evaluation completes or stops early
- **THEN** its output directory contains immutable raw run records and generated summaries that show completed versus planned attempts without exposing raw content in the summaries

### Requirement: Existing asset and result migration

Implementation SHALL inventory and migrate current private GMS2 and Retail profile files to project directories without silently changing contract contents. Existing GMS2 reliability and colloquial cases SHALL be reviewed before consolidation into one project case set; inconsistent expectations MUST be corrected or withheld from the formal baseline. Existing historical outputs and the original PoC archive SHALL retain their original provenance and MUST NOT be relabeled as new-format project runs. Current path references in active code, package rules, tests and operational documentation SHALL be updated.

#### Scenario: Private profile migration
- **WHEN** a migrated profile is compared to its source inventory
- **THEN** every preserved file has matching content or an explicitly documented, reviewed change and the catalog still loads

#### Scenario: Historical result preservation
- **WHEN** the new project layout is activated
- **THEN** prior global evaluation and stability outputs remain readable at their documented historical locations and are not counted as new project runs
