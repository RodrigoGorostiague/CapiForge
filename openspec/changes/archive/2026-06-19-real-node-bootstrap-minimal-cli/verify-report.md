## Verification Report

**Change**: real-node-bootstrap-minimal-cli
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

**Tests**: ✅ 71 passed / ❌ 0 failed / ⚠️ 0 skipped observed
```text
$ python3 -m unittest
.......................................................................
----------------------------------------------------------------------
Ran 71 tests in 0.653s

OK
```

**Targeted bootstrap CLI tests**: ✅ Passed
```text
$ python3 -m unittest tests.node.bootstrap_cli_test
..........
----------------------------------------------------------------------
Ran 10 tests in 0.519s

OK
```

**Demo compatibility**: ✅ Passed
```text
$ python3 scripts/demo_v1_runtime.py --output-dir /tmp/opencode/real-node-bootstrap-minimal-cli-demo
Result: {"succeeded": true}
Evidence: owner/worker/coordinator bootstrap, canonical task creation, claim conflict blocking, claim release, and owner-acceptance routing all completed successfully.
```

**CLI subprocess runtime evidence**: ✅ Passed for the supported sequential flow
```text
$ python3 scripts/capiforge_cli.py status --repo-root <temp-repo> --node-home <temp-node-home>
status=ok, bootstrap_state=uninitialized

$ python3 scripts/capiforge_cli.py init --repo-root <temp-repo> --node-home <temp-node-home>
status=accepted, bootstrap_state=initialized

$ python3 scripts/capiforge_cli.py adopt --repo-root <temp-repo> --node-home <temp-node-home>
status=accepted, bootstrap_state=adopted

$ python3 scripts/capiforge_cli.py read --repo-root <temp-repo> --node-home <temp-node-home> --as-of 2026-06-19T13:45:00Z
status=ok, bootstrap_state=adopted, deterministic entrypoint returned for the adopted repo
```

**Coverage**: ➖ Not available / threshold: 0

### Spec Compliance Matrix
| Requirement | Scenario | Test / Runtime Evidence | Result |
|-------------|----------|-------------------------|--------|
| Persistent owner-local initialization | Initialize a fresh local node | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_fresh_init_persists_initialized_state` | ✅ COMPLIANT |
| Persistent owner-local initialization | Reopen an existing local node home | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_init_is_idempotent_for_existing_bootstrap` | ✅ COMPLIANT |
| Explicit seed project adoption | Adopt this repository after initialization | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_same_repo_adopt_is_idempotent`; `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_sequential_cli_flow_works_across_real_processes` | ✅ COMPLIANT |
| Explicit seed project adoption | Reject invalid adoption transition | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_adopt_rejects_before_initialization`; `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_adopt_rejects_non_repo_root_target` | ✅ COMPLIANT |
| Deterministic local state visibility | Inspect adopted local state | `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_reopen_persists_adoption_and_read_payloads_are_deterministic`; sequential subprocess smoke | ✅ COMPLIANT |
| Deterministic local state visibility | Read without mutation | `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_read_returns_adopted_repo_entrypoint_without_persisting_cache`; `tests/node/entrypoint_runtime_test.py > NodeRuntimeIntegrationTest.test_local_read_helper_returns_ephemeral_entrypoint`; sequential subprocess smoke | ✅ COMPLIANT |
| Deterministic operational surface | Query actionable work | `tests/e2e/multi_node_runtime_test.py > MultiNodeEndToEndScenarioTest.test_remote_traversal_reads_owner_routing_metadata` | ✅ COMPLIANT |
| Deterministic operational surface | Report local bootstrap status | `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_status_reports_uninitialized_envelope`; `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_sequential_cli_flow_works_across_real_processes` | ✅ COMPLIANT |
| Deterministic operational surface | Reject command before required state | `tests/node/bootstrap_cli_test.py > BootstrapPersistenceTest.test_adopt_rejects_before_initialization`; `tests/node/bootstrap_cli_test.py > BootstrapCliSurfaceTest.test_read_requires_adoption_before_access` | ✅ COMPLIANT |

**Compliance summary**: 9/9 scenarios compliant

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Persistent owner-local initialization | ✅ Implemented | `runtime/node/bootstrap/__init__.py` persists `bootstrap.json`, ensures durable SQLite creation through `NodeStore.from_file()`, and keeps `init` non-adopting. |
| Explicit seed project adoption | ✅ Implemented | `NodeBootstrap.adopt_repo()` requires prior init, seeds workspace/project rows, persists adopted metadata, and rejects different-repo replacement. |
| Deterministic local state visibility | ✅ Implemented | `scripts/capiforge_cli.py` exposes JSON `status`/`read`; `read` requires adoption and uses `NodeMCPSurface.project_entrypoint_get_local()` for non-persistent reads. |
| Deterministic operational surface delta | ✅ Implemented | CLI commands `init`, `adopt`, `status`, and `read` return `{status,data,error}` envelopes with explicit bootstrap-state errors. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Persist bootstrap state outside domain tables | ✅ Yes | `runtime/node/bootstrap/__init__.py` stores lifecycle state in `.capiforge/node/bootstrap.json`; no schema migration introduced. |
| Repo-local owner trust, not enrolled-actor trust | ✅ Yes | CLI local reads use `NodeMCPSurface.project_entrypoint_get_local()` with `local_node_id`; no coordinator enrollment is required. |
| JSON-only deterministic CLI responses | ✅ Yes | `scripts/capiforge_cli.py` prints one JSON envelope per command and returns explicit error payloads. |
| Demo compatibility through shared persistence helper reuse | ✅ Yes | `scripts/demo_v1_runtime.py` reuses `NodeStore.from_file()` and passed runtime verification. |

### Issues Found
**CRITICAL**: None

**WARNING**:
- Process-level evidence now accurately proves the supported sequential out-of-process CLI contract only. Overlapping `adopt` and `read` invocations remain out of scope for this slice; `NodeBootstrap.require_adopted()` can still observe pre-adoption manifest state if commands race across processes.

**SUGGESTION**:
- If concurrent CLI invocation must become supported behavior, define explicit synchronization or atomicity semantics for adoption completion before reads and add dedicated race-aware tests.

### Verdict
PASS WITH WARNINGS
All 12 tasks are complete, all 9 scoped spec scenarios now have passing runtime evidence including real subprocess sequential smoke coverage, and the implementation matches the design for the supported owner-local flow. Remaining caution is limited to unsupported overlapping process execution, which is not covered by this V1.1 scope.
