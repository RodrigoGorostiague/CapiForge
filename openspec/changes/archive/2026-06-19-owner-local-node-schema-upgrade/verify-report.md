## Verification Report

**Change**: owner-local-node-schema-upgrade
**Version**: N/A
**Mode**: Standard

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 12 |
| Tasks complete | 12 |
| Tasks incomplete | 0 |

### Build & Tests Execution
**Build**: ➖ Not configured in `openspec/config.yaml`

**Targeted stale-node regression suites**: ✅ 72 passed / ❌ 0 failed / ⚠️ 0 skipped observed
```text
$ python3 -m unittest tests/storage/schema_node_test.py tests/node/bootstrap_cli_test.py tests/node/current_runtime_test.py tests/node/mcp_stdio_server_test.py
........................................................................
----------------------------------------------------------------------
Ran 72 tests in 10.802s

OK
```

**Broader validation suite**: ✅ 215 passed / ❌ 0 failed / ⚠️ 36 skipped observed
```text
$ python3 -m unittest
......................ss.ssss.....................................................................................................................................................ssssssssssssssssssssssssssssss.......
----------------------------------------------------------------------
Ran 215 tests in 22.042s

OK (skipped=36)
```

**Coverage**: ➖ Not available / threshold: 0

### Spec Compliance Matrix
| Requirement | Scenario | Test / Runtime Evidence | Result |
|-------------|----------|-------------------------|--------|
| Persistent owner-local initialization | Initialize a fresh local node | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_fresh_init_persists_initialized_state` | ✅ COMPLIANT |
| Persistent owner-local initialization | Reopen an existing local node home | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_init_is_idempotent_for_existing_bootstrap` | ✅ COMPLIANT |
| Persistent owner-local initialization | Upgrade a stale adopted local node on reopen | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_open_or_init_repairs_supported_stale_adopted_schema_on_reopen` | ✅ COMPLIANT |
| Persistent owner-local initialization | Fail closed on unsafe schema drift | `tests/storage/schema_node_test.py > NodeSchemaTest.test_from_file_rejects_unsupported_owner_local_drift_without_mutation` | ✅ COMPLIANT |
| Deterministic operational surface | Query actionable work | `tests/node/mcp_stdio_server_test.py > MCPStdioServerSmokeTest.test_stdio_server_supports_real_initialize_and_read_tool_flow` (`tasks_list_by_index`) | ✅ COMPLIANT |
| Deterministic operational surface | Report local bootstrap status | `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_status_and_read_upgrade_supported_stale_adopted_schema` | ✅ COMPLIANT |
| Deterministic operational surface | Reject command before required state | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_adopt_rejects_before_initialization`; `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_read_requires_adoption_before_access` | ✅ COMPLIANT |
| Deterministic operational surface | Upgrade stale schema before lifecycle access | `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_status_and_read_upgrade_supported_stale_adopted_schema`; `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_current_upgrades_supported_stale_adopted_schema_before_runtime_reads`; `tests/node/current_runtime_test.py > TasksReconcileStartIntegrationTest.test_reconcile_start_and_finish_upgrade_stale_owner_local_schema_before_lifecycle_access`; `tests/node/mcp_stdio_server_test.py > MCPStdioServerSmokeTest.test_stdio_server_upgrades_stale_owner_local_schema_before_lifecycle_reconcile_start` | ✅ COMPLIANT |
| Deterministic operational surface | Wait for an active bootstrap owner | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_open_or_init_waits_for_active_lock_owner` | ✅ COMPLIANT |
| Deterministic operational surface | Fail on timeout or suspect ownership | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_bootstrap_session_times_out_when_owner_does_not_release_lock`; `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_bootstrap_session_requires_explicit_recovery_for_stale_lock_file`; `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_bootstrap_session_treats_old_active_lock_owner_as_suspect` | ✅ COMPLIANT |
| Deterministic operational surface | Reject invalid negative lock timeout | `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_negative_lock_timeout_is_rejected_as_invalid_arguments` | ✅ COMPLIANT |

**Compliance summary**: 11/11 scenarios compliant

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Owner-local schema upgrade on reopen | ✅ Implemented | `runtime/node/store/__init__.py` routes existing DB opens through `_migrate_owner_local_schema()`, checks `PRAGMA user_version`, inspects `tasks` metadata, repairs `lifecycle_key` plus `idx_tasks_project_lifecycle_key`, and raises `LOCAL_SCHEMA_COMPATIBILITY_ERROR` on unsupported drift. |
| Canonical owner-local schema alignment | ✅ Implemented | `storage/node-schema.sql` declares `PRAGMA user_version = 1`, includes nullable `tasks.lifecycle_key`, and defines the partial unique index on `(project_id, lifecycle_key)` for non-null keys. |
| Shared upgrade boundary across bootstrap/runtime/MCP | ✅ Implemented | `runtime/node/bootstrap/__init__.py` reopens adopted stores through `NodeStore.from_file()` / `_open_adopted_store_unlocked()`, while `runtime/node/current.py` and `runtime/node/mcp_stdio.py` consume that shared adopted-store opener instead of side-channel SQLite access. |
| Task checklist completion | ✅ Implemented | `openspec/changes/owner-local-node-schema-upgrade/tasks.md` and `apply-progress.md` both show 12/12 completed with no remaining tasks. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Run upgrades at the shared node-open boundary | ✅ Yes | Existing DB opens flow through `connect_node_store()` / `NodeStore.from_file()` before bootstrap, CLI, runtime, or stdio logic touches lifecycle state. |
| Use version + metadata inspection for idempotent repair | ✅ Yes | Migration logic combines `PRAGMA user_version`, `PRAGMA table_info(tasks)`, and `sqlite_master` index SQL inspection before deciding whether to repair. |
| Fail closed on unsupported owner-local drift | ✅ Yes | Unsupported future versions and missing required `tasks` columns raise `SurfaceError("LOCAL_SCHEMA_COMPATIBILITY_ERROR", ...)` with rollback on SQLite migration failure. |
| Limit migration scope to repo-local owner DB | ✅ Yes | The implementation targets `.capiforge/node/node.sqlite3` through bootstrap-owned paths only; no coordinator or cross-repo migration path was introduced. |

### Issues Found
**CRITICAL**: None

**WARNING**: None

**SUGGESTION**:
- Coverage collection is still not configured in `openspec/config.yaml`; if this migration surface grows, add a coverage command so future verification can quantify branch coverage for schema-drift cases.

### Verdict
PASS
All 12 tasks are complete, all 11 scoped proposal/spec scenarios have passing runtime evidence, the targeted stale-schema regressions and broader unittest suite both passed, and the implementation matches the approved design for repo-local owner-node schema upgrades.
