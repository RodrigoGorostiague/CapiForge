---
name: capiforge-pickup-task
description: "Trigger: pick up task, claim ready task, choose next task, current project state. Inspect CapiForge state, select a ready task, claim it, and summarize the result."
license: Apache-2.0
metadata:
  author: "rodaja"
  version: "1.0"
---

# Skill: capiforge-pickup-task

## Activation Contract

Use **only** when an orchestrator explicitly assigns work from the CapiForge ready queue. For normal agent work, use `capiforge-publish-milestone` at milestones instead — do not claim tasks per micro-task.

## Hard Rules

- Keep all technical artifacts, comments, identifiers, and summaries in English.
- Prefer only the product-facing MCP tools: `current_get`, `tasks_ready_get`, `tasks_claim`, and `tasks_claim_renew` when extending a long session.
- Read current state before claiming. Never claim blindly.
- Use a bounded ready-task read and the default 5-minute lease unless the caller provides another lease.
- Do not silently claim a different task after a failed claim unless the caller explicitly allowed fallback.

## Decision Gates

| Situation | Action |
| --- | --- |
| No ready tasks | Return `status: no_ready_tasks` with current project context, queue counts, and **next steps** (see below). Do not claim blindly. |
| Exactly one ready task | Claim it unless the caller asked for inspection only. |
| Multiple ready tasks with explicit `task_id` or policy | Apply that selection rule exactly. |
| Multiple ready tasks with no policy | Use the deterministic default policy: select the first task in `tasks_ready_get.data.tasks` order and say so in the summary. |
| Claim fails because the task is no longer ready or available | Refresh once with `tasks_ready_get`; report the stale selection or conflict; retry only when explicit fallback was authorized. |

## Execution Steps

1. Call `current_get` first to capture bootstrap state, adopted project context, and the current ready-task signal.
2. If the current payload already shows no ready tasks, stop and return a concise operational summary with `status: no_ready_tasks` and these **next steps**:
   - Check `entrypoint.queue_counts` and `tasks_list_by_index` for `blocked`, `done`, or `expired_claim`.
   - If all work is `in_progress` or `claimed`, wait or ask the operator to finish/release tasks.
   - To create new work: publish an audit (`audit_create_brief` → `audit_publish`) and seed or reconcile tasks with `tasks_reconcile_start` and a stable `lifecycle_key`.
   - Point the operator to `docs/mvp.md` for the full empty-queue playbook.
3. Call `tasks_ready_get` with a bounded limit and inspect the returned queue.
4. Resolve task selection in this order: explicit `task_id`, explicit caller policy, default first-in-queue policy.
5. Build a one-sentence claim plan from the selected task's visible title or summary. Keep it specific and operational.
6. Call `tasks_claim` with `task_id`, `plan`, and optional `lease_minutes`.
7. If the claim fails with an availability/state conflict, call `tasks_ready_get` once more and return the refreshed facts instead of looping.

## Output Contract

Return a concise operational summary with:

- `status`
- `selection_policy`
- `selected_task`
- `claim_result`
- `ready_queue_snapshot`
- `next_action`

## References

- `docs/mvp.md`
- `README.md`
- `contracts/mcp-surface.md`
