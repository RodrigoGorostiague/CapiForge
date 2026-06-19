# Tasks: Shared Local-First MCP Knowledge Layer

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 1,500-2,200 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 → PR 4 |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Bootstrap schemas, IDs, authority guards | PR 1 | Base: main; include schema tests |
| 2 | Build node runtime and entrypoint indexes | PR 2 | Depends on PR 1; include traversal tests |
| 3 | Add coordinator enrollment, claims, routed proposals | PR 3 | Depends on PR 2; include multi-node tests |
| 4 | Expose MCP/CLI surface and approval flows | PR 4 | Depends on PR 3; include end-to-end scenarios |

## Phase 1: Foundation / Security Boundaries

- [x] 1.1 Create `storage/node-schema.sql` for workspace/project/task/audit/link/index tables and owner-aware constraints.
- [x] 1.2 Create `storage/coordinator-schema.sql` for `nodes`, `project_owners`, `claim_leases`, `mutation_routes`, `sync_announcements`, and approvals metadata.
- [x] 1.3 Add `runtime/shared/ids.*` and `runtime/shared/contracts.*` for canonical IDs, actor identity, justification payloads, and owner-write validation.
- [x] 1.4 Add schema/contract tests in `tests/storage/schema_*` and `tests/contracts/authority_*` for immutability, task states, and non-owner rejection.

## Phase 2: Local Node Runtime / Deterministic Traversal

- [x] 2.1 Create `runtime/node/store/*` to persist audits, tasks, task mutations, artifact refs, local documents, and human-approved project links.
- [x] 2.2 Create `runtime/node/index/*` to build `project_entrypoints` plus ready/blocked/done/critical/expired-claim materialized indexes.
- [x] 2.3 Create `runtime/node/router/*` to resolve `owner_node_id`, accept owner writes, and emit routed proposals from non-owner nodes.
- [x] 2.4 Add node integration tests in `tests/node/entrypoint_*` for deterministic traversal, cross-project guards, and offline owner reads.

## Phase 3: Coordinator / Claims / Routed Mutations

- [x] 3.1 Create `runtime/coordinator/enrollment/*` for per-node signed invitation enrollment and owner assignment visibility.
- [x] 3.2 Create `runtime/coordinator/claims/*` for exclusive leases, renew/release/expire handling, and stale-claim visibility.
- [x] 3.3 Create `runtime/coordinator/routes/*` for proposal intake, system validation, owner accept/reject decisions, and sync summaries.
- [x] 3.4 Add coordinator integration tests in `tests/coordinator/*` for claim collision, expiry recovery, routed mutation acceptance, and outage degradation.

## Phase 4: MCP / CLI Surface

- [x] 4.1 Create `contracts/mcp-surface.md` and `runtime/shared/errors.*` for deterministic read/mutate/override commands and explicit failures.
- [x] 4.2 Create `runtime/node/mcp/*` and `runtime/coordinator/mcp/*` for `workspace.get`, `project.entrypoint.get`, `tasks.list_by_index`, `tasks.claim`, `tasks.transition`, `cross_project.request`, and `sync.status`.
- [x] 4.3 Add surface tests in `tests/mcp_cli/*` covering justification-required mutations, closed-audit protection, and routed cross-project approval flow.

## Phase 5: End-to-End Verification / Bootstrap Docs

- [x] 5.1 Add multi-process scenarios in `tests/e2e/*` for two nodes plus one coordinator covering traversal, claim exclusivity, and owner-routed writes.
- [x] 5.2 Add bootstrap notes in `README.md` or `docs/runtime-bootstrap.md` for module layout, lease timing defaults, and local-only document boundaries.
