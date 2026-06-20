# Proposal: Owner-local Node Schema Upgrade

## Proposal question round
- Questions to confirm later: Should auto-upgrade run on every adopted-node open path, how should partial manual repairs be treated, and do we fail closed on unknown future schema drift?
- Working assumptions: upgrade is automatic and repo-local, stale owner-local DBs are repaired idempotently on open, and unsupported drift returns an explicit local error instead of silent mutation.

## Intent
Prevent stale adopted owner-local node DBs from breaking lifecycle flows. Existing `.capiforge/node/node.sqlite3` files must auto-upgrade on open so operators never need manual SQL for schema columns or indexes such as `tasks.lifecycle_key`.

## Scope
### In Scope
- Add repo-local owner-node schema upgrade on existing DB open.
- Cover the known `tasks.lifecycle_key` column and unique index drift.
- Prove bootstrap/CLI/MCP reopen paths upgrade before lifecycle access.

### Out of Scope
- Coordinator, remote-node, or cross-repo migration machinery.
- General downgrade tooling or manual schema editing workflows.

## Capabilities
### New Capabilities
- None.

### Modified Capabilities
- `real-node-bootstrap`: reopening an adopted local node must repair supported stale owner-local schema before runtime use.
- `mcp-cli-surface`: owner-local bootstrap and lifecycle commands must benefit from open-time upgrade instead of requiring manual SQL.

## Approach
Introduce a versioned, idempotent owner-local migrator invoked from the existing node-open path. It inspects SQLite metadata, applies ordered local migrations inside a transaction, and keeps scope limited to `.capiforge/node/node.sqlite3`.

## Affected Areas
| Area | Impact | Description |
|------|--------|-------------|
| `runtime/node/store/__init__.py` | Modified | Run migrations when reopening an existing node DB. |
| `storage/node-schema.sql` | Modified | Keep canonical owner-local schema aligned with migrations. |
| `runtime/node/bootstrap/__init__.py` | Modified | Ensure all adopted-node open paths use upgraded stores. |
| `tests/node/bootstrap_cli_test.py` | Modified | Add stale-node reopen coverage. |
| `tests/node/current_runtime_test.py` | Modified | Prove lifecycle flows succeed after upgrade. |

## Risks
| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Partial manual repairs create mixed schema state | Med | Use metadata checks and idempotent migration steps. |
| Mid-upgrade failure leaves local DB inconsistent | Low | Wrap ordered migrations in one transaction and fail closed. |

## Rollback Plan
Revert the migrator entrypoint and migration metadata changes, restore previous open behavior, and recover affected local test DBs from backups or recreated fixtures.

## Dependencies
- Existing owner-local schema source in `storage/node-schema.sql`.

## Success Criteria
- [ ] Reopening an adopted stale local node auto-adds `tasks.lifecycle_key` and required indexes before lifecycle commands run.
- [ ] Operators can use owner-local open/read/start/finish flows without manual SQL on previously adopted repos.
