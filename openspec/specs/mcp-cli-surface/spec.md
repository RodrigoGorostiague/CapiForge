# MCP CLI Surface Specification

## Purpose

Define a deterministic MCP and CLI contract for querying, updating, claiming, and synchronizing the task-audit system.

## Requirements

### Requirement: Deterministic operational surface

The system MUST expose deterministic MCP and CLI operations for querying tasks and audits, claiming work, updating task state, and reading sync status. Responses SHOULD use canonical IDs, bounded results, and explicit status or error outcomes.

#### Scenario: Query actionable work
- GIVEN a project has ready tasks
- WHEN an agent calls the actionable-work operation
- THEN the response returns canonical task references and explicit status

### Requirement: Mutation validation

Every AI mutation operation MUST require justification metadata before the change is accepted. Mutation commands MUST reject invalid state transitions or missing required task metadata. For project domain state, only the project's owner node MUST be allowed to perform the canonical write. Non-owner nodes MAY submit proposals, claim requests, or routed mutation requests, but they MUST NOT be accepted as canonical writers.

#### Scenario: Reject unjustified AI mutation
- GIVEN an AI agent submits a task state change without justification metadata
- WHEN the mutation is validated
- THEN the system rejects the request

#### Scenario: Reject non-owner canonical write
- GIVEN a node is not the owner node for a project
- WHEN it submits a direct canonical mutation for that project's domain state
- THEN the system rejects or reroutes the request
- AND the write is not recorded as canonical project state

### Requirement: Human override and approval gates

The surface MUST allow human overrides of AI-managed task state. AI MAY create cross-project tasks only after the system records both user notice and human approval for explicitly linked projects. Cross-project mutations MUST be routed to the destination project's owner node after those approvals are recorded.

#### Scenario: Approve cross-project AI task creation
- GIVEN two projects are explicitly linked
- AND notice and human approval are recorded
- WHEN an AI agent creates a cross-project task
- THEN the system accepts the request

#### Scenario: Route approved cross-project mutation
- GIVEN notice and human approval are recorded for a linked destination project
- WHEN a non-owner node invokes a cross-project mutation command
- THEN the surface routes the mutation to the destination project's owner node

### Requirement: Audit-safe publication controls

The surface MUST prevent autonomous AI publication or rewriting of closed audits unless a human-authorized addendum or follow-up audit flow is used.

#### Scenario: Attempt to edit a closed audit
- GIVEN an audit is `closed`
- WHEN an agent requests direct content mutation
- THEN the system rejects the edit and requires addendum or follow-up flow
