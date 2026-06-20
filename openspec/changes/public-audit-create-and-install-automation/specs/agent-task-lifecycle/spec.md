# Delta for Agent Task Lifecycle

## MODIFIED Requirements

### Requirement: Start-time reconciliation

The system MUST reconcile work only within the adopted project and owner-local authority. It MUST use one deterministic lifecycle key to match reusable tasks and MUST NOT use fuzzy matching. If no reusable task exists, the system MAY create one only through a published same-project audit origin, including a brief audit created through the public owner-local flow, with recorded lifecycle key, origin, and justification metadata. Before active work begins, the system MUST hold a valid claim and transition the task to `in_progress`.
(Previously: create-on-miss required an audit-backed path but did not allow the public brief-audit origin flow.)

#### Scenario: Reuse an existing lifecycle task
- GIVEN the adopted project has a reusable task with the requested lifecycle key
- WHEN an agent starts lifecycle work
- THEN the system reuses that task, records justification metadata, claims it, and transitions it to `in_progress`

#### Scenario: Create a lifecycle task from the public brief-audit path
- GIVEN no reusable task exists for the requested lifecycle key
- WHEN installed automation first publishes a same-project brief audit through the public surface
- THEN lifecycle start creates one same-project task from that published audit before claiming it

### Requirement: Finish-time closure and failure handling

The system MUST close lifecycle work only while the acting agent still has a valid claim. It MUST require explicit closure metadata, MUST transition the task to `done` or `blocked`, and MUST record the metadata required by the task model. If claim validation, authority checks, or closure metadata validation fail, the system MUST reject automatic closure, MUST NOT mutate the task, and MUST return an explicit outcome for human or retry handling.
(Previously: finish-time handling required a valid claim but did not explicitly include metadata and authority validation failures.)

#### Scenario: Finish lifecycle work as done
- GIVEN an agent holds a valid active claim on an `in_progress` lifecycle task
- WHEN the agent finishes successfully with required closure metadata
- THEN the task enters `done` with the required result fields recorded

#### Scenario: Reject finish after lease expiry or metadata failure
- GIVEN a lifecycle-task claim expired or closure metadata is incomplete
- WHEN the agent attempts automatic closure
- THEN the system returns an explicit failure outcome and leaves the task unchanged
