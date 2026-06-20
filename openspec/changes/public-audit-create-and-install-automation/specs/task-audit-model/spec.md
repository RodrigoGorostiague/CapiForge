# Delta for Task Audit Model

## ADDED Requirements

### Requirement: Brief-audit publication boundary

The system MUST allow a brief audit to move from `draft` to `published` through a public owner-local same-project flow only. Publication MUST require the minimum brief-audit justification fields needed for downstream task creation, and cross-project or non-owner publication MUST be rejected.

#### Scenario: Publish a same-project brief audit
- GIVEN a draft brief audit has the required summary and justification fields
- WHEN the owner-local public publish flow is invoked for the adopted project
- THEN the audit becomes `published` and may justify task creation

#### Scenario: Reject cross-project or incomplete publication
- GIVEN a draft brief audit is incomplete or targets another project
- WHEN publication is requested
- THEN the system rejects the request and leaves the audit unchanged

## MODIFIED Requirements

### Requirement: Task-centered operations

The system MUST treat tasks as the central operational entity. Every task MUST be justified by an audit, MUST have exactly one origin audit, and MAY link additional audits later. Automatically created lifecycle tasks MUST use an explicit published-audit origin path, MUST record the lifecycle key and creator identity in justification metadata, and MUST remain same-project only. A brief audit created through the public owner-local flow MAY serve as that origin audit once it is published.
(Previously: lifecycle auto-create required an audit-backed origin path but did not define a public brief-audit origin flow.)

#### Scenario: Create a justified task
- GIVEN a published audit identifies actionable work
- WHEN a task is created from that audit
- THEN the task stores that audit as its origin audit and may link later audits

#### Scenario: Auto-create a lifecycle task from a published brief audit
- GIVEN no reusable lifecycle task exists in the adopted project
- WHEN an allowed lifecycle wrapper receives a published brief audit from the public flow
- THEN the task stores that audit as its origin with lifecycle-key justification metadata
