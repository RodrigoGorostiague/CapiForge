# MVP v0.3 — Baseline verification (2026-06-21)

Manual pass/fail against [mvp-v03.md](mvp-v03.md) operator checklist.

| Check | Result | Notes |
|-------|--------|-------|
| `./capinstall install --cursor --opencode` | pass | Prior install; `verify` OK |
| `./capinstall verify --json` → `ok: true` | pass | No issues |
| `capiforge status` → `adopted` | pass | Owner-local node |
| Cursor MCP → `capiforge mcp serve` | pass | `current_get` OK post-restart |
| `.cursor/skills/capiforge-publish-milestone` | pass | Present |
| `capiforge web` hub (purpose, architecture, tasks, audits) | pass | `project_pages` seeded |
| Human edit project pages | pass | `/project-page` save API |
| `capiforge --version` | pass | `0.3.0` after `capinstall update` |
| Full unittest suite | pass | 264 tests OK (43 skipped) |

## Product criteria

| # | Criterion | Result |
|---|-----------|--------|
| P1 | Web hub | pass |
| P2 | `project_pages` edit | pass |
| P3 | milestone skill via capinstall | pass |
| P4 | MCP v0.2 regression | pass |

## Release criteria

| # | Criterion | Result |
|---|-----------|--------|
| R1 | unittest green | pass |
| R2 | capinstall verify | pass |
| R3 | README quick start | pass |
| R4 | git tag `v0.3.0` | pass |

## Deferred

- `audit/future/*`
- Optional: `mcp-milestone-batch`, `ui-local-docs-viewer`
