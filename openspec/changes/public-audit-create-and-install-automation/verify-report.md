## Verification Report

**Change**: public-audit-create-and-install-automation
**Version**: N/A
**Mode**: Standard

### Completeness
| Metric | Value |
|--------|-------|
| Tasks total | 14 |
| Tasks complete | 14 |
| Tasks incomplete | 0 |

### Build & Tests Execution
**Build**: ➖ Not applicable
```text
No separate build/type-check command is defined for this Python stdlib unittest project.
Verification relied on runtime execution evidence from the targeted runtime, CLI, MCP stdio, and installer suites.
```

**Tests**: ❌ 88 passed / ❌ 4 failed / ⚠️ 8 skipped
```text
$ python3 -m unittest tests.node.current_runtime_test
Ran 11 tests in 0.203s
FAILED (errors=2)
- tests.node.current_runtime_test.TasksReconcileStartIntegrationTest.test_reconcile_start_creates_missing_task_from_audit_and_claims_it
- tests.node.current_runtime_test.TasksReconcileStartIntegrationTest.test_reconcile_start_composes_public_audit_publish_before_create_on_miss
Error: KeyError: 'origin_audit_id'

$ python3 -m unittest tests.node.bootstrap_cli_test
Ran 53 tests in 6.125s
FAILED (errors=1)
- tests.node.bootstrap_cli_test.BootstrapCliSurfaceTest.test_audit_create_and_publish_commands_return_json_envelopes
Error: KeyError: 'origin_audit_id'

$ python3 -m unittest tests.node.mcp_stdio_server_test
Ran 19 tests in 3.948s
FAILED (errors=1)
- tests.node.mcp_stdio_server_test.MCPStdioServerSmokeTest.test_stdio_server_composes_public_audit_publish_before_lifecycle_create
Error: KeyError: 'origin_audit_id'

$ python3 -m unittest tests.install.setup_test
Ran 17 tests in 11.125s
OK (skipped=8)
```

**Coverage**: ➖ Not available

### Spec Compliance Matrix
| Requirement | Scenario | Test | Result |
|-------------|----------|------|--------|
| MCP CLI Surface — Public brief-audit create and publish operations | Create and publish a brief audit publicly | `tests.node.bootstrap_cli_test > test_audit_create_and_publish_commands_return_json_envelopes`; `tests.node.mcp_stdio_server_test > test_stdio_server_supports_public_audit_tool_flow`; `tests.node.current_runtime_test > test_audit_publish_promotes_adopted_project_draft_and_rejects_foreign_audit` | ❌ FAILING |
| MCP CLI Surface — Public brief-audit create and publish operations | Reject incomplete or out-of-bound publish | `tests.node.bootstrap_cli_test > test_audit_publish_rejects_foreign_project_audit`; stdio argument validation tests in `tests.node.mcp_stdio_server_test` | ✅ COMPLIANT |
| MCP CLI Surface — Automatic agent lifecycle operations | Start work after public audit publication | `tests.node.current_runtime_test > test_reconcile_start_composes_public_audit_publish_before_create_on_miss`; `tests.node.mcp_stdio_server_test > test_stdio_server_composes_public_audit_publish_before_lifecycle_create` | ❌ FAILING |
| MCP CLI Surface — Automatic agent lifecycle operations | Fail finish without a valid claim | `tests.node.current_runtime_test > test_reconcile_finish_rejects_expired_claim_without_terminal_mutation`; matching CLI/MCP finish rejection tests | ✅ COMPLIANT |
| MCP CLI Surface — Automatic agent lifecycle operations | Reject finish without explicit metadata | finish metadata validation tests in `tests.node.current_runtime_test`, `tests.node.bootstrap_cli_test`, and `tests.node.mcp_stdio_server_test` | ✅ COMPLIANT |
| Installed Agent Automation — Installer-managed completed-work contract | Install exposes the automation artifact | `tests.install.setup_test > test_install_update_uninstall_flow`; `tests.install.setup_test > test_opencode_merge_and_remove` | ✅ COMPLIANT |
| Installed Agent Automation — Installer-managed completed-work contract | Missing artifact stays visible | `tests.install.setup_test > test_install_update_uninstall_flow` | ✅ COMPLIANT |
| Installed Agent Automation — Public-surface lifecycle execution | Record completed work through installed automation | Runtime/CLI/MCP composed-flow tests above | ❌ FAILING |
| Installed Agent Automation — Public-surface lifecycle execution | Stop after a public-surface failure | draft-origin rejection tests in runtime/CLI/MCP suites | ✅ COMPLIANT |
| Agent Task Lifecycle — Start-time reconciliation | Reuse an existing lifecycle task | `tests.node.current_runtime_test > test_reconcile_start_reuses_ready_claimed_in_progress_and_blocked_tasks` | ✅ COMPLIANT |
| Agent Task Lifecycle — Start-time reconciliation | Create a lifecycle task from the public brief-audit path | `tests.node.current_runtime_test > test_reconcile_start_composes_public_audit_publish_before_create_on_miss`; CLI/MCP composed-flow tests | ❌ FAILING |
| Agent Task Lifecycle — Finish-time closure and failure handling | Finish lifecycle work as done | done-finish runtime/CLI/MCP tests | ✅ COMPLIANT |
| Agent Task Lifecycle — Finish-time closure and failure handling | Reject finish after lease expiry or metadata failure | expiry and explicit-metadata rejection tests in runtime/CLI/MCP suites | ✅ COMPLIANT |
| Task Audit Model — Brief-audit publication boundary | Publish a same-project brief audit | public audit publish tests in runtime/CLI/MCP suites | ✅ COMPLIANT |
| Task Audit Model — Brief-audit publication boundary | Reject cross-project or incomplete publication | foreign audit publish rejection tests in runtime/CLI/MCP suites | ✅ COMPLIANT |
| Task Audit Model — Task-centered operations | Auto-create a lifecycle task from a published brief audit | composed public-audit lifecycle tests in runtime/CLI/MCP suites | ❌ FAILING |

