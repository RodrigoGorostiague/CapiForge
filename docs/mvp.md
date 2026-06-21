# CapiForge MVP — Acceptance Checklist

> **v0.3 documentation hub:** see [mvp-v03.md](mvp-v03.md). This file documents the **v0.2 coordination MVP**, which remains supported.

Use this checklist to confirm owner-local agent coordination is **MVP-ready** for a single adopted repository.

## Operator checklist (human)

- [ ] `./capinstall install --cursor --opencode` completes without errors
- [ ] `./capinstall verify --json` reports `ok: true`
- [ ] `capiforge status` shows `bootstrap_state: adopted`
- [ ] Cursor MCP config points at `capiforge mcp serve` for this repo
- [ ] `.cursor/skills/` contains the five CapiForge skills (or OpenCode skills tree is present)

## Agent minimum path (queue pickup)

An agent MUST be able to complete this sequence using MCP only:

1. `current_get` — confirm adopted project and queue snapshot
2. `tasks_ready_get` — bounded read of ready work
3. `tasks_claim` — exclusive lease on one ready task
4. `tasks_transition` → `in_progress`
5. (optional) `tasks_claim_renew` if work exceeds the default 5-minute lease
6. `tasks_transition` → `done` with all required finish metadata

## Agent minimum path (new justified work)

When no ready task exists or work is keyed by `lifecycle_key`:

1. `audit_create_brief` → `audit_publish`
2. `tasks_reconcile_start` with `lifecycle_key` + create seed fields on miss
3. `tasks_reconcile_finish` with explicit `done` or `blocked` metadata

## Expected errors and recovery

| Error | Meaning | Recovery |
| --- | --- | --- |
| `CLAIM_CONFLICT` | Another active lease owns the task | Pick a different ready task or wait for release/expiry |
| `CLAIM_EXPIRED` | Lease elapsed before finish | `tasks_reconcile_start` again (lifecycle) or re-claim (queue) |
| `INVALID_TASK_STATE` (claim mismatch) | Transition used a different session than claim | Use the same MCP client session or match `capiforge-cli` actor IDs |
| `no_ready_tasks` (skill status) | Queue empty | Publish audit + seed tasks, or finish in-progress work first |
| Bootstrap lock stale | Prior CLI/MCP process interrupted | Re-run with `--recover-stale-lock --non-interactive` |

## Session identity (multi-agent)

- MCP derives `session_id` from `clientInfo` (`mcp-<client>-<hash>`).
- Override with `CAPIFORGE_SESSION_ID` when needed for automation.
- **Policy:** call `tasks_claim_renew` every 3–4 minutes on long tasks; default lease is 5 minutes.
- Two different sessions MUST NOT hold the same task claim simultaneously.

## MVP done criteria

The MVP is **done** when all of the following hold:

1. Install + verify pass on a clean machine (developer path).
2. Full test suite passes: `python3 -m unittest discover -s tests -p '*test*.py'`
3. An agent completes Path A or Path B end-to-end without direct SQL.
4. Skills (`AGENTS.md` decision tree) cover pickup, start, close, data-layer, and record-completed-work.
5. Empty ready queue has documented next steps (`README.md`, `capiforge-pickup-task` skill).

## References

- [architecture-v01.md](architecture-v01.md)
- [audits/audit-v02-mvp-status.md](audits/audit-v02-mvp-status.md)
- [../AGENTS.md](../AGENTS.md)
- [../skills/capiforge-data-layer/SKILL.md](../skills/capiforge-data-layer/SKILL.md)
