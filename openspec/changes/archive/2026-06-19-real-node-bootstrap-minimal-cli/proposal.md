# Proposal: Real Node Bootstrap and Minimal CLI

## Intent

Turn the repo's demo-only persistent bootstrap into a supported V1.1 owner-local product path. Operators need to initialize a local node, explicitly adopt this CapiForge repo as the owned project, inspect status, and read deterministic project data without implicit adoption or coordinator automation.

## Scope

### In Scope
- Persistent local node bootstrap for a single owner node using existing SQLite schemas.
- Explicit CLI adoption of this repository as the seed project; bootstrap MUST NOT auto-adopt.
- Minimal CLI commands: `init`, `adopt`, `status`, `read`.
- Read/status flows that expose local node identity, storage paths, adopted project metadata, and deterministic entrypoint data.

### Out of Scope
- Coordinator enrollment, LAN workflows, claims orchestration, and cross-node routing automation.
- Broad mutation/authoring CLI flows, packaging expansion, or multi-project automation beyond the first adopted repo.

## Capabilities

### New Capabilities
- `real-node-bootstrap`: Persistent owner-local node initialization and explicit project adoption for one local project.

### Modified Capabilities
- `mcp-cli-surface`: Add deterministic local operator commands (`init`, `adopt`, `status`, `read`) plus explicit error boundaries for unapplied bootstrap/adoption state.

## Approach

Extract reusable file-backed bootstrap from demo/test assembly into a first-class runtime path, then place a thin CLI over it. Trust boundary: the local node remains the only canonical writer for the adopted project; any shared MCP/coordinator integration stays optional and non-authoritative. Compatibility boundary: preserve current runtime modules and demo flow while adding an additive bootstrap path.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `runtime/node/store/__init__.py` | Modified | Persistent bootstrap/open helpers |
| `runtime/node/mcp/__init__.py` | Modified | Read/status surface wiring |
| `scripts/demo_v1_runtime.py` | Modified | Reuse shared bootstrap instead of custom setup |
| `README.md` | Modified | Document supported bootstrap/adopt flow |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Scope expands into coordinator/LAN UX | Med | Freeze V1.1 to local-owner commands only |
| Implicit repo adoption blurs trust/intent | Med | Require explicit `adopt` and clear status errors |
| Bootstrap drifts from existing demo/tests | Low | Reuse proven file-backed setup and keep demo as compatibility check |

## Rollback Plan

Remove the new CLI/bootstrap entrypoint, keep existing demo/test assembly as the supported fallback, and leave local adopted node homes as disposable additive data. Avoid destructive schema changes so reverting code does not require repository migration.

## Dependencies

- Existing runtime modules, SQLite schemas, and current entrypoint/read contracts.

## Success Criteria

- [ ] A local operator can run `init`, `adopt`, `status`, and `read` against this repo without coordinator setup.
- [ ] Bootstrap is explicit, local-first, and preserves current demo/test behavior if the new path is reverted.
