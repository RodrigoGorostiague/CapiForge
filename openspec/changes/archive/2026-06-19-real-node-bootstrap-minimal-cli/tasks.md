# Tasks: Real Node Bootstrap and Minimal CLI

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 480-700 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> PR 2 -> PR 3 |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Persist bootstrap state and SQLite reopen helpers | PR 1 | Base = feature tracker; include unit tests for init/reopen/state guards |
| 2 | Add JSON CLI for init/adopt/status and local read wiring | PR 2 | Base = PR 1 branch; include command tests and error envelopes |
| 3 | Reuse bootstrap in demo and document operator flow | PR 3 | Base = PR 2 branch; include demo/test updates and README |

## Phase 1: Foundation / Persistence

- [x] 1.1 Create `runtime/node/bootstrap/__init__.py` with `BootstrapState`, manifest load/save, and `uninitialized -> initialized -> adopted` guards.
- [x] 1.2 Update `runtime/node/store/__init__.py` with file-backed SQLite open/create helpers reused by bootstrap and demo paths.
- [x] 1.3 Add `tests/node/bootstrap_cli_test.py` cases for fresh init, init idempotency, adopt-before-init rejection, and same-repo adopt idempotency.

## Phase 2: CLI Commands / Core Behavior

- [x] 2.1 Create `scripts/capiforge_cli.py` to dispatch `init`, `adopt`, `status`, and `read`, always printing `{status,data,error}` JSON.
- [x] 2.2 Extend `runtime/node/mcp/__init__.py` with a local-read helper that accepts the synthetic local actor without coordinator enrollment.
- [x] 2.3 Implement repo-only adoption in `runtime/node/bootstrap/__init__.py`, persisting adopted project metadata and rejecting different-repo replacement.
- [x] 2.4 Expand `tests/node/bootstrap_cli_test.py` for `status` envelopes, prerequisite-state errors, and `read` staying read-only for the adopted repo.

## Phase 3: Integration / Compatibility

- [x] 3.1 Refactor `scripts/demo_v1_runtime.py` to reuse the shared persistent store/bootstrap helper instead of custom schema bootstrapping.
- [x] 3.2 Add integration assertions in `tests/node/bootstrap_cli_test.py` for reopen persistence, seeded workspace/project rows, and deterministic entrypoint payloads.
- [x] 3.3 Update `tests/node/entrypoint_runtime_test.py` or `tests/mcp_cli/surface_test.py` only where shared read helpers need compatibility coverage.

## Phase 4: Docs / Verification

- [x] 4.1 Update `README.md` with the supported owner-local flow, `.capiforge/node/` layout, JSON command examples, and explicit non-goals.
- [x] 4.2 Run `python3 -m unittest` and verify scenarios for init, adopt, status, read, and demo compatibility before marking the slice ready.
