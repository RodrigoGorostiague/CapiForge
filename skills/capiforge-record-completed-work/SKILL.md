---
name: capiforge-record-completed-work
description: "Record completed same-project work through the public audit and lifecycle surface."
license: Apache-2.0
metadata:
  author: "rodaja"
  version: "1.0"
---

# Skill: capiforge-record-completed-work

Use this skill when an installed OpenCode session needs to record completed owner-local work for the adopted CapiForge project.

## Contract

- Keep all technical artifacts in English.
- Use only public product-facing CapiForge operations.
- Stay owner-local and same-project only.
- Never seed audits or tasks through direct database writes.
- Never call `tasks_reconcile_finish` without explicit outcome metadata.

## Required Sequence

1. Create a brief audit through `audit_create_brief` with non-empty `title` and `content`.
2. Publish that audit through `audit_publish`.
3. Start or create the lifecycle task through `tasks_reconcile_start`, passing the published `audit_id` as `origin_audit_id` when a reusable task does not already exist.
4. Finish through `tasks_reconcile_finish` only after collecting explicit `done` or `blocked` metadata.

## Failure Handling

- If audit create or publish fails, stop and return the surfaced validation or authority error.
- If lifecycle start fails, stop and do not attempt finish.
- If finish metadata is incomplete or the claim is no longer valid, stop and ask for a retry with explicit closure data.

## References

- `contracts/mcp-surface.md`
- `skills/capiforge-start-task/SKILL.md`
- `skills/capiforge-close-task/SKILL.md`
