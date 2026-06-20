# Delta for mcp-cli-surface

## MODIFIED Requirements

### Requirement: Deterministic operational surface

The system MUST expose deterministic MCP and CLI operations for querying tasks and audits, claiming work, updating task state, and reading sync status. For the owner-local bootstrap path, the CLI MUST also expose `init`, `adopt`, `status`, and `read` as explicit local-operator commands. Responses SHOULD use canonical IDs, bounded results, and explicit status or error outcomes. The CLI MUST surface bootstrap/adoption state as `uninitialized`, `initialized`, or `adopted`, MUST return explicit error outcomes when a command requires a later state than the current one, and MUST keep `read` read-only for the adopted repository only. Every owner-local entry path that opens the adopted local node, including bootstrap CLI flows, top-level lifecycle commands, and MCP stdio surfaces, MUST run the same open-time schema upgrade pass before reading or mutating runtime state. Supported stale schemas MUST recover without manual SQL; unsafe schemas MUST return explicit local errors. When another bootstrap command already owns the local lock, the CLI MUST show visible waiting status, SHALL wait by default until the configured timeout, and MUST fail with explicit timeout or suspect-lock errors when safe progress cannot continue. Non-interactive execution MUST fail instead of prompting for stale-lock recovery. Negative lock-timeout values MUST be rejected as invalid arguments instead of being coerced. Verbose output SHOULD escalate owner identity, PID/liveness, lock age, and recovery hints.
(Previously: owner-local entry paths reopened existing node DBs without a required shared schema-upgrade pass.)

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

#### Scenario: Upgrade stale schema before lifecycle access
- GIVEN an adopted local node DB is stale but within supported owner-local upgrade rules
- WHEN the operator or agent runs a lifecycle-capable CLI or MCP entry path
- THEN the surface upgrades the DB before lifecycle access
- AND the command proceeds without requiring manual SQL

#### Scenario: Wait for an active bootstrap owner
- GIVEN another bootstrap command currently owns the local lock
- WHEN the operator runs a bootstrap command before timeout expires
- THEN the CLI reports waiting status and completes only after the lock is released

#### Scenario: Fail on timeout or suspect ownership
- GIVEN a bootstrap command cannot safely acquire the local lock before timeout or healthy ownership cannot be confirmed
- WHEN the operator runs a bootstrap command
- THEN the CLI returns an explicit timeout or suspect-lock error
- AND non-interactive mode does not prompt for recovery

#### Scenario: Reject invalid negative lock timeout
- GIVEN the operator passes a negative `--lock-timeout-seconds` value
- WHEN the operator runs a bootstrap command
- THEN the CLI returns an explicit invalid-arguments error
- AND the command does not touch persisted bootstrap state
