# Agent Entrypoint Index Specification

## Purpose

Provide deterministic traversal so agents can discover projects, linked work, and operational queues without prompt reconstruction.

## Requirements

### Requirement: Canonical workspace and project graph

The system MUST model workspaces containing projects. Every workspace, project, task, audit, and linkable artifact MUST have a canonical stable ID and canonical link. Only humans MAY define or remove project-to-project links.

#### Scenario: Traverse a linked project graph
- GIVEN a workspace contains multiple projects
- WHEN an agent reads the workspace graph
- THEN each project is addressable by a stable ID and canonical link
- AND only human-approved project links are present

### Requirement: Project entrypoint

The system MUST expose one deterministic project entrypoint per project. The entrypoint MUST summarize project identity, linked projects, active audits, actionable task queues, index locations, and the current owner node required for agent-first traversal and canonical mutation routing.

#### Scenario: Open a project entrypoint
- GIVEN an agent needs starting context for a project
- WHEN it requests the project entrypoint
- THEN it receives the canonical starting record for traversal

#### Scenario: Resolve canonical mutation route
- GIVEN an agent plans a project-domain mutation
- WHEN it reads the project entrypoint
- THEN it can identify the project's owner node before attempting a canonical write

### Requirement: Materialized agent indexes

The system MUST maintain materialized indexes for deterministic lookup of actionable work, including at minimum ready, blocked, done, critical-priority, and expired-claim tasks.

#### Scenario: List blocked work deterministically
- GIVEN blocked tasks exist in a project
- WHEN an agent queries the blocked index
- THEN it receives blocked task references without scanning all records

### Requirement: Cross-project traversal guard

Agents MAY traverse linked projects through the entrypoint graph, but AI MUST NOT create cross-project tasks unless the projects are explicitly linked and both notice and human approval have been recorded. Cross-project mutations MUST be routed to the destination project's owner node after the required notice and human approval are recorded.

#### Scenario: Attempt cross-project task creation without approval
- GIVEN two projects are not both linked and approved for cross-project work
- WHEN an AI agent attempts to create a cross-project task
- THEN the system rejects the creation request

#### Scenario: Route an approved cross-project mutation
- GIVEN two linked projects have recorded notice and human approval
- WHEN an AI agent requests a mutation in the destination project
- THEN the request is routed to the destination project's owner node
