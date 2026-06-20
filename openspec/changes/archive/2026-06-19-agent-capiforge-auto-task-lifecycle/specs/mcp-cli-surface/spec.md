# Delta for MCP CLI Surface

## ADDED Requirements

### Requirement: Automatic agent lifecycle operations

The system MUST expose deterministic MCP and CLI lifecycle operations for start-time reconciliation and finish-time closure after MCP bootstrap is configured. Start operations MUST resolve the adopted project, require a lifecycle key, reuse or create only same-project owner-local tasks, obtain a valid claim, and transition the task to `in_progress` before work proceeds. Finish operations MUST require a valid claim and MUST close to `done` or `blocked` with explicit justification metadata and status outcomes for expiry or validation failure.

#### Scenario: Start work through lifecycle wrapper
- GIVEN MCP is configured for an adopted project
- WHEN an agent calls the lifecycle start operation with a lifecycle key and plan
- THEN the response returns the reconciled task reference in `in_progress` with an active claim

#### Scenario: Fail finish without a valid claim
- GIVEN an agent attempts the lifecycle finish operation after claim expiry or release
- WHEN the finish request is validated
- THEN the surface returns an explicit failure outcome and does not change task state
