# Apply Progress: public-audit-create-and-install-automation

## Mode
Standard

## Review Boundary
- Delivery mode: chained PR slice
- Chain strategy: feature-branch-chain
- Current slice: PR 3 / Installer and OpenCode registration
- Boundary: register a deterministic OpenCode skills path plus installed automation artifact, wire installer install/update/remove/verify around that artifact, and cover the unavailable-artifact failure path

## Completed Tasks
- [x] 1.1 Add owner-local `audit_create_brief()` and `audit_publish()` in `runtime/node/mcp/__init__.py` with same-project and draft-state guards.
- [x] 1.2 Add adopted-project wrappers in `runtime/node/current.py` and audit state helpers in `runtime/node/store/__init__.py` for draft -> published transitions.
- [x] 1.3 Expose MCP handlers/schemas in `runtime/node/mcp_stdio.py` and CLI routing in `runtime/bootstrap_cli.py` + `runtime/cli.py` for `audit create` and `audit publish`.
- [x] 2.1 Update `runtime/node/current.py` so lifecycle start can consume a public published brief audit on create-miss and keep same-project execution-context validation.
- [x] 2.2 Tighten `runtime/bootstrap_cli.py` and `runtime/node/mcp_stdio.py` finish validation so `tasks_reconcile_finish` always requires explicit done/blocked metadata.
- [x] 2.3 Document the public audit + lifecycle sequence and trust boundary in `contracts/mcp-surface.md` and refresh `skills/capiforge-start-task/SKILL.md` to reference the supported flow.
- [x] 4.1 Extend `tests/node/current_runtime_test.py` for same-project audit publish, create-miss lifecycle start, finish metadata rejection, and claim-expiry rejection.
- [x] 4.2 Extend `tests/node/mcp_stdio_server_test.py` and `tests/node/bootstrap_cli_test.py` for audit tool/command envelopes, validation failures, and composed public flow parity.
- [x] 3.1 Extend `scripts/integration_config.py` to merge a versioned OpenCode automation artifact/config reference beside the MCP server entry.
- [x] 3.2 Update `scripts/installer_core.py` install/update/remove/verify paths to write, clean up, and validate that automation artifact deterministically.
- [x] 3.3 Add the repo-managed automation artifact under the installed OpenCode-facing path selected by the implementation and wire it to `audit_create_brief -> audit_publish -> tasks_reconcile_start -> tasks_reconcile_finish`.
- [x] 4.3 Extend `tests/install/setup_test.py` for install/update/remove/verify coverage of the OpenCode automation registration and unavailable-artifact failure path.

## Verification Evidence
- `python3 -m unittest tests.node.current_runtime_test tests.node.bootstrap_cli_test tests.node.mcp_stdio_server_test`
- Result: PASS (83 tests)
- `python3 -m unittest tests.install.setup_test`
- Result: PASS (13 tests, 8 skipped)

## Remaining Tasks
- None.

## Notes
- This slice keeps the feature-branch chain focused on runtime lifecycle composition: callers must publish a same-project audit before create-on-miss, and finish metadata is now rejected early on CLI/MCP surfaces before any task mutation.
- The installed OpenCode contract now uses a repo-managed skill copied into `~/.config/opencode/skills/capiforge-record-completed-work/` and registered via `skills.paths` beside the MCP server entry in `opencode.json`.
- Installer install/update rewrites that skill deterministically from the checkout, uninstall removes it, and verify reports an explicit issue when the installed artifact is missing.
