---
name: capiforge-close-task
description: "Trigger: close finished task, complete task lifecycle, mark task done, finish claimed work. Validate live claim/task context, transition the task to its terminal state, and summarize the result."
license: Apache-2.0
metadata:
  author: "rodaja"
  version: "1.0"
---

# Skill: capiforge-close-task

## Activation Contract

Use when a CapiForge task was already picked up and started, implementation is finished, and the orchestrator needs to complete the lifecycle without exposing raw MCP protocol details to the end user.

## Hard Rules

- Keep all technical artifacts, comments, identifiers, and summaries in English.
- Prefer higher-level product-facing reads first: `current_get` when available; otherwise use `workspace_get_current`, `project_entrypoint_get`, `tasks_list_by_index`, and `sync_status`.
- Resolve the target task only from explicit caller input or prior claimed/in-progress context. If neither exists, stop and recommend `capiforge-pickup-task` or `capiforge-start-task`.
- Never close a task without validating project, task, claim, and lease context first.
- Default the terminal state to `done` unless explicit repo workflow for this task requires another terminal state.
- Treat `tasks.transition` / `tasks_transition` as the final authority when no higher-level close wrapper exists.
- Task lifecycle reminder: `pickup -> start -> close`.

## Decision Gates

| Situation | Action |
| --- | --- |
| No target `task_id` and no prior active-task context | Return `status: missing_target`; recommend pickup/start first. |
| Claim context is missing `claim_id`, `task_id`, or `lease_expires_at` | Return `status: missing_claim_context`; do not transition. |
| Claim lease is expired, mismatched to the target task/project, or otherwise stale | Return `status: claim_invalid`; require re-pickup/re-claim or human review. |
| Task already shows `done` or another terminal state | Return `status: already_closed` with the current terminal state and claim context. |
| Transition rejects the claim or state | Return the surfaced conflict and say re-pickup/re-claim or human review is required. |

## Execution Steps

1. Read current project state first with `current_get` or the higher-level workspace/project/sync tools.
2. Resolve the target from explicit `task_id` input; otherwise reuse prior claimed-task context from the immediately preceding start result or orchestrator memory.
3. Verify the adopted project matches the active claim context and that `lease_expires_at` is still in the future.
4. Confirm the target is the intended task; do not silently switch to a different claimed, ready, or done task.
5. If visible state already shows a terminal state, return an idempotent summary and stop.
6. Prepare close metadata that satisfies repo conventions for `done`: justification plus result, affected artifacts, linked references, and expected impact.
7. If a higher-level close wrapper exists, use it. Otherwise call `tasks.transition` / `tasks_transition` with `requested_state: done`, the active claim session context, and the close metadata.
8. Report the accepted terminal transition, or surface the authoritative rejection without retry loops.

## Output Contract

Return a concise operational summary with:

- `status`
- `task_id`
- `previous_state`
- `new_state`
- `claim_id`
- `lease_expires_at`
- `next_action`

## References

- `README.md`
- `contracts/mcp-surface.md`
- `openspec/specs/task-audit-model/spec.md`
- `skills/capiforge-pickup-task/SKILL.md`
- `skills/capiforge-start-task/SKILL.md`
