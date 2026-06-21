# CapiForge MVP v0.3 — 5-minute demo script

Use after `./capinstall install --cursor --non-interactive` on a fresh clone.

## 1. Install and verify (1 min)

```bash
./capinstall install --cursor --non-interactive
./capinstall verify --json
capiforge --version    # expect 0.3.0
capiforge status       # bootstrap_state: adopted
```

## 2. Project hub (2 min)

```bash
capiforge web
```

In the browser:

1. Confirm **Propósito** and **Arquitectura** sections on home.
2. Click **Editar propósito** → change one line → **Guardar**.
3. Return to home; confirm the edit appears.

## 3. Tasks and documentation (1 min)

1. Open **Tareas** — review queue counts and task table.
2. Open **Documentación** — select **CapiForge v0.3 — MVP closure and release** audit.
3. Confirm linked tasks appear under the audit.

## 4. Realtime (optional, post-SSE tasks)

1. With `capiforge web` open, in another terminal run a task transition or page save.
2. Confirm the UI updates without manual full-page refresh (SSE path).

## 5. Agent contract (30 sec)

Show `.cursor/skills/capiforge-publish-milestone/SKILL.md` — agents publish at milestones only; Engram for session memory.
