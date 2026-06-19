# Proposal: Shared Local-First MCP Knowledge Layer

## Intent
Build a local-first task/audit layer so AI agents can act with auditable justification and coordinate safely across machines without a shared server becoming authoritative.

## Scope

### In Scope
- Workspace/project model with canonical IDs and agent-first traversal.
- Audits, tasks, linked artifacts, and explicit task relationships.
- Claim/lease coordination, LAN coordinator, and MCP/CLI-first interfaces.

### Out of Scope
- Complex UI, autonomous audit publication, or AI-authored cross-project relationships.
- Full document sync, advanced auto-resolution, embeddings-first search, or cloud deployment.

## Capabilities

### New Capabilities
- `task-audit-model`: audit/task lifecycles, justification rules, artifact links, and readiness/completion metadata.
- `multi-agent-claims`: exclusive claim, renewable lease, escalation on claimed work, and safety rules.
- `agent-entrypoint-index`: canonical project entrypoint plus materialized agent indexes for precise traversal.
- `lan-coordinator-sync`: thin coordinator for enrollment, lease visibility, and structured metadata exchange.
- `mcp-cli-surface`: deterministic MCP/API-first and CLI operations for query, claim, update, and sync status.

### Modified Capabilities
None.

## Approach
Use a hybrid architecture: sovereign local SQLite stores per node plus one self-hosted LAN runtime combining coordinator and shared MCP server. V1 syncs only structured metadata and canonical summaries; long-form documents stay local-only.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `openspec/specs/task-audit-model/spec.md` | New | Core rules and state models |
| `openspec/specs/multi-agent-claims/spec.md` | New | Claim/lease and escalation behavior |
| `openspec/specs/agent-entrypoint-index/spec.md` | New | Canonical entrypoint and indexes |
| `openspec/specs/lan-coordinator-sync/spec.md` | New | Shared coordination and sync boundaries |
| `openspec/specs/mcp-cli-surface/spec.md` | New | Deterministic agent interface contract |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Coordinator becomes de facto source of truth | Med | Enforce local authority and offline-safe reads |
| Weak identity/lease rules allow conflicting AI actions | High | Require node/agent/session identity and expiring exclusive claims |
| Non-deterministic IDs/indexes waste agent context | High | Define canonical IDs, links, and bounded traversal contracts first |

## Rollback Plan
If coordinator/claim behavior proves unsafe, disable shared mutation paths and fall back to read-only shared discovery while keeping local task/audit data authoritative.

## Dependencies

- Self-hosted LAN availability for the shared runtime.
- SQLite for local and coordinator persistence.

## Success Criteria

- [ ] Agents can find critical/blocked/expired work from a deterministic project entrypoint.
- [ ] Every AI task mutation records mandatory justification metadata; closed audits stay immutable.
- [ ] Two agents cannot actively work the same task; encountering a claimed task forces escalation instead of action.

## Proposal Question Round
- Confirm whether AI-created cross-project tasks need approval or notification.
- Confirm whether humans may reopen cancelled/done tasks.
- Confirm retention/privacy requirements for local-only documents and audit evidence.
