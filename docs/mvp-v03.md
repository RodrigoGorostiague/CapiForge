# CapiForge MVP v0.3 — Documentation Hub Acceptance Checklist

**Status: complete** (tag `v0.3.0`). Active milestone: [mvp-v04.md](mvp-v04.md).

Use this checklist to confirm the **documentation and task hub** MVP is ready for a single local owner with multiple agents on one adopted repository.

> **Note:** Coordination MVP v0.2 remains complete. See [mvp.md](mvp.md) for the prior agent-coordination checklist and [audits/audit-v03-scope-pivot.md](audits/audit-v03-scope-pivot.md) for the pivot audit.

## Operator checklist (human)

- [ ] `./capinstall install --cursor --opencode` completes without errors
- [ ] `./capinstall verify --json` reports `ok: true`
- [ ] `capiforge status` shows `bootstrap_state: adopted`
- [ ] `capiforge web` shows **purpose**, **architecture**, **tasks**, and **audits** for the adopted project
- [ ] Human can edit purpose and architecture pages from the web UI
- [ ] `.cursor/skills/` contains CapiForge skills including `capiforge-publish-milestone`

## Hybrid truth model

| Content | Canonical source | CapiForge role |
| --- | --- | --- |
| Purpose, architecture, tasks, audits | CapiForge SQLite | Human UI + agent milestones |
| OpenSpec specs | `openspec/` in repo | Reference only; do not duplicate |
| Agent session memory | Engram | Do not duplicate in CapiForge |
| Long-form repo docs | `docs/` in repo | Indexed via `local_documents` when needed |

## Agent minimum path (milestones only)

Agents MUST **not** call CapiForge on every micro-task. Publish only at milestones:

| Milestone | MCP sequence |
| --- | --- |
| Audit / review completed | `audit_create_brief` → `audit_publish` |
| Significant feature closed | `tasks_reconcile_start` → `tasks_reconcile_finish` with `done_*` metadata |
| Architecture change | Update project page (UI or future MCP) + audit addendum |
| Micro-task, exploration, minor fix | **No CapiForge write** — use Engram / git / OpenSpec |

Typical milestone cost: **≤ 3 MCP calls** (vs 7+ for per-task pickup/start/close).

## Agent optional path (queue-assigned work)

When the human or orchestrator explicitly assigns work from the CapiForge ready queue:

1. `current_get` → `tasks_ready_get` → `tasks_claim`
2. `tasks_transition` → `in_progress`
3. `tasks_transition` → `done` | `blocked` with required metadata

Use skills `capiforge-pickup-task` → `capiforge-start-task` → `capiforge-close-task` only for this path.

## MVP v0.3 done criteria

1. Install + verify pass on a clean machine.
2. Full test suite passes: `python3 -m unittest discover -s tests -p '*test*.py'`
3. Web UI displays purpose, architecture, task state, and audit docs.
4. `capiforge-publish-milestone` skill documents when and how agents publish.
5. Audit v0.3 published with derived tasks under `audit/v0.3/*`.
6. v0.2 MCP flows still work (regression).

## References

- [architecture-v01.md](architecture-v01.md)
- [audits/audit-v03-scope-pivot.md](audits/audit-v03-scope-pivot.md)
- [audits/audit-v03-mvp-closure.md](audits/audit-v03-mvp-closure.md)
- [mvp-v03-baseline.md](mvp-v03-baseline.md)
- [demo-v03.md](demo-v03.md)
