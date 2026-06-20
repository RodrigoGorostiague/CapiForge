# Design: Public Audit Create and Install Automation

## Technical Approach

Add one owner-local public audit path on top of the existing adopted-project wrappers, then let installed automation call only product-facing surfaces. The runtime change stays inside the current bootstrap → current wrapper → `NodeMCPSurface` stack: create a brief audit as `draft`, publish it explicitly, then feed its `audit_id` into the existing `tasks_reconcile_start` / `tasks_reconcile_finish` flow. Installer work extends the existing OpenCode integration writer so install/update always register one deterministic automation artifact through a stable config/skill boundary.

## Architecture Decisions

| Topic | Choice | Alternatives | Rationale |
|---|---|---|---|
| Audit mutation boundary | Add canonical owner-local `audit_create_brief` and `audit_publish` operations in `runtime/node/mcp/__init__.py`, consumed by adopted wrappers and stdio/CLI | Direct `NodeStore.create_audit()` exposure; hidden installer-side DB writes | Matches the existing lifecycle wrapper pattern, keeps owner authority checks in one place, and preserves a reviewable product surface. |
| Publish model | Keep create and publish as separate visible steps; automation may compose them into one deterministic sequence | Single implicit “record completed work” mutation | Preserves explicit lifecycle state, lets humans inspect drafts, and avoids a hidden side channel while still allowing automation to orchestrate the public steps. |
| Install automation | Write one repo-managed OpenCode automation artifact plus config reference during install/update | Prompt-only convention; multiple per-user scripts/hooks | The installer already owns MCP config registration. Extending that stable boundary keeps automation deterministic, versioned with the repo, and easy to verify/remove. |
| Scope guard | Enforce owner-local, adopted-project only in audit create/publish and lifecycle wrappers | Cross-project publish/create in V1 | Aligns with current `tasks_reconcile_start` same-project validation and proposal scope; avoids weakening trust boundaries before routing rules exist. |

## Data Flow

    Installed agent / user
      │ brief audit payload
      ▼
    OpenCode skill/config hook
      ▼
    MCP stdio / CLI public commands
      ▼
    runtime.node.current wrappers
      ├── audit_create_brief(draft)
      ├── audit_publish(published)
      ├── tasks_reconcile_start(origin_audit_id=audit_id)
      └── tasks_reconcile_finish(done|blocked)

Threat model: canonical writes remain on the adopted owner node; automation may invoke the flow but MUST NOT bypass `NodeMCPSurface`; cross-project identifiers in execution context remain rejected; finish still requires explicit closeout metadata and an active claim.

## File Changes

| File | Action | Description |
|---|---|---|
| `runtime/node/mcp/__init__.py` | Modify | Add canonical brief-audit create/publish methods with owner-local authorization and publish-state validation. |
| `runtime/node/current.py` | Modify | Add adopted-project audit wrappers reused by CLI/MCP public flow. |
| `runtime/node/mcp_stdio.py` | Modify | Expose `audit_create_brief` and `audit_publish` MCP tools with JSON validation. |
| `runtime/bootstrap_cli.py` | Modify | Add JSON-envelope audit commands that mirror stdio behavior. |
| `runtime/cli.py` | Modify | Add public `audit create` / `audit publish` command routing beside existing `tasks` commands. |
| `runtime/node/store/__init__.py` | Modify | Add small audit lookup/update helpers for state transitions without exposing store-only side paths. |
| `contracts/mcp-surface.md` | Modify | Document public audit commands, statuses, and owner-local trust boundary. |
| `scripts/integration_config.py` | Modify | Merge a stable OpenCode automation reference alongside MCP registration. |
| `scripts/installer_core.py` | Modify | Install/update/remove/verify the automation artifact deterministically. |
| `skills/capiforge-start-task/SKILL.md` | Modify | Reference the installed lifecycle contract as the supported automation boundary. |
| `tests/node/current_runtime_test.py` | Modify | Cover audit draft→publish→reconcile start flow and same-project rejection. |
| `tests/node/mcp_stdio_server_test.py` | Modify | Cover new audit MCP tools and composed installed flow. |
| `tests/node/bootstrap_cli_test.py` | Modify | Cover CLI parity and envelope shape. |
| `tests/install/setup_test.py` | Modify | Verify installer writes/removes/verifies the automation artifact. |

## Interfaces / Contracts

```python
audit_create_brief(title, content, *, project_id=adopted_project) -> {audit_id, state="draft"}
audit_publish(audit_id) -> {audit_id, state="published"}
```

`audit_create_brief` MUST create on the adopted project only. V1 brief audits should require non-empty `title` and `content`; richer fields remain automation metadata in the later task justification/execution context. `audit_publish` MUST reject foreign-project audits and non-draft/non-published transitions.

## Testing Strategy

| Layer | What to Test | Approach |
|---|---|---|
| Unit | Audit state validation, adopted-project guard, installer config merge | Extend `unittest` coverage for wrapper/helper functions. |
| Integration | Public audit create/publish plus lifecycle start/finish composition | Extend node and stdio integration suites. |
| E2E | Install/update/verify produces a usable automation boundary | Extend installer tests around written OpenCode config/artifact paths. |

## Migration / Rollout

No migration required. Rollout is additive: new audit commands, new installer-written automation artifact, and docs/skill updates. Existing installed configs keep working; reinstall/update registers the automation contract.

## Open Questions

- [ ] Confirm the final OpenCode artifact shape: dedicated skill file reference, config hook block, or both if one only points to the other.
- [ ] Confirm whether `audit publish` should be user-visible in docs even if installed automation normally calls it immediately after create.
