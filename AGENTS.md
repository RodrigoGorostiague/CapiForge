# Project Agent Notes

## Project Skills

- `skills/capiforge-pickup-task/SKILL.md` — Load when an orchestrator needs to inspect CapiForge state, choose a ready task, claim it through the product-facing MCP tools, and return a concise operational summary.
- `skills/capiforge-start-task/SKILL.md` — Load when an orchestrator already has a claimed task and needs to validate the live claim, move that task to `in_progress`, and return a concise operational summary.
- `skills/capiforge-close-task/SKILL.md` — Load when an orchestrator has finished work on a claimed task and needs to validate live claim/task context, transition it to a terminal state, and return a concise operational summary.
