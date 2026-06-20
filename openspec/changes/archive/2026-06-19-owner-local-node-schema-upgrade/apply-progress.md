# Apply Progress: Owner-local Node Schema Upgrade

## Change
- owner-local-node-schema-upgrade

## Mode
- Standard

## Completed Tasks
- [x] 1.1 Update `storage/node-schema.sql` to declare the latest owner-local `tasks.lifecycle_key` layout and target `PRAGMA user_version`.
- [x] 1.2 Extend `runtime/node/store/__init__.py` with schema inspection helpers plus an ordered `_migrate_owner_local_schema()` transaction for supported stale `tasks` drift.
- [x] 1.3 Raise explicit `SurfaceError` on unsupported owner-local drift or future `user_version` values, leaving the DB unchanged.
- [x] 2.1 Change `runtime/node/store/__init__.py::connect_node_store()` / `NodeStore.from_file()` to initialize new DBs or migrate existing repo-local DBs before returning.
- [x] 2.2 Keep `runtime/node/bootstrap/__init__.py` on the shared `NodeStore.from_file()` path for `open_or_init()`, `adopt_repo()`, `require_adopted()`, and `read_entrypoint()` reopen flows.
- [x] 2.3 Verify runtime callers in `runtime/node/current.py` and `runtime/node/mcp_stdio.py` still rely on the same upgraded owner-local store boundary without side-channel repair logic.
- [x] 3.1 Extend `tests/storage/schema_node_test.py` with stale-schema fixtures that prove idempotent column/index repair, user-version updates, and unsafe-drift failure.
- [x] 3.2 Add `tests/node/bootstrap_cli_test.py` cases where adopted stale DBs are reopened through `status` and `read` and recover before lifecycle access.
- [x] 3.3 Add `tests/node/current_runtime_test.py` coverage showing `tasks_reconcile_start()` / `tasks_reconcile_finish()` succeed on a pre-migration DB missing `lifecycle_key` metadata.
- [x] 3.4 Add `tests/node/mcp_stdio_server_test.py` coverage proving the stdio server upgrades an adopted stale DB without manual SQL.
- [x] 4.1 Run `python3 -m unittest tests/storage/schema_node_test.py tests/node/bootstrap_cli_test.py tests/node/current_runtime_test.py tests/node/mcp_stdio_server_test.py` and fix any migration regressions.
- [x] 4.2 Review work-unit boundaries in `openspec/changes/owner-local-node-schema-upgrade/tasks.md` so implementation lands as PR 1 schema, PR 2 bootstrap wiring, PR 3 runtime/MCP regressions.

## Files Changed
| File | Action | Notes |
|---|---|---|
| `storage/node-schema.sql` | Modified | Declared canonical owner-local schema version via `PRAGMA user_version = 1`. |
| `runtime/node/store/__init__.py` | Modified | Added schema inspection helpers, repo-local migration flow, and explicit compatibility errors. |
| `runtime/node/bootstrap/__init__.py` | Modified | Routed adopted bootstrap reopen flows through the shared upgraded store boundary and reused a single adopted-store opener. |
| `runtime/node/current.py` | Modified | Reused the bootstrap adopted-store opener so runtime reads keep the shared migration boundary under the bootstrap lock. |
| `runtime/node/mcp_stdio.py` | Modified | Reused the bootstrap adopted-store opener for stdio surface reads instead of reopening side-channel stores. |
| `tests/storage/schema_node_test.py` | Modified | Added stale-schema repair, idempotency, user-version, and unsupported-drift coverage. |
| `tests/node/bootstrap_cli_test.py` | Modified | Added stale adopted-node reopen regressions for `open_or_init`, `status`, `read`, and `current`. |
| `tests/node/current_runtime_test.py` | Modified | Added stale-schema lifecycle reconciliation coverage that proves start/finish succeed after open-time upgrade. |
| `tests/node/mcp_stdio_server_test.py` | Modified | Added stale-schema stdio lifecycle coverage proving MCP reconcile-start upgrades the adopted local DB automatically. |
| `runtime/node/store/__init__.py` | Modified | Closed SQLite connections on initialization or migration failure to prevent leaked-handle warnings during unsupported drift checks. |
| `openspec/changes/owner-local-node-schema-upgrade/tasks.md` | Modified | Marked completed PR 3 regression, verification, and final boundary-review tasks as done. |
| `openspec/changes/owner-local-node-schema-upgrade/tasks.md` | Modified | Reviewed and recorded the final chained PR boundaries for PR 1 schema, PR 2 bootstrap wiring, and PR 3 runtime/MCP regressions. |
| `openspec/changes/owner-local-node-schema-upgrade/apply-progress.md` | Modified | Recorded the final cleanup slice and cumulative 12/12 implementation completion state. |

## Deviations from Design
- None — implementation matches the approved design.

## Issues Found
- The stale-schema regression fixture cannot safely rename `tasks` because SQLite updates trigger dependencies; the tests now downgrade via `DROP COLUMN lifecycle_key` plus index removal to model the pre-migration schema without breaking unrelated owner-local objects.
- The full migration regression suite surfaced leaked SQLite handles when `NodeStore.from_file()` failed during unsupported-drift checks; `connect_node_store()` now closes the connection before re-raising.

## Remaining Tasks
- None.

## Workload / PR Boundary
- Mode: chained PR slice
- Current work unit: PR 3 final boundary review and bookkeeping
- Boundary: Closed the final autonomous repo-local owner-local slice by recording the delivered PR 1/2/3 boundaries and confirming the regression suite still passes for the completed implementation.
- Estimated review budget impact: Documentation-only bookkeeping plus a focused regression rerun; comfortably within a small child-PR follow-up.

## Status
- 12/12 implementation tasks complete. Ready for verify.

## Tests Run
- `python3 -m unittest tests/node/current_runtime_test.py tests/node/mcp_stdio_server_test.py`
- `python3 -m unittest tests/storage/schema_node_test.py tests/node/bootstrap_cli_test.py tests/node/current_runtime_test.py tests/node/mcp_stdio_server_test.py`
