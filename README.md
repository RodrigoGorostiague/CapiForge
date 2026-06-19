# CapiForge Runtime Bootstrap

<p align="center">
  <img src="assets/capiforge-icons/capiforge_logo_original_transparente.png" alt="CapiForge logo" width="220">
</p>

> Product / project name: **CapiForge**

## Brand Assets

- `assets/capiforge-icons/capiforge_logo_original_transparente.png` is the default README/GitHub branding asset for light surfaces.
- `assets/capiforge-icons/capiforge_logo_invertido_transparente.png` is preserved for dark-background Git and project-branding uses.
- `assets/capiforge-icons/capiforge-ascii.txt` is kept in-project for future TUI/app graphics so the terminal presentation can reuse the same brand set later.

## Module Layout

- `storage/` contains the owner-node and coordinator SQLite schemas used to bootstrap local-first state.
- `runtime/shared/` holds canonical IDs, mutation contracts, and surface error payloads shared by nodes and the coordinator.
- `runtime/node/` contains local node persistence, deterministic entrypoint indexes, owner routing, and node MCP handlers.
- `runtime/coordinator/` contains LAN enrollment, exclusive claim leases, routed mutation visibility, and coordinator MCP handlers.
- `tests/e2e/` covers the review-facing multi-node topology: two nodes plus one thin coordinator.

## Bootstrap Defaults

V1 keeps the coordinator thin and non-authoritative. Each project has exactly one owner node for canonical domain writes. Non-owner nodes may read synced metadata, request claims, and submit routed proposals that require explicit owner acceptance.

Shared read/sync surfaces are intended for trusted enrolled nodes only. Runtime calls now require a session-bound `node_proof` derived from the invitation fingerprint plus `node_id`, `agent_id`, and `session_id`, instead of treating a reusable shared string or raw `node_id` as sufficient authority.

Project-scoped authorization is now enforced before local entrypoint reads, indexed task reads, claims, and routed mutation proposal creation. Enrollment alone is not enough to inspect or act on arbitrary project IDs.

Coordinator-backed project reads remain minimal in V1: the owner node, a node with coordinator claim history for that project, or a node already participating in a routed mutation for that destination project may read shared sync metadata. Node-local mirrored reads add one more narrow allowance: a trusted node may traverse a foreign project only when it owns a project that is already explicitly linked to that foreign project in local metadata. Claiming a task does not create that access retroactively.

Claimed execution remains valid only while the coordinator lease is active. Releasing or expiring a lease returns the task to a non-active state until a new valid claim exists.

Suggested lease defaults for bootstrap environments:

- Lease duration: 5 minutes
- Renewal cadence: every 2 minutes
- Clock-skew grace window: 30 seconds

These defaults come from the current V1 design and are intended to keep claim recovery predictable without making the coordinator authoritative.

## Local-Only Document Boundary

Long-form documents stay local-only in node storage. V1 sync shares structured metadata, artifact references, owner-node routing metadata, claim visibility, and canonical summaries only. If a human wants to share long-form content, that export must happen through a separate explicit mechanism outside the coordinator's default sync path.

Approved cross-project routes remain non-authoritative until the destination owner node applies them locally. Acceptance records the route decision; canonical task materialization still happens on the owner node. Sync announcements are accepted only from the enrolled reporting node itself and only for projects that node is already authorized to coordinate on.

Cross-project routing now requires coordinator-held notice/approval state for the exact source/destination pair and current destination owner. Local requester cache is not sufficient on its own, and a revoked approval blocks later owner acceptance.

Direct audit content edits are owner-local human-control actions only. AI actors and non-owner nodes must use follow-up/addendum flows instead, and closed audits still reject direct rewrites.

## Test Runner

The repository includes a stdlib `unittest` entrypoint shim at the repo root, so a naive default invocation discovers the full suite instead of silently running zero tests.

```bash
python3 -m unittest
```

Default retention keeps synced metadata and artifact references available until a human removes them or newer evidence supersedes them. Automatic expiry applies only to claim leases.
