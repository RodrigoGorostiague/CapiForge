# MVP v0.4 — Baseline verification (2026-06-21)

Manual pass/fail against [mvp-v04.md](mvp-v04.md) operator checklist.

| Check | Result | Notes |
|-------|--------|-------|
| `./capinstall install --cursor --opencode` | pass | Prior install; `verify` OK |
| `./capinstall verify --json` → `ok: true` | pass | No issues |
| `capiforge status` → `adopted` | pass | Owner-local node |
| `capiforge web` project switcher (2+ projects) | pass | Registry + page header switcher |
| Switching projects updates home/tasks/docs | pass | Context preserved per route |
| Onboarding section on home | pass | Primeros pasos block |
| `scripts/index_local_docs.py` | pass | Indexes `docs/` into Documentación |
| Platform RFCs under `docs/rfcs/` | pass | sync v0.5, multi-user v0.6, BI v1.0 |
| `audit/future/*` cancelled | pass | `scripts/supersede_audit_future_tasks.py` |
| Product TUI removed; web is human surface | pass | `runtime/hub/` shared snapshots |

## Product criteria

| # | Criterion | Result |
|---|-----------|--------|
| P1 | Multi-project web navigation | pass |
| P2 | Onboarding from hub | pass |
| P3 | Docs indexer + viewer | pass |
| P4 | Platform RFCs + future superseded | pass |

## Release criteria

| # | Criterion | Result |
|---|-----------|--------|
| R1 | unittest green (189 tests) | pass | Requires `runtime/node/current.py` claim-expiry commit |
| R2 | capinstall verify | pass |
| R3 | git tag `v0.4.0` | pending | Tag after release fix is committed |

## Evidence

```bash
.venv/bin/python3 -m unittest discover -s tests -p '*_test.py'  # 189 OK (outside sandbox)
./capinstall verify --json                                       # ok: true
```
