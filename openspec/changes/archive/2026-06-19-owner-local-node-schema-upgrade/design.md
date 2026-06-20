# Design: Owner-local Node Schema Upgrade

## Technical Approach

Add a repo-local migration pass to the existing `NodeStore.from_file()` open path so every owner-local reopen upgrades `.capiforge/node/node.sqlite3` before runtime code reads lifecycle data. The migrator stays inside the bootstrap/store boundary, inspects real SQLite metadata, applies ordered idempotent steps, and aligns the live DB with `storage/node-schema.sql` without introducing a separate admin command.

## Architecture Decisions

| Topic | Choice | Alternatives | Rationale |
|---|---|---|---|
| Upgrade entrypoint | Run migrations from `connect_node_store()` / `NodeStore.from_file()` | New CLI admin repair command; bootstrap-only one-off hook | All adopted-node surfaces already reopen through `NodeStore`. Fixing the shared open boundary covers CLI, stdio MCP, TUI, and bootstrap reads without duplicating policy. |
| Drift detection | Use `PRAGMA user_version` plus metadata inspection (`PRAGMA table_info`, `sqlite_master`, `PRAGMA index_list`) | Version-only; ad hoc column checks in lifecycle code | Existing adopted nodes may have partial manual repairs. Version alone is not enough, and feature-local checks spread schema policy. Inspecting actual columns/indexes keeps migrations deterministic and idempotent. |
| Failure policy | Support only known owner-local migrations; unknown future drift raises a local error | Best-effort mutation of unknown layouts | This DB is local but authoritative for owner-local lifecycle flows. Failing closed is safer than silently mutating an unsupported schema. |
| Scope boundary | Migrate only `.capiforge/node/node.sqlite3` for the current repo | Coordinator/global/cross-repo migration machinery | Matches the proposal’s trust boundary and avoids inventing shared rollout semantics for a local SQLite file. |

## Data Flow

`bootstrap_cli` / stdio MCP / TUI / runtime helper → `NodeBootstrap` lock + state validation → `NodeStore.from_file(node.sqlite3)` → migrate-if-needed transaction → runtime surface/query/mutation.

    CLI / MCP / TUI
          │
          ▼
    NodeBootstrap session
          │
          ▼
    NodeStore.from_file()
          ├── new DB: execute canonical schema
          └── existing DB: inspect → migrate → set user_version
                     │
                     ▼
              lifecycle-safe runtime access

Trust boundary: only the local repo owner node database is mutated. No coordinator DB, remote node, or cross-repo file is opened for migration.

## File Changes

| File | Action | Description |
|---|---|---|
| `runtime/node/store/__init__.py` | Modify | Add migration orchestration during existing DB open, schema inspection helpers, ordered migration execution, and explicit unsupported-drift errors. |
| `storage/node-schema.sql` | Modify | Declare the latest canonical owner-local schema, including `tasks.lifecycle_key`, its partial unique index, and the target `PRAGMA user_version`. |
| `runtime/node/bootstrap/__init__.py` | Modify | Keep bootstrap reopen paths on the shared store-open boundary and avoid any side-channel repair path. |
| `tests/storage/schema_node_test.py` | Modify | Assert canonical schema/user-version expectations and lifecycle-key uniqueness on the upgraded layout. |
| `tests/node/bootstrap_cli_test.py` | Modify | Add stale adopted-node reopen coverage proving `status`/`read` repair schema before lifecycle access. |
| `tests/node/current_runtime_test.py` | Modify | Add lifecycle start/finish coverage against a pre-migration DB missing `tasks.lifecycle_key` and its index. |
| `tests/node/mcp_stdio_server_test.py` | Modify | Verify stdio server opens an adopted stale DB and succeeds without manual SQL. |

## Interfaces / Contracts

```python
def connect_node_store(db_path: str | Path, schema_path: str | Path | None = None) -> sqlite3.Connection:
    ...  # initialize new DB or migrate existing owner-local DB before return

def _migrate_owner_local_schema(connection: sqlite3.Connection) -> None:
    ...  # ordered, transactional, idempotent
```

Migration v1 repairs the observed drift:
- add nullable `tasks.lifecycle_key` when absent
- create `idx_tasks_project_lifecycle_key` when absent or non-matching
- set `PRAGMA user_version = 1` only after the transaction commits

If inspection finds an unsupported `user_version` or a conflicting `tasks` shape that cannot be repaired safely, raise `SurfaceError` and leave the DB unchanged.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Metadata inspection and idempotent migration steps | Add focused schema tests using temporary SQLite files with missing column/index combinations. |
| Integration | Bootstrap reopen upgrades before `status`, `read`, and adopted runtime access | Extend `bootstrap_cli_test.py` with stale DB fixtures and repeated reopen assertions. |
| E2E | Lifecycle and stdio flows on an adopted stale node | Extend `current_runtime_test.py` and `mcp_stdio_server_test.py` to prove no manual SQL is required. |

## Migration / Rollout

Automatic on next local open. No manual rollout step, feature flag, or coordinator coordination is required. Operators with already adopted repos get the repair when any existing owner-local open path touches the store.

## Open Questions

- [ ] Should the canonical schema version live only in `PRAGMA user_version`, or also in a small constant inside `runtime/node/store/__init__.py` for test readability?
