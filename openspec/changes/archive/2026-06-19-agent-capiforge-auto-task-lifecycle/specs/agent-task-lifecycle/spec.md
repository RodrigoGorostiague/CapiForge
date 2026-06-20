# Agent Task Lifecycle Specification

## Purpose

Define deterministic owner-local task reconciliation for automatic agent start and finish flows.

## Requirements

### Requirement: Start-time reconciliation

The system MUST reconcile work only within the adopted project and owner-local authority. It MUST use one deterministic lifecycle key to match reusable tasks and MUST NOT use fuzzy matching. If no reusable task exists, the system MAY create one only through an audit-backed path with recorded lifecycle key, origin, and justification metadata. Before active work begins, the system MUST hold a valid claim and transition the task to `in_progress`.

#### Scenario: Reuse an existing lifecycle task
- GIVEN the adopted project has a reusable task with the requested lifecycle key
- WHEN an agent starts lifecycle work
- THEN the system reuses that task, records justification metadata, claims it, and transitions it to `in_progress`

#### Scenario: Create a lifecycle task when none matches
- GIVEN no reusable task exists for the requested lifecycle key
- WHEN an agent starts lifecycle work with an allowed auto-create path
- THEN the system creates one same-project task with audit-backed origin metadata before claiming it

### Requirement: Finish-time closure and failure handling

The system MUST close lifecycle work only while the acting agent still has a valid claim. It MUST transition the task to `done` or `blocked` and record closure metadata required by the task model. If the claim has expired, the system MUST reject automatic closure, MUST NOT mutate the task, and MUST return an explicit expiry outcome for human or retry handling.

#### Scenario: Finish lifecycle work as done
- GIVEN an agent holds a valid active claim on an `in_progress` lifecycle task
- WHEN the agent finishes successfully
- THEN the task enters `done` with result, affected artifacts, linked references, and expected impact

#### Scenario: Reject finish after lease expiry
- GIVEN an agent's lifecycle-task claim expired before finish
- WHEN the agent attempts automatic closure
- THEN the system returns an explicit expiry error and leaves the task unchanged
