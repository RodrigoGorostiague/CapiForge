# Tasks: Owner-local Node Schema Upgrade

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 360-480 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | auto-chain |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Add owner-local schema migrator and canonical versioning | PR 1 | Base = feature/tracker branch; include schema tests. |
| 2 | Wire bootstrap/open paths to the shared upgrade boundary | PR 2 | Base = PR 1 branch; verify `status`/`read` reopen stale DBs safely. |
| 3 | Add lifecycle and stdio stale-node regressions | PR 3 | Base = PR 2 branch; keep runtime/MCP tests with the behavior. |

### Reviewed PR Boundaries

- PR 1: tasks 1.1, 1.2, 1.3, 3.1
- PR 2: tasks 2.1, 2.2, 2.3, 3.2
- PR 3: tasks 3.3, 3.4, 4.1, 4.2

## Phase 1: Foundation / Schema

- [x] 1.1 Update `storage/node-schema.sql` to declare the latest owner-local `tasks.lifecycle_key` layout and target `PRAGMA user_version`.
- [x] 1.2 Extend `runtime/node/store/__init__.py` with schema inspection helpers plus an ordered `_migrate_owner_local_schema()` transaction for supported stale `tasks` drift.
- [x] 1.3 Raise explicit `SurfaceError` on unsupported owner-local drift or future `user_version` values, leaving the DB unchanged.

## Phase 2: Open-path Integration

- [x] 2.1 Change `runtime/node/store/__init__.py::connect_node_store()` / `NodeStore.from_file()` to initialize new DBs or migrate existing repo-local DBs before returning.
- [x] 2.2 Keep `runtime/node/bootstrap/__init__.py` on the shared `NodeStore.from_file()` path for `open_or_init()`, `adopt_repo()`, `require_adopted()`, and `read_entrypoint()` reopen flows.
- [x] 2.3 Verify runtime callers in `runtime/node/current.py` and `runtime/node/mcp_stdio.py` still rely on the same upgraded owner-local store boundary without side-channel repair logic.

## Phase 3: Regression Coverage

- [x] 3.1 Extend `tests/storage/schema_node_test.py` with stale-schema fixtures that prove idempotent column/index repair, user-version updates, and unsafe-drift failure.
- [x] 3.2 Add `tests/node/bootstrap_cli_test.py` cases where adopted stale DBs are reopened through `status` and `read` and recover before lifecycle access.
- [x] 3.3 Add `tests/node/current_runtime_test.py` coverage showing `tasks_reconcile_start()` / `tasks_reconcile_finish()` succeed on a pre-migration DB missing `lifecycle_key` metadata.
- [x] 3.4 Add `tests/node/mcp_stdio_server_test.py` coverage proving the stdio server upgrades an adopted stale DB without manual SQL.

## Phase 4: Verification / Cleanup

- [x] 4.1 Run `python3 -m unittest tests/storage/schema_node_test.py tests/node/bootstrap_cli_test.py tests/node/current_runtime_test.py tests/node/mcp_stdio_server_test.py` and fix any migration regressions.
- [x] 4.2 Review work-unit boundaries in `openspec/changes/owner-local-node-schema-upgrade/tasks.md` so implementation lands as PR 1 schema, PR 2 bootstrap wiring, PR 3 runtime/MCP regressions.
