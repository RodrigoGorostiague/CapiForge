# Apply Progress: Agent CapiForge Auto Task Lifecycle

## Status

- Mode: Standard
- Delivery: chained PR slice
- Chain strategy: feature-branch-chain
- Current slice: PR 5 Phase 5 cleanup — naming/help verification and final work-unit verification bookkeeping
- Scope boundary: build on the finish-time closeout slice, lock lifecycle naming/help text to the spec vocabulary, and finish the last verification pass without expanding feature scope

## Completed Tasks

- [x] 1.1 Update `storage/node-schema.sql` with nullable `tasks.lifecycle_key` and a per-project unique index that allows existing `NULL` rows.
- [x] 1.2 Extend `runtime/node/store/__init__.py` create/read paths to persist `lifecycle_key` and add exact `project_id + lifecycle_key` lookup helpers.
- [x] 1.3 Add schema/store tests in `tests/storage/schema_node_test.py` for uniqueness, null back-compat, and deterministic lookup/reuse.
- [x] 2.1 Add shared lifecycle validation/helpers in `runtime/node/current.py` for exact-key matching, required create seed fields, and same-project guardrails.
- [x] 2.2 Implement `tasks_reconcile_start` in `runtime/node/current.py` to reuse an existing task or create via `tasks_create_from_audit`, then claim and transition to `in_progress`.
- [x] 2.3 Extend `tests/mcp_cli/surface_test.py` for reuse of `ready|claimed|in_progress|blocked` lifecycle tasks and audit-backed create-only-on-miss behavior.
- [x] 3.1 Add stdio handlers/tool definitions in `runtime/node/mcp_stdio.py` for lifecycle start/finish plus any missing mutation surface needed by installed agents.
- [x] 3.2 Add JSON-envelope bootstrap commands in `runtime/bootstrap_cli.py` and route `capiforge tasks start|finish` in `runtime/cli.py` with deterministic argument validation.
- [x] 3.3 Extend `tests/node/mcp_stdio_server_test.py` and `tests/node/bootstrap_cli_test.py` for tool discovery, envelope parity, and owner-local same-project-only flows.
- [x] 4.1 Implement `tasks_reconcile_finish` in `runtime/node/current.py` to require an active matching claim, then close to `done` or `blocked` with required metadata.
- [x] 4.2 Ensure expired or released claims fail closed without mutation and optionally clean local claim cache after terminal closeout in `runtime/node/current.py` and `runtime/node/store/__init__.py`.
- [x] 4.3 Add integration coverage in `tests/mcp_cli/surface_test.py` for expired-claim rejection, explicit expiry outcome, and blocked/done closure metadata.
- [x] 5.1 Verify MCP/CLI naming and help text in `runtime/node/mcp_stdio.py`, `runtime/bootstrap_cli.py`, and `runtime/cli.py` stay English and match the spec terms.
- [x] 5.2 Run `python3 -m unittest` after each work unit and keep fixes/tests in the same slice before `sdd-apply` closeout.

## Verification

- `python3 -m unittest tests.storage.schema_node_test`
- `python3 -m unittest`
- `python3 -m unittest tests.node.current_runtime_test tests.mcp_cli.surface_test`
- `python3 -m unittest`
- `python3 -m unittest tests.node.bootstrap_cli_test tests.node.mcp_stdio_server_test`
- `python3 -m unittest`
- `python3 -m unittest tests.node.current_runtime_test tests.node.bootstrap_cli_test tests.node.mcp_stdio_server_test tests.mcp_cli.surface_test`
- `python3 -m unittest`
- `python3 -m unittest tests.node.bootstrap_cli_test tests.node.mcp_stdio_server_test`
- `python3 -m unittest`

## Files Changed

- `storage/node-schema.sql` — added nullable `lifecycle_key` column and per-project unique partial index.
- `runtime/node/store/__init__.py` — persisted lifecycle keys in task creation and added exact lookup helper.
- `tests/storage/schema_node_test.py` — added schema/store coverage for unique keys, NULL compatibility, and deterministic lookup.
- `runtime/node/current.py` — added lifecycle start validation helpers, same-project guards, and the owner-local `tasks_reconcile_start` wrapper.
- `runtime/node/mcp/__init__.py` — allowed audit-backed task creation to persist lifecycle keys and lifecycle creator metadata.
- `tests/node/current_runtime_test.py` — added integration coverage for create-on-miss, same-project guardrails, and reuse of ready/claimed/in-progress/blocked lifecycle tasks.
- `tests/mcp_cli/surface_test.py` — added lifecycle-key persistence assertions for audit-backed task creation.
- `runtime/node/mcp_stdio.py` — added MCP `tasks_reconcile_start` tooling with deterministic argument validation for lifecycle-start calls.
- `runtime/bootstrap_cli.py` — added `tasks-start` JSON-envelope command plus JSON parsing for lifecycle create-seed arguments.
- `runtime/cli.py` — routed `capiforge tasks start` to the bootstrap lifecycle-start wrapper.
- `tests/node/mcp_stdio_server_test.py` — added stdio + installed-command lifecycle-start coverage, including same-project rejection behavior.
- `tests/node/bootstrap_cli_test.py` — added bootstrap lifecycle-start coverage for reuse, create-on-miss, and same-project guardrails.
- `runtime/node/current.py` — added `tasks_reconcile_finish`, finish metadata validation, expiry/release-safe claim checks, and terminal closeout claim cleanup.
- `runtime/node/store/__init__.py` — added cached-claim cleanup used after successful lifecycle terminal closeout.
- `runtime/node/mcp_stdio.py` — exposed `tasks_reconcile_finish` alongside start tooling and updated stdio guidance text for lifecycle closeout.
- `runtime/bootstrap_cli.py` — added `tasks-finish` JSON-envelope support with deterministic closeout argument validation.
- `runtime/cli.py` — routed `capiforge tasks finish` to the bootstrap lifecycle-finish wrapper.
- `tests/node/current_runtime_test.py` — added runtime integration coverage for successful done closeout and expiry rejection.
- `tests/node/bootstrap_cli_test.py` — added bootstrap finish coverage for done closeout and explicit expiry failure.
- `tests/node/mcp_stdio_server_test.py` — added stdio tool discovery/closeout flow coverage plus installed-command `tasks finish` routing.
- `tests/mcp_cli/surface_test.py` — added closeout metadata persistence checks for `done`/`blocked` and expiry-state coordination regression coverage.
- `runtime/node/mcp_stdio.py` — aligned lifecycle tool descriptions and initialization guidance with owner-local/same-project spec terminology.
- `runtime/bootstrap_cli.py` — improved lifecycle command help text, argument help, and parser guidance for the JSON-envelope bootstrap surface.
- `runtime/cli.py` — aligned installed `tasks start|finish` help strings with the lifecycle spec language.
- `tests/node/bootstrap_cli_test.py` — added regression coverage for bootstrap help text terminology.
- `tests/node/mcp_stdio_server_test.py` — added regression coverage for MCP tool descriptions and installed-command help text, and fixed console-script cleanup to remove only the generated temp directory.

## Remaining Tasks

- None.

## Notes

- Phase 5 completed as the final owner-local cleanup slice for the feature-branch chain.
- While adding help-text regressions, the MCP stdio smoke test cleanup was corrected from deleting `/tmp` to deleting only the generated console-script directory; this was required to keep the full unittest suite stable.
