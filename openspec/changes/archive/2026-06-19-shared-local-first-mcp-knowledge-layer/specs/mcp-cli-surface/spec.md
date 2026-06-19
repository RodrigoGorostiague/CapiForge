# Delta for MCP CLI Surface

## MODIFIED Requirements

### Requirement: Mutation validation

Every AI mutation operation MUST require justification metadata before the change is accepted. Mutation commands MUST reject invalid state transitions or missing required task metadata. For project domain state, only the project's owner node MUST be allowed to perform the canonical write. Non-owner nodes MAY submit proposals, claim requests, or routed mutation requests, but they MUST NOT be accepted as canonical writers.
(Previously: mutation validation covered justification and state validity, but not single-owner canonical write authority.)

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
(Previously: approved cross-project AI actions were allowed, but destination-owner routing was not required.)

#### Scenario: Approve cross-project AI task creation
- GIVEN two projects are explicitly linked
- AND notice and human approval are recorded
- WHEN an AI agent creates a cross-project task
- THEN the system accepts the request

#### Scenario: Route approved cross-project mutation
- GIVEN notice and human approval are recorded for a linked destination project
- WHEN a non-owner node invokes a cross-project mutation command
- THEN the surface routes the mutation to the destination project's owner node