**Compliance summary**: 11/16 scenarios compliant

### Correctness (Static Evidence)
| Requirement | Status | Notes |
|------------|--------|-------|
| Public owner-local audit create/publish APIs exist | ✅ Implemented | `runtime/node/mcp/__init__.py`, `runtime/node/current.py`, `runtime/node/mcp_stdio.py`, `runtime/bootstrap_cli.py`, and `runtime/cli.py` expose the public draft/publish flow. |
| Same-project published audit is required before lifecycle create-on-miss | ✅ Implemented | `runtime/node/current.py` calls `_require_published_origin_audit()` before task creation. |
| Finish still requires explicit metadata and valid claim | ✅ Implemented | `runtime/node/current.py` plus CLI/MCP validation paths reject missing finish metadata and expired claims. |
| Installed automation artifact is repo-managed and installer-written | ✅ Implemented | `runtime/installer/integration_config.py`, `runtime/installer/core.py`, and `skills/capiforge-record-completed-work/SKILL.md` provide deterministic install/update/remove/verify behavior. |
| Lifecycle create/start response preserves composed-flow origin audit reference | ❌ Incomplete | `tasks_reconcile_start()` returns `task_id`, `claim_id`, `state`, and lifecycle metadata but omits `origin_audit_id`, causing runtime, CLI, and MCP suite failures. |

### Coherence (Design)
| Decision | Followed? | Notes |
|----------|-----------|-------|
| Add canonical owner-local `audit_create_brief` / `audit_publish` operations | ✅ Yes | Implemented in `runtime/node/mcp/__init__.py` and wrapped in adopted-project runtime surfaces. |
| Keep create and publish as separate visible steps | ✅ Yes | Separate CLI and MCP commands/tools exist for create and publish. |
| Install one repo-managed automation artifact via stable config boundary | ✅ Yes | OpenCode `skills.paths` registration and copied `capiforge-record-completed-work` artifact are implemented and installer-verified. |
| Enforce owner-local same-project scope guards | ✅ Yes | Public publish and lifecycle create-on-miss reject foreign-project or invalid execution-context usage. |
| Preserve a reviewable composed public flow across runtime/CLI/MCP surfaces | ⚠️ Partial | Composition works, but return envelopes are inconsistent with the tested contract because `origin_audit_id` is missing from lifecycle-start results. |

### Issues Found
**CRITICAL**:
- Relevant verification suites fail in runtime, CLI, and MCP stdio because lifecycle-start results omit `origin_audit_id` during create-on-miss/public-audit composition.
- The failing tests block verification for the public composed flow and prevent this change from meeting the runtime-evidence gate.

**WARNING**:
- Tasks are all checked complete, but the checked verification tasks do not currently match executable reality; the change is not archive-ready.

**SUGGESTION**:
- Align the lifecycle-start return envelope across runtime, CLI, and MCP layers with the composed-flow test contract, then rerun the targeted suites and refresh this verify report.

### Verdict
FAIL
Core runtime evidence is failing in the public audit → lifecycle start flow, so proposal/spec/design/task completion is not yet proven.
