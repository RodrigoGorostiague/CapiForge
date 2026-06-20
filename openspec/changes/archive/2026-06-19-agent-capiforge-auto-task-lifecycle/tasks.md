# Tasks: Agent CapiForge Auto Task Lifecycle

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 550-800 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 -> PR 2 -> PR 3 |
| Delivery strategy | auto-forecast |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Owner-local lifecycle storage and start wrapper | PR 1 | Same-project only; base behavior + tests |
| 2 | MCP stdio and CLI lifecycle surfaces | PR 2 | Adds tool/command parity on top of PR 1 |
| 3 | Finish/expiry safe closeout and regression tests | PR 3 | Expiry failure, blocked/done closeout, polish |

## Phase 1: Foundation / Storage

- [x] 1.1 Update `storage/node-schema.sql` with nullable `tasks.lifecycle_key` and a per-project unique index that allows existing `NULL` rows.
- [x] 1.2 Extend `runtime/node/store/__init__.py` create/read paths to persist `lifecycle_key` and add exact `project_id + lifecycle_key` lookup helpers.
- [x] 1.3 Add schema/store tests in `tests/storage/schema_node_test.py` for uniqueness, null back-compat, and deterministic lookup/reuse.

## Phase 2: Owner-local reconcile start

- [x] 2.1 Add shared lifecycle validation/helpers in `runtime/node/current.py` for exact-key matching, required create seed fields, and same-project guardrails.
- [x] 2.2 Implement `tasks_reconcile_start` in `runtime/node/current.py` to reuse an existing task or create via `tasks_create_from_audit`, then claim and transition to `in_progress`.
- [x] 2.3 Extend `tests/mcp_cli/surface_test.py` for reuse of `ready|claimed|in_progress|blocked` lifecycle tasks and audit-backed create-only-on-miss behavior.

## Phase 3: MCP stdio and CLI wiring

- [x] 3.1 Add stdio handlers/tool definitions in `runtime/node/mcp_stdio.py` for lifecycle start/finish plus any missing mutation surface needed by installed agents.
- [x] 3.2 Add JSON-envelope bootstrap commands in `runtime/bootstrap_cli.py` and route `capiforge tasks start|finish` in `runtime/cli.py` with deterministic argument validation.
- [x] 3.3 Extend `tests/node/mcp_stdio_server_test.py` and `tests/node/bootstrap_cli_test.py` for tool discovery, envelope parity, and owner-local same-project-only flows.

## Phase 4: Finish-time safety / closeout

- [x] 4.1 Implement `tasks_reconcile_finish` in `runtime/node/current.py` to require an active matching claim, then close to `done` or `blocked` with required metadata.
- [x] 4.2 Ensure expired or released claims fail closed without mutation and optionally clean local claim cache after terminal closeout in `runtime/node/current.py` and `runtime/node/store/__init__.py`.
- [x] 4.3 Add integration coverage in `tests/mcp_cli/surface_test.py` for expired-claim rejection, explicit expiry outcome, and blocked/done closure metadata.

## Phase 5: Cleanup / Verification

- [x] 5.1 Verify MCP/CLI naming and help text in `runtime/node/mcp_stdio.py`, `runtime/bootstrap_cli.py`, and `runtime/cli.py` stay English and match the spec terms.
- [x] 5.2 Run `python3 -m unittest` after each work unit and keep fixes/tests in the same slice before `sdd-apply` closeout.
