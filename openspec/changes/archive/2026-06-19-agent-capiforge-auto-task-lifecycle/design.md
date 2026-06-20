# Design: Agent CapiForge Auto Task Lifecycle

Owner-local lifecycle automation for installed agents. This change adds adopted-project wrappers that reuse existing task primitives, expose the missing mutation tools on the stdio MCP server, and add deterministic `lifecycle_key` reconciliation for automatic start/finish flows.

## Technical Approach

Implement two wrapper operations in `runtime/node/current.py`: `tasks_reconcile_start` and `tasks_reconcile_finish`. They run inside the existing adopted-project bootstrap/session pattern, resolve the local project, perform exact-key lookup, and call `NodeMCPSurface.tasks_create_from_audit`, `tasks_claim`, `tasks_transition`, and `tasks_release` as needed. V1 stays same-project and owner-local; no coordinator routing or fuzzy matching is added.

## Architecture Decisions

| Topic | Choice | Alternatives | Rationale |
|---|---|---|---|
| Entry point | Extend adopted-project wrappers in `runtime/node/current.py` | New standalone lifecycle service | Preserves the current read/claim wrapper pattern and keeps bootstrap locking, actor construction, and local authority checks in one place. |
| Matching | Add `tasks.lifecycle_key` with exact per-project lookup | Fuzzy description matching; external map table | Exact keys make reuse deterministic, prevent accidental duplicates, and give idempotent agent calls. |
| Creation path | Auto-create only when caller supplies a published `origin_audit_id` plus task seed metadata | Auto-publish a synthetic audit; direct store-only task creation | Reuses the existing audit-backed mutation contract and fails safe when audit provenance is missing. |
| Expiry policy | Finish requires an active matching claim; expired leases fail closed and instruct caller to reconcile-start again | Silent re-claim or lease renewal during finish | Avoids hidden ownership changes and matches current claim-state coordination rules. |

## Data Flow

    Agent
      │ lifecycle_key + task seed/close payload
      ▼
    MCP stdio tool / CLI wrapper
      ▼
    runtime.node.current adopted-project helper
      ├── exact lookup by project_id + lifecycle_key
      ├── create_from_audit (only if no task and audit seed exists)
      ├── tasks_claim + tasks_transition(in_progress)
      └── tasks_transition(done|blocked) or tasks_release

Start flow: lookup exact key → reuse existing task when state is `ready|claimed|in_progress|blocked` after claim sync → create only if no match and published audit seed is provided → claim → transition to `in_progress`.

Finish flow: lookup exact key → verify same task and active claim for caller session at `as_of` → transition to `done` or `blocked` with required metadata → optionally release claim cache/state after terminal close if needed for cleanliness.

## File Changes

| File | Action | Description |
|---|---|---|
| `storage/node-schema.sql` | Modify | Add nullable `lifecycle_key` to `tasks` and a unique index scoped to `project_id`. |
| `runtime/node/store/__init__.py` | Modify | Persist/read `lifecycle_key`; add exact lookup helper for project + lifecycle key. |
| `runtime/node/current.py` | Modify | Add adopted-project reconcile start/finish wrappers and shared validation helpers. |
| `runtime/node/mcp_stdio.py` | Modify | Expose missing mutation tools plus high-level lifecycle tools on the installed stdio MCP server. |
| `runtime/bootstrap_cli.py` | Modify | Add JSON-envelope parity commands for lifecycle start/finish. |
| `runtime/cli.py` | Modify | Route `capiforge tasks start|finish` to the bootstrap wrapper commands. |
| `tests/mcp_cli/surface_test.py` | Modify | Cover exact-key reuse, published-audit creation, and expired-claim failure. |
| `tests/node/mcp_stdio_server_test.py` | Modify | Cover new MCP tools and start/finish tool flows. |
| `tests/node/bootstrap_cli_test.py` | Modify | Cover CLI parity and deterministic envelope behavior. |

## Interfaces / Contracts

```python
tasks_reconcile_start(lifecycle_key, plan, lease_minutes=5,
    origin_audit_id=None, description=None, priority=None,
    effort=None, risk=None, task_type=None, justification=None,
    execution_context=None) -> {task_id, claim_id, state}

tasks_reconcile_finish(lifecycle_key, outcome, as_of=None,
    done_result=None, done_artifacts=None, done_references=None,
    done_expected_impact=None, blocked_reason=None,
    blocked_evidence=None, blocked_next_step=None) -> {task_id, state}
```

`outcome` is `done|blocked`. `lifecycle_key` is required and exact. Start MUST reject create requests without a published `origin_audit_id` and complete task seed fields. Finish MUST reject when the caller no longer holds the active claim.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Exact-key lookup, idempotent reuse, metadata validation | `unittest` for store/current helpers |
| Integration | Surface create/claim/transition/finish behavior, expiry demotion, same-project guard | Extend `tests/mcp_cli/surface_test.py` |
| E2E | Installed stdio + CLI start/finish envelopes | Extend `tests/node/mcp_stdio_server_test.py` and `tests/node/bootstrap_cli_test.py` |

## Migration / Rollout

No migration required beyond local schema evolution for owner-local node databases. Existing tasks keep `NULL lifecycle_key`; new lifecycle automation requires populated keys.

## Open Questions

- [ ] Should terminal tasks keep their `lifecycle_key` permanently reserved, or should a future human override be allowed to clear/reassign it?
