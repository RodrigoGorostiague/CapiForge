## Exploration: public audit creation and install-time lifecycle automation

### Current State
Completed-work lifecycle support already exists for owner-local same-project automation, but it depends on a pre-existing published audit. The public CLI/MCP surface exposes `tasks_claim`, `tasks_reconcile_start`, and `tasks_reconcile_finish`, while `tasks_reconcile_start` can only auto-create a task when the caller provides `origin_audit_id` plus full task seed metadata. There is no public CLI/MCP command to create or publish a brief audit, and the installer only bootstraps the repo plus MCP server config; it does not register any task-lifecycle skill, prompt contract, or automation hook.

### Affected Areas
- `runtime/node/current.py` — lifecycle start/finish wrappers already exist, but start hard-requires a published origin audit for create-on-miss.
- `runtime/node/mcp_stdio.py` — public installed MCP tools expose read/claim/lifecycle wrappers, but no audit-create or audit-publish tool.
- `runtime/bootstrap_cli.py` — CLI parity exists for lifecycle wrappers, but not for public audit creation.
- `runtime/cli.py` — top-level `capiforge tasks start|finish` routing exists; any new audit flow likely needs a sibling public command group.
- `runtime/node/mcp/__init__.py` — core task creation is audit-backed and owner-local; this is the right boundary for adding canonical audit mutation APIs.
- `runtime/node/store/__init__.py` — contains only local store helpers such as `create_audit`; today audit creation is internal, not product-facing.
- `openspec/specs/task-audit-model/spec.md` — tasks MUST originate from an audit, so public audit creation is a prerequisite for clean product-facing completed-work recording.
- `openspec/specs/mcp-cli-surface/spec.md` and `contracts/mcp-surface.md` — public surface contract currently lacks an audit create/publish operation.
- `scripts/installer_core.py` and `scripts/integration_config.py` — installer writes MCP config only; no automation artifact is installed beyond server registration.
- `skills/capiforge-pickup-task/SKILL.md`, `skills/capiforge-start-task/SKILL.md`, `skills/capiforge-close-task/SKILL.md` — skills exist, but installation does not wire them into OpenCode/CapiForge bootstrap behavior.

### Approaches
1. **Add a public audit-create/publish surface and keep lifecycle orchestration external** — expose product-facing audit creation, then let agent skills call audit create + lifecycle start + lifecycle finish explicitly.
   - Pros: Minimal runtime invention, aligns with existing skill split, preserves current task/audit boundaries.
   - Cons: Automation remains partly convention-based, and install-time setup still needs a separate mechanism to ensure agents actually use the flow.
   - Effort: Medium

2. **Add a public completed-work recording flow plus install-time automation bootstrap** — expose public brief-audit creation and wire installer-managed automation so installed agents can create the audit, create/reconcile the task, and close it through the product-facing path automatically.
   - Pros: Best fit for the requested outcome, removes direct DB seeding, and makes future sessions inherit the behavior after install.
   - Cons: Needs a clear automation boundary for OpenCode/agent startup, plus spec work for audit state transitions and deterministic lifecycle inputs.
   - Effort: High

### Recommendation
Recommend **Approach 2**. The clean slice is to add a public owner-local audit creation/publish API first, then define one installer-managed automation artifact that teaches installed agents to call `audit-create -> tasks_reconcile_start -> tasks_reconcile_finish` through the product-facing CLI/MCP flow. Keep V1 same-project and owner-local, and avoid hidden DB writes or non-deterministic background behavior.

### Risks
- The current public contract has no audit-create/publish operation, so the requested flow cannot be implemented by configuration alone.
- `tasks_reconcile_start` currently requires a published audit on create-on-miss, which means completed-work recording still needs an explicit audit lifecycle design.
- Installer integration currently writes MCP server config only; adding agent behavior may require repo-managed skill files, prompt/bootstrap docs, or an installer-written config fragment whose target format must stay stable.
- Fully automatic closeout can drift from user intent if the automation boundary is too implicit; the spec should keep required finish metadata explicit.

### Ready for Proposal
Yes — propose one change that adds a public brief-audit creation path plus installer-managed automation for OpenCode/CapiForge sessions, explicitly scoped to owner-local same-project flows and explicit finish metadata.
