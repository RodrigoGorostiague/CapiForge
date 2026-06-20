# Project Agent Notes

## Architecture

- Kickoff and v0.1 state: [docs/architecture-v01.md](docs/architecture-v01.md)
- v0.1 coordination audit: [docs/audits/audit-v01-agent-coordination.md](docs/audits/audit-v01-agent-coordination.md)

## Coordination Decision Tree

| Situation | Skill path |
| --- | --- |
| Work already exists in the ready queue | `capiforge-pickup-task` → `capiforge-start-task` → `capiforge-close-task` |
| New justified work keyed by `lifecycle_key` | `capiforge-record-completed-work` or manual `audit_create_brief` → `audit_publish` → `tasks_reconcile_start` → `tasks_reconcile_finish` |
| Need DB/state semantics before acting | `capiforge-data-layer` |
| Verify MVP readiness or recover from empty queue | [docs/mvp.md](docs/mvp.md) |

## Project Skills

- `skills/capiforge-data-layer/SKILL.md` — Load first when agents need the SQLite contract, task states, claim rules, and start/finish update expectations.
- `skills/capiforge-pickup-task/SKILL.md` — Inspect state, select a ready task, claim it, and summarize the result.
- `skills/capiforge-start-task/SKILL.md` — Validate a live claim and move the task to `in_progress` via `tasks_transition` or `tasks_reconcile_start`.
- `skills/capiforge-close-task/SKILL.md` — Validate claim context and close via `tasks_transition` or `tasks_reconcile_finish`.
- `skills/capiforge-record-completed-work/SKILL.md` — Installed OpenCode automation for the public audit + lifecycle reconcile sequence.

## MCP Tools (owner-local)

Reads: `current_get`, `tasks_ready_get`, `tasks_list_by_index`, `project_entrypoint_get`, `workspace_get_current`, `sync_status`

Claims: `tasks_claim`, `tasks_claim_renew`, `tasks_release`

Mutations: `tasks_transition`, `tasks_reconcile_start`, `tasks_reconcile_finish`

Audits: `audit_create_brief`, `audit_publish`
