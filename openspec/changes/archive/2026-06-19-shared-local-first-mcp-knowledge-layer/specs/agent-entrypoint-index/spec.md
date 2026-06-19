# Delta for Agent Entrypoint Index

## MODIFIED Requirements

### Requirement: Project entrypoint

The system MUST expose one deterministic project entrypoint per project. The entrypoint MUST summarize project identity, linked projects, active audits, actionable task queues, index locations, and the current owner node required for agent-first traversal and canonical mutation routing.
(Previously: the entrypoint summarized traversal context, but it did not require owner-node authority metadata.)

#### Scenario: Open a project entrypoint
- GIVEN an agent needs starting context for a project
- WHEN it requests the project entrypoint
- THEN it receives the canonical starting record for traversal

#### Scenario: Resolve canonical mutation route
- GIVEN an agent plans a project-domain mutation
- WHEN it reads the project entrypoint
- THEN it can identify the project's owner node before attempting a canonical write

### Requirement: Cross-project traversal guard

Agents MAY traverse linked projects through the entrypoint graph, but AI MUST NOT create cross-project tasks unless the projects are explicitly linked and both notice and human approval have been recorded. Cross-project mutations MUST be routed to the destination project's owner node after the required notice and human approval are recorded.
(Previously: approved cross-project creation was allowed, but destination-owner routing was not explicit.)

#### Scenario: Attempt cross-project task creation without approval
- GIVEN two projects are not both linked and approved for cross-project work
- WHEN an AI agent attempts to create a cross-project task
- THEN the system rejects the creation request

#### Scenario: Route an approved cross-project mutation
- GIVEN two linked projects have recorded notice and human approval
- WHEN an AI agent requests a mutation in the destination project
- THEN the request is routed to the destination project's owner node
