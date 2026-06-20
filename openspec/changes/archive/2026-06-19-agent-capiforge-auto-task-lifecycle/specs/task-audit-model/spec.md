# Delta for Task Audit Model

## MODIFIED Requirements

### Requirement: Task-centered operations

The system MUST treat tasks as the central operational entity. Every task MUST be justified by an audit, MUST have exactly one origin audit, and MAY link additional audits later. Automatically created lifecycle tasks MUST use an explicit audit-backed origin path, MUST record the lifecycle key and creator identity in justification metadata, and MUST remain same-project only.
(Previously: Tasks required one origin audit but did not define the audit-backed auto-create path for lifecycle reconciliation.)

#### Scenario: Create a justified task
- GIVEN a published audit identifies actionable work
- WHEN a task is created from that audit
- THEN the task stores that audit as its origin audit
- AND the task MAY accept later linked audits without replacing the origin

#### Scenario: Auto-create a lifecycle task
- GIVEN no reusable lifecycle task exists in the adopted project
- WHEN an allowed lifecycle wrapper creates a task
- THEN the task stores one audit-backed origin and lifecycle-key justification metadata
