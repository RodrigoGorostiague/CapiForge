# Tasks: Public Audit Create and Install Automation

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 650-850 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> PR 2 -> PR 3 |
| Delivery strategy | auto-forecast |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Public audit create/publish surface | PR 1 | Base = feature/tracker branch; include CLI/MCP/docs/tests |
| 2 | Lifecycle create/finish automation flow | PR 2 | Base = PR 1 branch; keep task reconcile tests with code |
| 3 | Installer/OpenCode registration | PR 3 | Base = PR 2 branch; include install/remove/verify tests |

## Phase 1: Public Audit Foundation

- [x] 1.1 Add owner-local `audit_create_brief()` and `audit_publish()` in `runtime/node/mcp/__init__.py` with same-project and draft-state guards.
- [x] 1.2 Add adopted-project wrappers in `runtime/node/current.py` and audit state helpers in `runtime/node/store/__init__.py` for draft -> published transitions.
- [x] 1.3 Expose MCP handlers/schemas in `runtime/node/mcp_stdio.py` and CLI routing in `runtime/bootstrap_cli.py` + `runtime/cli.py` for `audit create` and `audit publish`.

## Phase 2: Lifecycle Record-Completed Flow

- [x] 2.1 Update `runtime/node/current.py` so lifecycle start can consume a public published brief audit on create-miss and keep same-project execution-context validation.
- [x] 2.2 Tighten `runtime/bootstrap_cli.py` and `runtime/node/mcp_stdio.py` finish validation so `tasks_reconcile_finish` always requires explicit done/blocked metadata.
- [x] 2.3 Document the public audit + lifecycle sequence and trust boundary in `contracts/mcp-surface.md` and refresh `skills/capiforge-start-task/SKILL.md` to reference the supported flow.

## Phase 3: Installer and OpenCode Automation

- [x] 3.1 Extend `scripts/integration_config.py` to merge a versioned OpenCode automation artifact/config reference beside the MCP server entry.
- [x] 3.2 Update `scripts/installer_core.py` install/update/remove/verify paths to write, clean up, and validate that automation artifact deterministically.
- [x] 3.3 Add the repo-managed automation artifact under the installed OpenCode-facing path selected by the implementation and wire it to `audit_create_brief -> audit_publish -> tasks_reconcile_start -> tasks_reconcile_finish`.

## Phase 4: Verification

- [x] 4.1 Extend `tests/node/current_runtime_test.py` for same-project audit publish, create-miss lifecycle start, finish metadata rejection, and claim-expiry rejection.
- [x] 4.2 Extend `tests/node/mcp_stdio_server_test.py` and `tests/node/bootstrap_cli_test.py` for audit tool/command envelopes, validation failures, and composed public flow parity.
- [x] 4.3 Extend `tests/install/setup_test.py` for install/update/remove/verify coverage of the OpenCode automation registration and unavailable-artifact failure path.
