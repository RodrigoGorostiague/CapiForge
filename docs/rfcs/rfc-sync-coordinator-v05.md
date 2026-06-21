# RFC: LAN sync coordinator activation (v0.5)

**Status:** draft  
**Supersedes:** `audit/future/sync-coordinator`  
**Lifecycle key:** `audit/v0.4/rfc-sync-coordinator`

## Problem

CapiForge v0.4 runs as a **local hub** with coordinator code present but frozen. v0.5 needs **same-owner, multi-machine** sync without breaking the hybrid truth model (SQLite authoritative per node, long-form docs local-only).

## Goals

- Activate coordinator LAN sync for task/audit metadata between nodes owned by the same human.
- Preserve `local_documents` as local-only (no blob sync).
- Deterministic conflict resolution with explicit authority rules.

## Non-goals

- Multi-user workspaces (v0.6).
- Cross-owner federation.
- Real-time BI dashboards (v1.0).

## Authority model

| Data | Authority | Sync direction |
| --- | --- | --- |
| Tasks, claims, audits | Owner node that created mutation | Last-writer with mutation log |
| `project_pages` | Hub node for adopted repo | Pull from hub on secondary nodes |
| `local_documents` | Local only | Never sync payload |
| Coordinator routes | Coordinator node | Push pending routes to peers |

**Rule:** a secondary machine never overrides hub bootstrap state; it registers as a peer and pulls project metadata.

## Delta sync

1. Export `task_mutations` + audit headers since `last_sync_cursor`.
2. Exclude `local_documents` and full audit bodies > N KB from LAN export (metadata + refs only).
3. Import applies mutations in `mutation_id` order; reject if project_id unknown.
4. Coordinator marks routes `acked` after peer applies batch.

Existing hook: `NodeStore.export_sync_payload()` — extend with cursor and size limits.

## Activation checklist (v0.5 derived tasks)

| Task | Deliverable |
| --- | --- |
| `audit/v0.5/sync-authority-spec` | Written authority matrix + failure modes |
| `audit/v0.5/sync-delta-export` | Cursor-based export/import in node store |
| `audit/v0.5/coordinator-unfreeze` | Enable coordinator in non-test runtime |
| `audit/v0.5/e2e-multi-node` | Green `tests/e2e/multi_node_runtime_test.py` in CI |

## Test plan

- Reuse `tests/e2e/multi_node_runtime_test.py`.
- Add regression: sync never includes `local_documents` rows.
- Add regression: expired claim on node A visible on node B after sync.

## Rollback

Keep coordinator behind `CAPIFORGE_SYNC=0` default until e2e gate passes; hub-only mode remains v0.4 baseline.
