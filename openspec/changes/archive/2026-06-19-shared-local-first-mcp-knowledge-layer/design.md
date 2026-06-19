# Design: Shared Local-First MCP Knowledge Layer

## Technical Approach

V1 uses a two-tier runtime: one local node per machine plus one thin LAN coordinator/shared MCP runtime. Project **domain state** lives only in the owner node's SQLite database; **coordination state** lives in coordinator SQLite and is reconstructible from node announcements, claim traffic, and synced summaries. This implements the proposal's local-first model while enforcing the spec delta that each project has exactly one owner node for canonical writes.

## Architecture Decisions

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| Project authority | multi-writer sync, server authority, single owner | Single owner node per project | Simplest deterministic routing, token-efficient for agents, avoids coordinator authority drift in V1. |
| Shared runtime scope | full replica, thin metadata hub | Thin coordinator + shared MCP | Keeps coordinator replaceable, supports LAN discovery/claims, and preserves local-only docs. |
| Persisted data split | unified store, split stores | Split domain vs coordination SQLite | Makes trust boundaries explicit and lets coordinator rebuild without owning project truth. |
| Cross-project writes | free AI linking, coordinator-owned, human-gated | Human-gated links + owner-routed writes | Matches approval requirements and keeps project boundaries explicit. |

## Data Flow

```text
Agent/CLI → local MCP node → entrypoint/index lookup
                      │
      read local owner data or coordinator metadata
                      │
      non-owner mutation → coordinator route/proposal queue → owner node
                      │                                       │
                      └──── claim/status visibility ───────────┘
```

Domain write path: agent resolves project entrypoint, checks `owner_node_id`, and writes canonically only on that node. Non-owner nodes may create routed requests, claim requests, or sync summaries. Coordinator outage degrades shared discovery/routing, but owner-node local reads/writes still work.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `openspec/changes/shared-local-first-mcp-knowledge-layer/design.md` | Create | V1 implementation design. |
| `runtime/node/` | Create | Local node modules: domain store, owner router, local MCP handlers, index builder, sync publisher. |
| `runtime/coordinator/` | Create | Shared modules: enrollment, claim registry, route/proposal queue, sync health, shared MCP handlers. |
| `storage/node-schema.sql` | Create | Owner/non-owner local SQLite schema for project domain state and local documents. |
| `storage/coordinator-schema.sql` | Create | Coordinator SQLite schema for coordination metadata only. |
| `contracts/mcp-surface.md` | Create | Deterministic MCP + CLI operation contract used by implementation. |

## Interfaces / Contracts

```text
Node DB tables: workspaces, projects, project_entrypoints, tasks, audits,
task_relations, task_mutations, claims_local_cache, artifact_refs, local_documents,
project_links, cross_project_approvals, index_queue.

Coordinator DB tables: nodes, project_owners, claim_leases, mutation_routes,
sync_announcements, project_summaries, notice_approvals, enrollment_events.
```

Indexes: `tasks(project_id,state,priority)`, `claim_leases(project_id,task_id,status,lease_expires_at)`, `mutation_routes(destination_project_id,status,created_at)`, `project_entrypoints(project_id) UNIQUE`, `project_owners(project_id) UNIQUE`.

Deterministic surface:
- Read: `workspace.get`, `project.entrypoint.get`, `tasks.list_by_index`, `audits.get`, `sync.status`
- Mutate: `tasks.claim`, `tasks.release`, `tasks.transition`, `tasks.create_from_audit`, `cross_project.request`
- Human control: `tasks.override`, `links.approve`, `owner.assign`

All mutation inputs require canonical IDs, actor identity (`node_id`, `agent_id`, `session_id`), and justification metadata.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | State transitions, owner-write guard, lease expiry math, index projection | Table-driven tests once stack is chosen. |
| Integration | SQLite schemas, routed mutation flow, coordinator rebuild, outage degradation | Fixture DBs plus multi-process node/coordinator tests. |
| E2E | Agent traversal, claim collision, approved cross-project routing | CLI/MCP scenario tests over two nodes and one coordinator. |

## Migration / Rollout

Sequence V1 as: (1) schemas + IDs, (2) local node runtime + entrypoint/index builder, (3) coordinator enrollment/claims, (4) routed mutation + approval flow, (5) deterministic MCP/CLI surface. No data migration required.

Retention: local long-form documents remain only in `local_documents`; sync exports only `artifact_refs` metadata and canonical summaries. Nothing auto-expires except claim leases. Claims use `active → renewed/released/expired`; expiry removes exclusivity, not history. Suggested V1 timing: 5-minute lease, renew every 2 minutes, 30-second grace for clock skew.

Security/trust: coordinator is trusted for availability and routing visibility, not for canonical project truth. Nodes trust enrolled node identities on the LAN through per-node signed invitations; human approval gates owner assignment, project linking, and cross-project actions. If coordinator is unavailable, owner nodes continue local work, non-owner writes fall back to queued/manual proposals, and shared claim visibility becomes stale rather than authoritative.

## Open Questions

- [ ] Should non-owner routed mutations be auto-applied by the owner node or require explicit human/operator acceptance in V1?
- [x] Use per-node signed invitations for LAN V1 enrollment instead of shared-secret bootstrap.
