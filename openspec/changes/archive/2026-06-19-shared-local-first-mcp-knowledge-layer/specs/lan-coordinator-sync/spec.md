# Delta for LAN Coordinator Sync

## MODIFIED Requirements

### Requirement: Local authority with thin coordination

The architecture MUST use a local SQLite store per node and a thin LAN coordinator or shared MCP runtime backed by SQLite. For V1, each project MUST have exactly one owner node. The owner node MUST be the canonical writer for that project's domain state. Non-owner nodes MAY read, sync metadata, request claims, and propose mutations, but they MUST NOT become canonical writers for that project's domain state. The coordinator MUST NOT become the primary source of truth or accept non-owner writes as canonical domain state.
(Previously: local persistence stayed authoritative, but single-owner canonical write authority was not explicit.)

#### Scenario: Coordinator becomes unavailable
- GIVEN a node has local data
- WHEN the LAN coordinator is offline
- THEN local reads remain available from the node store
- AND authority does not shift to the absent coordinator

#### Scenario: Non-owner proposes a project mutation
- GIVEN a project has an assigned owner node
- WHEN a different node submits a domain mutation through shared coordination
- THEN the mutation is treated as a proposal or routed request
- AND the non-owner node does not become the canonical writer

### Requirement: Shared visibility for coordination

The coordinator SHOULD expose enrollment status, claim visibility, sync health, and owner-node metadata needed for safe multi-node coordination, while avoiding ownership of local-only content or project domain authority.
(Previously: the coordinator exposed coordination metadata without explicitly surfacing owner-node authority.)

#### Scenario: Inspect sync health
- GIVEN multiple nodes participate in the workspace
- WHEN an operator checks coordinator status
- THEN the system exposes node enrollment, claim visibility, and sync health metadata

#### Scenario: Inspect project owner metadata
- GIVEN a project participates in shared coordination
- WHEN an operator or agent requests coordination metadata
- THEN the response identifies that project's owner node
