# Proposal: Agent CapiForge Auto Task Lifecycle

## Intent
Enable installed CapiForge MCP integrations to manage agent work automatically: reconcile a task on start, create one when justified, claim it, enter `in_progress`, and close as `done` or `blocked` on finish without per-task prompting.

## Scope

### In Scope
- Owner-local, same-project lifecycle reconciliation triggered by installed MCP integration.
- Deterministic matching via an explicit lifecycle key, never fuzzy text matching.
- Automatic start/finish wrappers that enforce claim validity, `in_progress`, `done`, and `blocked` metadata.

### Out of Scope
- Cross-project routing, coordinator-first lifecycle automation, or human approval changes beyond current rules.
- Fuzzy equivalence matching, background claim renewal daemons, or autonomous multi-task planning.

## Capabilities

### New Capabilities
- `agent-task-lifecycle`: deterministic owner-local rules for automatic start/create/finish flows.

### Modified Capabilities
- `mcp-cli-surface`: add product-facing lifecycle reconciliation operations and activation semantics once MCP is configured.
- `task-audit-model`: define the audit-backed creation path for auto-created lifecycle tasks and closure metadata.
- `multi-agent-claims`: define lease validity and finish-time behavior when a claim expires before close.

## Approach
Add high-level lifecycle wrappers above existing runtime primitives. On start, resolve the adopted project, match by lifecycle key, create only through an explicit audit-safe path, claim, then transition to `in_progress`. On finish, require a valid claim; close to `done` or `blocked` with reason. Local-first is the V1 safety boundary.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `runtime/node/current.py` | Modified | Reconcile start/finish helpers |
| `runtime/node/mcp_stdio.py` | Modified | New MCP tool surface |
| `runtime/bootstrap_cli.py` | Modified | CLI parity for lifecycle wrappers |
| `runtime/node/store/__init__.py` | Modified | Lifecycle-key persistence |
| `openspec/specs/agent-task-lifecycle/spec.md` | New | Reconciliation contract |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Auto-create violates audit-origin rule | High | Specify one explicit audit-backed bootstrap path before apply |
| Claim expires mid-session | Med | Define renewal/fail-close policy in specs |
| Automation expands beyond local authority | Med | Keep V1 owner-local and same-project only |

## Rollback Plan
Disable the new lifecycle wrappers and fall back to explicit `tasks_ready_get` plus `tasks_claim`; no migration is required.

## Dependencies

- Existing task mutation primitives.
- Current adopted-project bootstrap model and published-audit workflow.

## Success Criteria

- [ ] Installed/configured MCP agents can start same-project work and reach `in_progress` with a valid claim automatically.
- [ ] Finishing work closes the task to `done` or `blocked` with required metadata and no per-task prompt.
- [ ] V1 never creates or mutates cross-project lifecycle state.

## Proposal Question Round
- Confirm the single V1 lifecycle key source.
- Confirm the audit-backed bootstrap path allowed for auto-created tasks.
- Confirm finish behavior after claim expiry.
