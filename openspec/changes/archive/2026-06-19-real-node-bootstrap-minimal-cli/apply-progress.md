# Apply Progress: Real Node Bootstrap and Minimal CLI

## Mode

Standard

## Completed Tasks

- [x] 1.1 Create `runtime/node/bootstrap/__init__.py` with `BootstrapState`, manifest load/save, and `uninitialized -> initialized -> adopted` guards.
- [x] 1.2 Update `runtime/node/store/__init__.py` with file-backed SQLite open/create helpers reused by bootstrap and demo paths.
- [x] 1.3 Add `tests/node/bootstrap_cli_test.py` cases for fresh init, init idempotency, adopt-before-init rejection, and same-repo adopt idempotency.
- [x] 2.1 Create `scripts/capiforge_cli.py` to dispatch `init`, `adopt`, `status`, and `read`, always printing `{status,data,error}` JSON.
- [x] 2.2 Extend `runtime/node/mcp/__init__.py` with a local-read helper that accepts the synthetic local actor without coordinator enrollment.
- [x] 2.3 Implement repo-only adoption in `runtime/node/bootstrap/__init__.py`, persisting adopted project metadata and rejecting different-repo replacement.
- [x] 2.4 Expand `tests/node/bootstrap_cli_test.py` for `status` envelopes, prerequisite-state errors, and `read` staying read-only for the adopted repo.
- [x] 3.1 Refactor `scripts/demo_v1_runtime.py` to reuse the shared persistent store/bootstrap helper instead of custom schema bootstrapping.
- [x] 3.2 Add integration assertions in `tests/node/bootstrap_cli_test.py` for reopen persistence, seeded workspace/project rows, and deterministic entrypoint payloads.
- [x] 3.3 Update `tests/node/entrypoint_runtime_test.py` or `tests/mcp_cli/surface_test.py` only where shared read helpers need compatibility coverage.
- [x] 4.1 Update `README.md` with the supported owner-local flow, `.capiforge/node/` layout, JSON command examples, and explicit non-goals.
- [x] 4.2 Run `python3 -m unittest` and verify scenarios for init, adopt, status, read, and demo compatibility before marking the slice ready.

## Verification

- Ran `python3 -m unittest`
- Result: pass (71 tests)
- Ran `python3 scripts/demo_v1_runtime.py --output-dir /tmp/opencode/slash-demo/real-node-bootstrap-minimal-cli`
- Result: pass (`summary["succeeded"] == true`)
- Ran `python3 -m unittest tests.node.bootstrap_cli_test`
- Result: pass (10 tests), including a real subprocess smoke that executes `status -> init -> adopt -> read` sequentially across separate Python processes

## Workload / PR Boundary

- Mode: chained PR slice
- Chain strategy: feature-branch-chain
- Current work unit: Work Unit 3 — demo reuse, compatibility coverage, docs, and final verification
- Boundary: reuses shared persistent node-store bootstrap in the demo, adds persistence/read compatibility assertions, documents the owner-local CLI flow, and verifies the complete unittest plus demo path; excludes any post-V1.1 coordinator enrollment UX or cross-node automation expansion
- Review budget impact: final focused slice stays within the approved documentation/integration boundary and closes the chain without reopening earlier work units

## Remaining Tasks

- [x] None.

## Notes

- Demo compatibility required mirroring the worker-owned linked project and recorded approvals so current project-scoped authorization and routed mutation guards remain satisfied.
- The local read helper remains non-persistent: CLI `read` and direct local surface coverage confirm deterministic entrypoint payloads without writing `project_entrypoints` cache rows.
- Post-verify remediation stayed intentionally narrow: evidence now proves the supported sequential out-of-process CLI contract, while the known adopt/read overlap race remains outside this minimal pass and does not expand runtime concurrency guarantees.
