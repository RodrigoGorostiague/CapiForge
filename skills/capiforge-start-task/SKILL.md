---
name: capiforge-start-task
description: "Trigger: start claimed task, move task to in_progress, begin active work. Validate claimed-task context, require a live claim, transition to in_progress, and summarize the result."
license: Apache-2.0
metadata:
  author: "rodaja"
  version: "1.0"
---

# Skill: capiforge-start-task

## Activation Contract

Use when a CapiForge task was already selected and claimed, and the orchestrator needs to move that exact task into active execution without exposing raw MCP claim protocol details to the end user.

## Hard Rules

- Keep all technical artifacts, comments, identifiers, and summaries in English.
- Prefer product-facing reads first: `current_get` when available; otherwise use `workspace_get_current`, `project_entrypoint_get`, `tasks_list_by_index`, and `sync_status`.
- Resolve the target task only from explicit caller input or prior claimed-task context. If neither exists, stop and recommend `capiforge-pickup-task`.
- Never start a task without a valid active claim. Treat `tasks.transition` / `tasks_transition` as the final authority for claim validity.
- Validate project, task, claim, and lease context before attempting the state change.
- Task lifecycle reminder: `pickup -> start -> progress/close`.

## Decision Gates

| Situation | Action |
| --- | --- |
| No target `task_id` and no prior claimed-task context | Return `status: missing_target`; recommend pickup first. |
| Claim context is missing `claim_id`, `task_id`, or `lease_expires_at` | Return `status: missing_claim_context`; do not transition. |
| Claim lease is expired, mismatched to the target task/project, or otherwise stale | Return `status: claim_invalid`; require re-pickup or re-claim. |
| Task already shows `in_progress` | Return `status: already_started` with the existing claim context. |
| Transition rejects the claim or state | Return the surfaced conflict and say re-pickup/re-claim is required. |

## Execution Steps

1. Read current project state first with `current_get` or the higher-level workspace/project/sync tools.
2. Resolve the target from explicit `task_id` input; otherwise reuse prior claimed-task context from the immediately preceding pickup result or orchestrator memory.
3. Verify the adopted project matches the claimed-task context and that the lease expiry is still in the future.
4. Confirm the task is the intended work item and not an unrelated ready task; do not silently switch targets.
5. If available state already shows `in_progress`, return an idempotent summary and stop.
6. Call `tasks.transition` / `tasks_transition` with `requested_state: in_progress`, real justification metadata, and the active claim session context required by the runtime.
7. If the transition is accepted, report the task as started. If the runtime rejects because the claim is stale or missing, stop and instruct the orchestrator to re-run pickup/claim.

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
- `skills/capiforge-pickup-task/SKILL.md`
