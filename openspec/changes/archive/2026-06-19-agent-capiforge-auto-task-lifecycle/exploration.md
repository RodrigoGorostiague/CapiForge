## Exploration: automatic CapiForge task lifecycle reconciliation for agent work

### Current State
The repo already has a real task lifecycle model in the runtime: tasks can be created from a published audit, claimed with an exclusive lease, transitioned to `in_progress`, moved to `blocked`, and closed as `done`. However, the installed CLI and stdio MCP surface only expose read flows plus `tasks_claim` (`current_get`, `tasks_ready_get`, `tasks_list_by_index`, `workspace_get_current`, `project_entrypoint_get`, `sync_status`, `tasks_claim`). The higher-value mutation APIs that the runtime already implements internally — `tasks_create_from_audit`, `tasks_transition`, `tasks_release`, and `tasks_override` — are not exposed on the product-facing MCP surface.

That means the current repo supports **manual pickup** through MCP, but not the full automatic lifecycle the user asked for. There is also no existing equivalence matcher for “this agent request maps to that existing task”, and automatic task creation is constrained by the spec rule that every task must originate from a published audit.

### Affected Areas
- `runtime/node/mcp/__init__.py` — already contains the core lifecycle primitives (`tasks_create_from_audit`, `tasks_transition`, `tasks_release`) that automatic reconciliation would need.
- `runtime/node/mcp_stdio.py` — defines the installed MCP tool list and currently exposes only read flows plus `tasks_claim`.
- `runtime/node/current.py` — provides the current product-facing helper pattern for adopted-project reads and claiming; likely the right place for higher-level lifecycle wrappers.
- `runtime/bootstrap_cli.py` — mirrors the product-facing local command surface and would need alignment if lifecycle wrappers become first-class commands.
- `runtime/shared/contracts.py` — enforces readiness, justification, and active-claim requirements that automatic flows must satisfy.
- `runtime/node/store/__init__.py` — persists task metadata and claim cache; relevant for deterministic task matching keys and blocked/done metadata.
- `openspec/specs/task-audit-model/spec.md` — forces the audit-origin rule and terminal metadata requirements.
- `openspec/specs/mcp-cli-surface/spec.md` and `contracts/mcp-surface.md` — define the public MCP/CLI contract that currently stops short of automatic lifecycle reconciliation.
- `skills/capiforge-pickup-task/SKILL.md`, `skills/capiforge-start-task/SKILL.md`, `skills/capiforge-close-task/SKILL.md` — show the current intended orchestration as three separate explicit phases.

### Approaches
1. **Expose low-level mutation tools and keep orchestration in agent skills** — add MCP tools for create/transition/release and let orchestrators stitch pickup/start/close automatically.
   - Pros: Reuses existing runtime primitives, minimal domain invention, keeps lifecycle steps explicit and debuggable.
   - Cons: Still spreads logic across agent orchestration layers, does not give one canonical “reconcile lifecycle for this work session” entrypoint, leaves equivalent-task detection underspecified.
   - Effort: Medium

2. **Add a high-level lifecycle reconciliation surface** — introduce product-facing MCP wrappers for `reconcile_start` and `reconcile_finish` (or equivalent names) that read current state, match or create a task deterministically, claim it, move it to `in_progress`, and later close it as `done` or `blocked`.
   - Pros: Best match for the requested UX, centralizes policy, keeps future agents from reimplementing lifecycle rules differently.
   - Cons: Requires a clear deterministic matching key, a decision on how automatic task creation satisfies the audit-origin requirement, and likely a lease-renewal strategy for longer tasks.
   - Effort: High

### Recommendation
Recommend **Approach 2**, but scoped tightly: add **high-level owner-local lifecycle reconciliation wrappers** on top of the existing runtime primitives, while explicitly deferring cross-project routing and fuzzy matching.

The safest version of this change is:
- deterministic same-project matching only, based on a stable work key such as the OpenSpec change name or another explicit lifecycle key;
- owner-local/adopted-project flow only;
- automatic start ends with a valid claim plus `in_progress`;
- automatic finish defaults to `done`, but requires a blocked reason when closing incomplete work as `blocked`;
- no implicit cross-project creation/routing in V1;
- proposal/spec must decide whether automatic creation uses a dedicated published audit bootstrap pattern or expands the model to support another justified origin.

### Risks
- The current spec says every task must originate from a **published audit**, so automatic task creation from arbitrary agent work is not fully specified yet.
- There is no exposed MCP tool for `tasks_transition`, `tasks_create_from_audit`, or claim renewal today, so automatic start/finish cannot be implemented only by wiring existing product-facing tools together.
- The default claim lease is 5 minutes and the coordinator registry supports renewal internally, but there is no surfaced renewal flow; longer agent sessions may lose claim validity before finish.
- “Equivalent task” matching is currently undefined. Fuzzy text matching would be fragile; this change should stay with deterministic lifecycle keys.
- Current sync is degraded owner-local (`canonical_write_path: owner_node_local`), so automatic lifecycle should not promise coordinator-backed multi-node reconciliation in the first slice.

### Ready for Proposal
Yes — but the proposal should tell the user that the first safe slice is **owner-local automatic same-project lifecycle reconciliation with deterministic task keys**, and it must explicitly resolve the audit-origin rule plus lease-renewal policy before implementation.
