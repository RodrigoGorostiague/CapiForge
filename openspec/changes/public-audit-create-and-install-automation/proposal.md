# Proposal: Public Audit Create and Install Automation

## Intent
Enable product-facing completed-work recording without local store seeding by adding a public brief-audit publish path and installer-managed lifecycle automation. Trust stays owner-local and same-project; automation must be explicit, deterministic, and reviewable.

## Scope

### In Scope
- Public CLI/MCP flow to create and publish a brief audit for owner-local same-project work.
- Lifecycle start/create/finish automation that reuses existing wrappers where possible and still requires explicit finish metadata.
- Install-time delivery of one stable skill/config/hook artifact so installed sessions inherit the behavior.

### Out of Scope
- Cross-project audit/task creation, coordinator-routed writes, or background autonomous closeout.
- Replacing the task/audit model, hidden DB mutation shortcuts, or undocumented prompt-only behavior.

## Capabilities

### New Capabilities
- `installed-agent-automation`: deterministic install-time artifact that registers the completed-work lifecycle contract for installed agent sessions.

### Modified Capabilities
- `mcp-cli-surface`: add public audit create/publish operations and lifecycle activation semantics for installed automation.
- `task-audit-model`: define the brief-audit path that can justify same-project lifecycle task creation while preserving audit publication controls.
- `agent-task-lifecycle`: allow installed lifecycle start flows to use the new public audit path before same-project task reconciliation.

## Approach
Expose canonical owner-local audit mutation APIs above existing store helpers, then have one installed automation artifact call `audit-create -> audit-publish -> tasks_reconcile_start -> tasks_reconcile_finish`. Keep canonical writes on the adopted owner node only; shared MCP clients can invoke the flow but never bypass local authority.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `runtime/node/mcp/__init__.py` | Modified | Canonical public audit create/publish boundary |
| `runtime/node/mcp_stdio.py` | Modified | MCP tools for audit create/publish |
| `runtime/bootstrap_cli.py` | Modified | CLI parity for public audit flow |
| `scripts/installer_core.py` | Modified | Install automation artifact wiring |
| `skills/capiforge-start-task/SKILL.md` | Modified | Stable lifecycle contract consumption |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Automation closes work too implicitly | Med | Keep finish metadata required and reject silent closeout |
| Install hook format drifts | Med | Specify one stable repo-managed artifact and version it |
| Public audit mutation weakens boundaries | Med | Restrict writes to owner-local same-project flows |

## Rollback Plan
Remove the installed automation artifact and disable public audit commands, falling back to manual published-audit plus existing lifecycle wrappers; no cross-project migration is introduced.

## Dependencies
- Existing owner-local adopted-project bootstrap and lifecycle wrappers.
- Current task and audit state validation rules.

## Success Criteria
- [ ] Installed agents can record completed same-project work through public audit creation without local store seeding.
- [ ] Automation uses a documented installed artifact, not prompt-only convention.
- [ ] Finish-time closure still enforces explicit metadata and owner-local authority.

## Proposal Question Round
- Confirm the minimum brief-audit fields required before publish.
- Confirm where the installed automation artifact should live and how it is versioned.
- Confirm whether audit publish and lifecycle start stay separate visible steps or one wrapped public action.
