# CapiForge MVP v0.4 — Expanded hub acceptance checklist

Use this checklist to confirm the **expanded local hub** MVP is ready: multi-project navigation, onboarding, docs indexer, and platform RFCs.

> v0.3 remains complete. See [mvp-v03.md](mvp-v03.md) and [mvp-v03-baseline.md](mvp-v03-baseline.md).

## Operator checklist (human)

- [ ] `./capinstall install --cursor --opencode` completes without errors
- [ ] `./capinstall verify --json` reports `ok: true`
- [ ] `capiforge status` shows `bootstrap_state: adopted`
- [ ] `capiforge web` shows project switcher with 2+ adopted projects
- [ ] Switching projects updates home, tasks, and docs for the selected project
- [ ] Onboarding section visible on home (install, skills, milestone contract)
- [ ] `scripts/index_local_docs.py` indexes `docs/` into Documentación
- [ ] Platform RFCs exist under `docs/rfcs/`
- [ ] `audit/future/*` tasks cancelled; v0.4 RFC tasks seeded

## Product criteria

| # | Criterion | Target |
|---|-----------|--------|
| P1 | Multi-project web navigation | 2+ projects switchable |
| P2 | Onboarding from hub | No README required for first steps |
| P3 | Docs indexer + viewer | `docs/` visible in Documentación |
| P4 | Platform RFCs + future superseded | 3 RFCs; no stale `audit/future/*` ready |

## Release criteria

| # | Criterion | Target |
|---|-----------|--------|
| R1 | unittest green | Full suite pass |
| R2 | capinstall verify | ok: true |
| R3 | (Optional) git tag | `v0.4.0` |

## Agent minimum path (unchanged from v0.3)

Agents publish at milestones only. See [skills/capiforge-publish-milestone/SKILL.md](../skills/capiforge-publish-milestone/SKILL.md).

Preferred: `milestone_publish` (1 MCP call) for audit + optional lifecycle close.

## References

- [audit-v04-expanded-hub.md](audits/audit-v04-expanded-hub.md)
- [architecture-v01.md](architecture-v01.md)
- [demo-v04.md](demo-v04.md)
