# Project Agent Notes

## Architecture

- Product direction (v0.3): [docs/architecture-v01.md](docs/architecture-v01.md)
- Scope pivot audit: [docs/audits/audit-v03-scope-pivot.md](docs/audits/audit-v03-scope-pivot.md)
- MVP v0.3 checklist: [docs/mvp-v03.md](docs/mvp-v03.md)
- Coordination MVP v0.2: [docs/mvp.md](docs/mvp.md)

## Decision Tree (milestone-first)

| Situation | Skill / path |
| --- | --- |
| Normal agent work (default) | **No CapiForge write** — persist in Engram / git / OpenSpec |
| Milestone: audit, feature close, architecture change | `capiforge-publish-milestone` |
| Work explicitly assigned from CF ready queue | `capiforge-pickup-task` → `capiforge-start-task` → `capiforge-close-task` |
| New justified work keyed by `lifecycle_key` | `capiforge-record-completed-work` or manual audit + reconcile |
| DB / truth-boundary semantics | `capiforge-data-layer` |
| Human review of project state | `capiforge web` (primary surface) |
| Verify MVP readiness | [docs/mvp-v03.md](docs/mvp-v03.md) |

## What NOT to put in CapiForge

- Per micro-task session notes → **Engram**
- OpenSpec change proposals and specs → **`openspec/`**
- Exploratory context that does not change project purpose, architecture, audits, or task state

## Project Skills

- `skills/capiforge-publish-milestone/SKILL.md` — **Load first** for agent publication decisions.
- `skills/capiforge-data-layer/SKILL.md` — SQLite contract, hybrid truth model, claim rules.
- `skills/capiforge-pickup-task/SKILL.md` — Optional: claim a ready queue task when assigned.
- `skills/capiforge-start-task/SKILL.md` — Optional: start a claimed queue task.
- `skills/capiforge-close-task/SKILL.md` — Optional: close a claimed queue task.
- `skills/capiforge-record-completed-work/SKILL.md` — OpenCode milestone lifecycle automation.

## MCP Tools (owner-local)

Reads: `current_get`, `tasks_ready_get`, `tasks_list_by_index`, `project_entrypoint_get`, `workspace_get_current`, `sync_status`, `project_page_get`

Claims: `tasks_claim`, `tasks_claim_renew`, `tasks_release`

Mutations: `tasks_transition`, `tasks_reconcile_start`, `tasks_reconcile_finish`, `milestone_publish`, `project_page_upsert`

Audits: `audit_create_brief`, `audit_publish`
