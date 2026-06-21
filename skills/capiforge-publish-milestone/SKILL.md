---
name: capiforge-publish-milestone
description: "Trigger: publish milestone, audit complete, feature shipped, architecture update. When agents should write to CapiForge at milestones only — not per micro-task."
license: Apache-2.0
metadata:
  author: "rodaja"
  version: "1.0"
---

# Skill: capiforge-publish-milestone

Use this skill as the **default** CapiForge contract for agents. Most work does **not** require MCP calls.

## When to publish (milestones)

| Milestone | Publish? | Action |
| --- | --- | --- |
| Audit or review completed | Yes | `milestone_publish` or `audit_create_brief` → `audit_publish` |
| Significant feature or change closed | Yes | `milestone_publish` with `lifecycle`, or `tasks_reconcile_start` → `tasks_reconcile_finish` with `done_*` metadata |
| Architecture or purpose changed | Yes | `project_page_upsert` + audit addendum, or human updates via `capiforge web` |
| Micro-task, bugfix, exploration, refactor | **No** | Engram, git, OpenSpec only |
| Session notes, decisions, conventions | **No** | Engram (`mem_save`, etc.) |
| Spec / change proposal | **No** | `openspec/` in repo |

## Hard rules

- Keep all technical artifacts in English.
- Do **not** run pickup → start → close unless the orchestrator explicitly assigned a ready-queue task.
- Typical milestone: **1 MCP call** with `milestone_publish`, or **≤ 3 MCP calls** with the split audit/reconcile sequence.
- Never duplicate Engram session memory or OpenSpec content inside CapiForge audits.
- Never write SQL directly; use public MCP tools only.

## Audit milestone sequence

Preferred (one call):

1. `milestone_publish` with `title`, `content`, and optional `lifecycle` block to close tracked work.

Split sequence (still supported):

1. `audit_create_brief` with non-empty `title` and markdown `content`.
2. `audit_publish` with the returned `audit_id`.
3. Optionally `tasks_reconcile_start` / `tasks_reconcile_finish` if the milestone closes tracked work.

## Feature-close milestone sequence

1. Ensure a published `origin_audit_id` exists (create audit first if needed).
2. `tasks_reconcile_start` with stable `lifecycle_key` and seed fields on miss.
3. `tasks_reconcile_finish` with explicit `done` or `blocked` metadata.

## Content format (audits)

Use markdown with:

- **Summary** — one paragraph outcome
- **Scope** — what changed
- **Evidence** — paths, test commands, audit IDs
- **Follow-ups** — optional next milestones

## Hybrid truth model

| Source | Owns |
| --- | --- |
| CapiForge | Purpose, architecture, audits, tasks |
| Engram | Agent memory across sessions |
| OpenSpec | Specs and change proposals |
| Repo `docs/` | Long-form technical docs (indexed, not canonical in CF) |

## References

- `docs/mvp-v03.md`
- `docs/audits/audit-v03-scope-pivot.md`
- `skills/capiforge-data-layer/SKILL.md`
- `skills/capiforge-record-completed-work/SKILL.md`
