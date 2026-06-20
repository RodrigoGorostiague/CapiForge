# Delta for MCP CLI Surface

## ADDED Requirements

### Requirement: Public brief-audit create and publish operations

The system MUST expose deterministic public CLI and MCP operations to create a draft brief audit and publish it for the adopted project. These operations MUST return canonical audit references, MUST remain same-project and owner-local only, and MUST fail explicitly when required brief-audit fields or publication preconditions are missing.

#### Scenario: Create and publish a brief audit publicly
- GIVEN an adopted owner-local project and valid brief-audit fields
- WHEN an agent calls the public audit create and publish operations
- THEN the response returns the canonical published audit reference

#### Scenario: Reject incomplete or out-of-bound publish
- GIVEN the requested audit is missing required fields or targets another project
- WHEN publish is requested through the public surface
- THEN the system returns an explicit validation or authority error

## MODIFIED Requirements

### Requirement: Automatic agent lifecycle operations

The system MUST expose deterministic MCP and CLI lifecycle operations for start-time reconciliation and finish-time closure after MCP bootstrap is configured. Start operations MUST resolve the adopted project, require a lifecycle key, reuse or create only same-project owner-local tasks, and transition the task to `in_progress` before work proceeds. When no reusable task exists, public automation MUST be able to rely on a published brief audit created through the public audit surface instead of direct store seeding. Finish operations MUST require a valid claim and explicit closure metadata and MUST close to `done` or `blocked` with status outcomes for expiry or validation failure.
(Previously: lifecycle start could auto-create only from an already available published audit path and finish metadata was less explicit.)

#### Scenario: Start work after public audit publication
- GIVEN public automation published a brief audit for the adopted project
- WHEN an agent calls the lifecycle start operation with a lifecycle key and plan
- THEN the response returns the reconciled task in `in_progress` with an active claim

#### Scenario: Fail finish without a valid claim
- GIVEN an agent attempts the lifecycle finish operation after claim expiry or release
- WHEN the finish request is validated
- THEN the surface returns an explicit failure outcome and does not change task state

#### Scenario: Reject finish without explicit metadata
- GIVEN an agent holds a valid claim on a lifecycle task
- WHEN the finish request omits required closure metadata
- THEN the surface returns an explicit validation failure and leaves the task unchanged
