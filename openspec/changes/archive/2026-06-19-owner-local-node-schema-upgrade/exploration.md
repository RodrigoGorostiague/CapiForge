## Exploration: owner-local local node schema upgrade for adopted nodes

### Current State
The owner-local bootstrap path persists `.capiforge/node/node.sqlite3` through `NodeStore.from_file()` and `connect_node_store()`, but existing databases are only initialized when the file is new or empty. Once a node DB already exists, the runtime reopens it without any schema version check, migration pass, or compatibility repair. That gap is now visible because the recent owner-local lifecycle change added `tasks.lifecycle_key` and a partial unique index in `storage/node-schema.sql`, while `tasks_reconcile_start()` and `tasks_reconcile_finish()` already assume those fields exist on every adopted local node.

### Affected Areas
- `runtime/node/store/__init__.py` — current file-open path initializes fresh DBs only and is the natural place to run repo-local node migrations.
- `runtime/node/bootstrap/__init__.py` — `open_or_init()`, `adopt_repo()`, `read_entrypoint()`, and `require_adopted()` all depend on reopening an existing local node DB safely.
- `storage/node-schema.sql` — defines the latest canonical node schema, including `tasks.lifecycle_key` and the partial unique index.
- `runtime/node/current.py` — lifecycle reconcile helpers read and write `lifecycle_key`, so stale DBs fail here today.
- `runtime/bootstrap_cli.py` and `runtime/node/mcp_stdio.py` — product-facing owner-local open/read/start/finish surfaces should benefit from automatic upgrade without manual SQL.
- `tests/node/bootstrap_cli_test.py` and `tests/node/current_runtime_test.py` — need stale-DB reopen coverage proving automatic upgrade before lifecycle flows run.

### Approaches
1. **Targeted compatibility repair** — add bootstrap/open-time checks that specifically add missing lifecycle columns/indexes (and any other currently required owner-local tables) when an adopted local DB is reopened.
   - Pros: Smallest delta, directly fixes the demonstrated `tasks.lifecycle_key` drift, easy to land quickly.
   - Cons: Becomes an ad hoc list of feature checks, weak foundation for the next schema change, and spreads migration policy across helpers.
   - Effort: Medium

2. **Repo-local versioned node migrator** — introduce a node-schema upgrade step that runs whenever `NodeStore.from_file()` opens an existing DB, detects an older schema version, and applies ordered SQLite migrations for the owner-local node database only.
   - Pros: Gives a supported bootstrap/open path, keeps future local schema evolution in one place, and matches the user need better than another one-off fix.
   - Cons: Slightly larger change now because version storage, ordered migrations, and downgrade-safe tests must be added.
   - Effort: Medium

### Recommendation
Recommend **Approach 2** with a STRICT boundary: only migrate the repo-local owner node database, and only from the same bootstrap/open paths that already own `.capiforge/node/node.sqlite3`.

The safe slice is to make every existing local-node open path run one deterministic migration routine before runtime features touch the store. That routine should cover the known `tasks.lifecycle_key` upgrade first, but its contract should be generic enough to support the next owner-local schema change without another manual SQL repair. It should explicitly exclude coordinator databases, remote nodes, global rollout orchestration, and any cross-repo migration service.

### Risks
- Existing stale DBs may contain partial manual repairs, so migrations must be idempotent and inspect real SQLite metadata before altering schema.
- SQLite column/index upgrades can fail mid-flight if not wrapped carefully; bootstrap must avoid leaving the local DB half-upgraded.
- If migration is only triggered on `init` or only on `adopt`, existing adopted nodes that go straight to `status`, `current`, `tasks-start`, or MCP startup may still fail.

### Ready for Proposal
Yes — the proposal should tell the user to scope this as a supported owner-local node DB auto-upgrade path for stale adopted repositories, starting with the missing `tasks.lifecycle_key` migration and explicitly excluding coordinator/global migration machinery.
