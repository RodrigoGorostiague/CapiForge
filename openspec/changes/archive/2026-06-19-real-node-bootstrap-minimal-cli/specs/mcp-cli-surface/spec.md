# Delta for MCP CLI Surface

## MODIFIED Requirements

### Requirement: Deterministic operational surface

The system MUST expose deterministic MCP and CLI operations for querying tasks and audits, claiming work, updating task state, and reading sync status. For the owner-local bootstrap path, the CLI MUST also expose `init`, `adopt`, `status`, and `read` as explicit local-operator commands. Responses SHOULD use canonical IDs, bounded results, and explicit status or error outcomes. The CLI MUST surface bootstrap/adoption state as `uninitialized`, `initialized`, or `adopted`, MUST return explicit error outcomes when a command requires a later state than the current one, and MUST keep `read` read-only for the adopted repository only.

(Previously: The operational surface covered deterministic query, mutation, claim, and sync flows, but did not define explicit local bootstrap or adoption commands.)

#### Scenario: Query actionable work
- GIVEN a project has ready tasks
- WHEN an agent calls the actionable-work operation
- THEN the response returns canonical task references and explicit status

#### Scenario: Report local bootstrap status
- GIVEN a local node home is present
- WHEN the operator runs the `status` command
- THEN the CLI returns the persisted bootstrap state, local identity, storage paths, and adopted-project metadata when present

#### Scenario: Reject command before required state
- GIVEN the local node is `uninitialized` or `initialized` without an adopted project
- WHEN the operator runs `adopt` or `read` before its prerequisite state exists
- THEN the CLI returns an explicit state-boundary error and does not mutate persisted state
