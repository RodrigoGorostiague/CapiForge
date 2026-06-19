# Design: Real Node Bootstrap and Minimal CLI

## Technical Approach

Build a repo-local bootstrap layer that persists one owner node home under this repository, then expose a tiny script CLI for `init`, `adopt`, `status`, and `read`. V1.1 stays local-first: no coordinator DB, no enrollment, no LAN automation, and no broad mutation commands. `read` reuses the existing deterministic entrypoint/index logic; `init` and `adopt` only assemble enough durable state to make that read path real.

## Architecture Decisions

### Decision: Persist bootstrap state outside domain tables

| Option | Tradeoff | Decision |
|---|---|---|
| Reuse `projects`/`workspaces` only | Cannot represent `uninitialized` vs `initialized`, local node identity, or adoption intent cleanly | Rejected |
| Add bootstrap metadata to node DB | Couples V1.1 operator state to domain schema | Rejected for this slice |
| Keep a small repo-local bootstrap manifest beside the SQLite DB | Explicit state machine, easy idempotency, no schema migration | Chosen |

**Rationale**: The existing schema models project domain data, not operator bootstrap lifecycle. A sidecar manifest is the smallest credible way to persist identity, state, and adoption metadata without altering stable domain tables.

### Decision: Repo-local owner trust, not enrolled-actor trust

| Option | Tradeoff | Decision |
|---|---|---|
| Require coordinator enrollment for CLI reads | Violates local-owner scope and expands setup | Rejected |
| Use local filesystem possession of the node home as the trust boundary | Limited to owner-local use, matches scope | Chosen |

**Rationale**: This change is explicitly owner-local. The CLI may create a synthetic local actor only to traverse the existing node MCP read surface against the adopted project. That actor is valid for local reads only and MUST NOT unlock coordinator-backed flows.

### Decision: JSON-only deterministic CLI responses

| Option | Tradeoff | Decision |
|---|---|---|
| Human-formatted text | Harder to test and compose | Rejected |
| JSON with existing surface envelope | Consistent with current contracts and tests | Chosen |

**Rationale**: All commands will print one JSON object using `{status,data,error}`. `init`/`adopt` return `accepted`; `status`/`read` return `ok`; failures return `error` with `INVALID_BOOTSTRAP_STATE`, `TRUST_BOUNDARY_VIOLATION`, or existing shared errors.

## Data Flow

`init`

    capiforge_cli -> NodeBootstrap.open_or_init()
                  -> .capiforge/node/node.sqlite3
                  -> .capiforge/node/bootstrap.json (state=initialized)

`adopt`

    capiforge_cli -> NodeBootstrap.adopt_repo(repo_root)
                  -> NodeStore.create_workspace/upsert_project()
                  -> bootstrap.json (state=adopted)

`read`

    capiforge_cli -> NodeBootstrap.require_adopted()
                  -> NodeMCPSurface.project_entrypoint_get(local actor)
                  -> NodeIndexBuilder / NodeStore

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `runtime/node/bootstrap/__init__.py` | Create | Repo-local bootstrap manifest, state machine, adoption guardrails, and local CLI runtime assembly. |
| `scripts/capiforge_cli.py` | Create | Minimal JSON CLI entrypoint for `init`, `adopt`, `status`, and `read`. |
| `runtime/node/store/__init__.py` | Modify | Add persistent SQLite open/create helper reused by CLI and demo. |
| `runtime/node/mcp/__init__.py` | Modify | Add a tiny local-read helper or normalization needed to reuse the read surface without coordinator enrollment. |
| `scripts/demo_v1_runtime.py` | Modify | Reuse the shared persistent connection/bootstrap helper instead of custom schema setup. |
| `README.md` | Modify | Document the supported owner-local bootstrap flow and non-goals. |
| `tests/node/bootstrap_cli_test.py` | Create | State-machine and persistence tests for init/adopt/status/read. |

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class BootstrapState:
    state: Literal["uninitialized", "initialized", "adopted"]
    local_node_id: str
    node_home: str
    node_db_path: str
    adopted_project: dict | None
```

`status` returns persisted bootstrap metadata. `read` returns:

```json
{"status":"ok","data":{"bootstrap_state":"adopted","project":{...},"entrypoint":{...}}}
```

`adopt` only accepts this repo root, is idempotent for the same repo, and rejects replacing an already adopted different project.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Manifest state transitions and repo-boundary validation | New `unittest` cases for init/adopt idempotency and invalid transitions. |
| Integration | Persistent reopen, seeded project rows, deterministic status/read JSON | Temp-directory tests against the real SQLite schema and CLI main function. |
| E2E | Demo compatibility | Keep `python3 -m unittest`; update demo path to prove shared bootstrap still works. |

## Migration / Rollout

No migration required. The CLI writes additive repo-local state under `.capiforge/node/`; deleting that directory cleanly rolls back local bootstrap data.

## Open Questions

- [ ] None.
