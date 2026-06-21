---
name: capiforge-data-layer
description: "Trigger: CapiForge database, data layer, task states, lifecycle_key, claim leases, start/finish updates. Load before coordinating task lifecycle work."
license: Apache-2.0
metadata:
  author: "rodaja"
  version: "1.0"
---

# Skill: capiforge-data-layer

## Activation Contract

Use when an orchestrator needs to understand what CapiForge persists, which fields matter at task start and finish, and how to update state through MCP without direct SQL.

## Hard Rules

- Keep all technical artifacts in English.
- Never write SQL directly; use MCP tools only.
- Treat `.capiforge/node/node.sqlite3` as canonical owner-local storage for the adopted project.
- Every task MUST trace to one `origin_audit_id` from a published audit.
- Closed audits are immutable; corrections require a new audit.

## Local Layout

| Path | Role |
| --- | --- |
| `.capiforge/node/bootstrap.json` | Bootstrap state: `uninitialized` → `initialized` → `adopted` |
| `.capiforge/node/node.sqlite3` | Canonical SQLite domain store |
| `.capiforge/node/bootstrap.lock` | Serialized CLI/MCP access lock |

## Core Tables (conceptual)

| Table | Purpose |
| --- | --- |
| `project_pages` | Purpose, architecture, and custom markdown pages |
| `audits` | Brief findings; states `draft`, `published`, `closed`, `superseded` |
| `tasks` | Operational work item with state machine and closure metadata |
| `claim_leases` | Exclusive task leases |
| `claims_local_cache` | Denormalized active-claim mirror per task |
| `task_mutations` | Auditable AI/human state-change trail |
| `project_entrypoints` | Derived queue indexes (`ready`, `blocked`, `done`, etc.) |

## Hybrid truth boundaries

| Content | Canonical source | CapiForge |
| --- | --- | --- |
| Purpose, architecture | `project_pages` | Yes — human UI + milestone agent updates |
| Audits, tasks | SQLite | Yes — milestones and optional queue path |
| Specs | `openspec/` | Reference only |
| Agent memory | Engram | Never duplicate |
| Long-form docs | `docs/` | `local_documents` index only |

Default agent cadence: **milestones only** (`capiforge-publish-milestone`). Queue pickup is optional when work is assigned from the ready queue.

## Task States

`proposed` → `ready` → `claimed` → `in_progress` → `done` | `blocked` | `cancelled`

DB CHECK constraints enforce:

- `claimed` / `in_progress`: require `active_claim_session_id`
- `done`: require `done_result`, `done_artifacts`, `done_references`, `done_expected_impact`
- `blocked`: require `blocked_reason`, `blocked_evidence`, `blocked_next_step`

## Identity Keys

| Key | Use |
| --- | --- |
| `task_id` | Explicit queue task selection after `tasks_ready_get` |
| `lifecycle_key` | Deterministic idempotent identity for reconcile flows |
| `claim_id` | Active lease handle; required for renew/release |
| `session_id` | Must match holder for transitions; derived per MCP client |

## What To Read At Task Start

1. `current_get` — bootstrap, entrypoint, ready queue snapshot
2. `tasks_ready_get` or `tasks_list_by_index` — bounded queue when selecting work
3. Prior claim context: `claim_id`, `task_id`, `lease_expires_at`, `session_id`

## What To Write At Task Start

**Queue pickup path**

1. `tasks_claim` on a `ready` task → state `claimed`
2. `tasks_transition` with `requested_state: in_progress`
3. `tasks_claim_renew` if work may exceed the default 5-minute lease

**Lifecycle reconcile path**

1. `audit_create_brief` → `audit_publish` when creating new justified work
2. `tasks_reconcile_start` with `lifecycle_key` → creates on miss, claims, moves to `in_progress`

## What To Write At Task Finish

**Queue pickup path**

- `tasks_transition` with `requested_state: done` or `blocked` plus all required finish metadata
- Claim is released automatically on terminal transitions

**Lifecycle reconcile path**

- `tasks_reconcile_finish` with `lifecycle_key`, `outcome`, and explicit finish metadata

## JSON Fields

`justification_json` on tasks and mutations:

```json
{"summary": "...", "evidence_refs": ["..."], "expected_impact": "..."}
```

`execution_context_json` carries automation metadata such as `lifecycle_key`, `lifecycle_plan`, and `lifecycle_creator`.

## MCP Tools By Phase

| Phase | Tools |
| --- | --- |
| Read | `current_get`, `tasks_ready_get`, `tasks_list_by_index`, `project_entrypoint_get` |
| Claim | `tasks_claim`, `tasks_claim_renew`, `tasks_release` |
| Mutate | `tasks_transition`, `tasks_reconcile_start`, `tasks_reconcile_finish` |
| Audit | `audit_create_brief`, `audit_publish` |

## References

- `storage/node-schema.sql`
- `contracts/mcp-surface.md`
- `openspec/specs/task-audit-model/spec.md`
- `skills/capiforge-publish-milestone/SKILL.md`
- `skills/capiforge-pickup-task/SKILL.md`
- `skills/capiforge-start-task/SKILL.md`
- `skills/capiforge-close-task/SKILL.md`
