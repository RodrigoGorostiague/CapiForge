# RFC: Admin dashboards and cross-project BI (v1.0)

**Status:** draft  
**Supersedes:** `audit/future/admin-dashboards`  
**Lifecycle key:** `audit/v0.4/rfc-admin-dashboards`

## Problem

Operators need **cross-project visibility** (queue health, audit throughput, stale claims) without reading each project hub separately. v0.4 delivers per-project views only.

## Goals

- Read-only admin dashboard aggregating metrics from hub SQLite.
- Export-friendly summaries (JSON/CSV) for external BI.
- No new write path — dashboards consume existing store queries.

## Non-goals

- Embedded analytics warehouse.
- Semantic search / embeddings.
- Notion-style block editor.

## Data sources

| Metric | Source | Notes |
| --- | --- | --- |
| Tasks by state | `tasks` grouped by `project_id`, `state` | Per workspace rollup |
| Ready queue age | `tasks.ready` + `task_mutations` timestamps | SLA-style staleness |
| Audit publish rate | `audits` where `state=published` | Weekly bucket |
| Expired claims | `claims_local_cache` + lease window | Ops alert |
| Sync degraded | Coordinator route pending count | When sync enabled |

All queries owner-local; no PII beyond node/agent ids already in SQLite.

## UI sketch (v1.0)

- Route `/admin` on hub (owner-only gate).
- Cards: total ready, in_progress, blocked, done (7d).
- Table: projects with counts + last audit title.
- Link through to existing project switcher.

## v1.0 derived tasks

| Task | Deliverable |
| --- | --- |
| `audit/v1.0/admin-query-layer` | Store helpers for rollup metrics |
| `audit/v1.0/admin-web-dashboard` | `/admin` page + tests |
| `audit/v1.0/admin-export` | CLI `capiforge admin export --json` |

## Privacy

Dashboards never expose `local_documents` contents — only counts and paths if needed for ops.

## Rollback

Feature flag `CAPIFORGE_ADMIN=0`; hub continues with per-project pages only.
