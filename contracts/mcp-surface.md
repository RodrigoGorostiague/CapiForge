# MCP / CLI Surface Contract

## Principles

- Commands MUST return deterministic `status` values and canonical IDs.
- Read operations MUST stay bounded and MUST NOT require full-record scans by callers.
- AI mutation commands MUST require actor identity plus justification metadata.
- Trusted node authentication MUST use a session-bound `node_proof` derived from the enrolled invitation fingerprint plus `node_id`, `agent_id`, and `session_id`; raw invitation fingerprints MUST NOT be replayed as actor proofs.
- Canonical project writes MUST execute only on the owner node.
- Routed non-owner mutations MUST require explicit owner acceptance in V1.
- Closed audits MUST reject direct content mutation and require addendum or follow-up flows.

## Commands

### Read

| Command | Purpose | Required Input | Success Status |
|---|---|---|---|
| `workspace.get` | Read a workspace and its projects | `workspace_id`, trusted enrolled local actor context | `ok` |
| `project.entrypoint.get` | Read deterministic project entrypoint | `project_id`, `as_of`, trusted enrolled local actor context with project authorization | `ok` |
| `tasks.list_by_index` | Read bounded task queues | `project_id`, `index_name`, `as_of`, `limit?`, trusted enrolled local actor context with project authorization | `ok` |
| `sync.status` | Read coordinator sync visibility | `project_id`, trusted enrolled actor context with project authorization | `ok` |

### Mutate

| Command | Purpose | Required Input | Success Status |
|---|---|---|---|
| `tasks.claim` | Acquire an exclusive lease for actionable work | canonical IDs, actor identity, plan, lease window, prior project authorization | `claimed` |
| `tasks.release` | Release an active claim and leave claimed execution | canonical IDs, actor identity, claim ID | `accepted` |
| `tasks.transition` | Mutate task state or emit routed proposal | canonical IDs, actor identity, justification, target state | `accepted` or `proposal_emitted` |
| `tasks.create_from_audit` | Create a task with one published origin audit | canonical IDs, actor identity, justification, task fields, execution context | `accepted` or `proposal_emitted` |
| `cross_project.request` | Route approved cross-project work to destination owner | source/destination project IDs, actor identity, justification, coordinator-recorded notice/approval for that source→destination pair | `routed` |

### Human Control

| Command | Purpose | Required Input | Success Status |
|---|---|---|---|
| `tasks.override` | Record human override over AI-managed task state | canonical IDs, human actor, target state | `accepted` |
| `audit.content.update` | Direct audit content edit; MUST reject closed audits | `audit_id`, `content`, trusted owner-local human actor | `accepted` |

`proposal_emitted` responses MUST include `route_status: owner_acceptance_required` and `acceptance_signal: ROUTE_OWNER_ACCEPTANCE_REQUIRED` in `data` when a routed non-owner mutation is waiting for the owner node.

Accepted `cross_project.request` routes MUST NOT make the coordinator authoritative. The destination owner node MUST perform the local canonical application step after acceptance, using the accepted route as the authorization artifact for the destination-side task mutation.

## Error Codes

| Code | Meaning |
|---|---|
| `JUSTIFICATION_REQUIRED` | AI mutation was missing required justification metadata |
| `INVALID_TASK_STATE` | Requested task state is unsupported or inconsistent |
| `CLAIM_CONFLICT` | Another active lease already owns the task |
| `CROSS_PROJECT_APPROVAL_REQUIRED` | Linked-project notice and approval were not both recorded |
| `NON_OWNER_CANONICAL_WRITE` | Caller attempted a canonical project write from a non-owner node |
| `AUDIT_CLOSED_IMMUTABLE` | Closed audits reject direct content mutation |
| `ROUTE_OWNER_ACCEPTANCE_REQUIRED` | Routed mutation is pending explicit owner acceptance |
| `UNKNOWN_RESOURCE` | Requested workspace, project, task, or audit was not found |
| `AUTHORIZATION_REQUIRED` | Caller is not a trusted enrolled actor for the requested surface |

Project authorization for shared read/sync surfaces is intentionally minimal in V1: the current owner node, a node that already holds coordinator claim history for that project, or a node already participating in a routed mutation for that destination project MAY read coordinator-backed sync metadata. Enrollment alone MUST NOT grant read access to arbitrary projects by ID.

Node-local project reads and claims are also project-scoped in V1. A trusted enrolled node MAY access a project only when it is the owner, already has coordinator-scoped participation for that project, or owns a project that is explicitly linked to the requested project in local metadata. Claiming a task MUST NOT bootstrap that authorization retroactively.

Routed mutation proposal creation is project-scoped as well. A node MUST already be authorized for the source project (for cross-project requests) or for the destination project (for same-project routed mutations) before the coordinator accepts proposal work.

Cross-project requests MUST also be backed by coordinator state. Request submission and owner acceptance MUST verify a live `notice_approvals` record (or equivalent coordinator notice/approval record) for the exact source→destination pair and destination owner node; requester-local approval cache alone is insufficient.

Claim-derived project access is temporary in V1. Historical released or expired claim rows MUST NOT keep granting ongoing project access after the active lease ends.

## Response Shape

```json
{
  "status": "ok | claimed | accepted | proposal_emitted | routed | error",
  "data": {},
  "error": {
    "code": "ERROR_CODE",
    "message": "deterministic explanation",
    "details": {}
  }
}
```
