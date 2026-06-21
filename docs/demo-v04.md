# CapiForge MVP v0.4 — 5-minute demo script

Use after `./capinstall install --cursor --non-interactive` on a fresh clone.

## 1. Install and verify (1 min)

```bash
./capinstall install --cursor --non-interactive
./capinstall verify --json
capiforge --version    # expect 0.4.0
capiforge status       # bootstrap_state: adopted
```

## 2. Multi-project hub (2 min)

```bash
capiforge web
```

In the browser:

1. Confirm **Primeros pasos** onboarding block on home.
2. Use **+ Añadir proyecto** to adopt a second folder (any git repo or empty adopted folder).
3. Use the **Proyecto** selector in the page header — switch between hub and the extra project.
4. Confirm home, tasks, and docs update for each project without losing the current route.

## 3. Docs indexer (1 min)

```bash
python3 scripts/index_local_docs.py
capiforge web
```

1. Open **Documentación** for the hub project.
2. Confirm repo files under `docs/` appear in the local documents list.
3. Open `docs/demo-v04.md` (this file) in the viewer.

## 4. Tasks and audits (30 sec)

1. Open **Tareas** — review queue counts for the active project.
2. Open **Documentación** — select **CapiForge v0.4 — Expanded hub roadmap** audit.
3. Confirm linked tasks appear under the audit.

## 5. Agent contract (30 sec)

Show `.cursor/skills/capiforge-publish-milestone/SKILL.md` — agents publish at milestones only; Engram for session memory; web hub for human review.
