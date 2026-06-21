#!/usr/bin/env python3
"""Seed demo web UI tasks linked to published audits in the adopted repo."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import uuid4

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore
from runtime.paths import default_repo_root


def _justification(summary: str, *, impact: str, evidence: str) -> str:
    return json.dumps(
        {
            "summary": summary,
            "evidence_refs": [evidence],
            "expected_impact": impact,
        }
    )


DEMO_TASKS = (
    {
        "description": "Mejorar badges de estado y paginación en la web",
        "state": "ready",
        "priority": "high",
        "effort": "medium",
        "risk": "low",
        "task_type": "feature",
        "summary": "Colorear pills por grado y paginar listados para una lectura más clara.",
        "impact": "La web refleja mejor el estado operativo sin scroll infinito.",
        "evidence": "web://tasks-ui",
    },
    {
        "description": "Indicador de sync con pulso en sidebar e inicio",
        "state": "ready",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "feature",
        "summary": "Mostrar un punto animado según degradación o rutas pendientes.",
        "impact": "Operadores detectan sync degradado sin leer texto largo.",
        "evidence": "web://sync-indicator",
    },
    {
        "description": "Enlazar detalle de tarea con auditoría de origen",
        "state": "ready",
        "priority": "medium",
        "effort": "low",
        "risk": "medium",
        "task_type": "doc",
        "summary": "Desde el panel de tarea abrir la auditoría vinculada en /docs.",
        "impact": "Menos fricción entre spec y ejecución.",
        "evidence": "web://task-detail",
    },
    {
        "description": "Unificar badges en tareas vinculadas de auditorías",
        "state": "proposed",
        "priority": "low",
        "effort": "low",
        "risk": "low",
        "task_type": "refactor",
        "summary": "Reutilizar el mismo estilo de pills que la tabla principal.",
        "impact": "Consistencia visual entre /tasks y /docs.",
        "evidence": "web://docs-linked-tasks",
    },
)


def seed_web_tasks(*, repo_root: Path, dry_run: bool = False) -> int:
    bootstrap = NodeBootstrap(repo_root=repo_root)
    state = bootstrap.status(interactive=False)
    if state.state != "adopted" or not state.adopted_project:
        print("Repository is not adopted. Run: capiforge init && capiforge adopt", file=sys.stderr)
        return 1

    project_id = state.adopted_project["project_id"]
    store = NodeStore.from_file(state.node_db_path)
    try:
        audits = [row for row in store.list_project_audits(project_id) if row["state"] == "published"]
        if not audits:
            print("No published audits found. Publish an audit before seeding tasks.", file=sys.stderr)
            return 1

        audit_id = audits[0]["audit_id"]
        existing = {row["description"] for row in store.list_project_tasks(project_id)}
        created = 0
        for spec in DEMO_TASKS:
            if spec["description"] in existing:
                continue
            task_id = f"tsk_web_{uuid4().hex[:10]}"
            if dry_run:
                print(f"would create {task_id}: {spec['description']}")
                created += 1
                continue
            store.create_task(
                task_id,
                project_id,
                audit_id,
                spec["state"],
                spec["priority"],
                spec["effort"],
                spec["risk"],
                spec["task_type"],
                spec["description"],
                justification_json=_justification(
                    spec["summary"],
                    impact=spec["impact"],
                    evidence=spec["evidence"],
                ),
                execution_context_json=json.dumps({"source": "seed_web_demo_tasks"}),
            )
            created += 1
            print(f"created {task_id} -> {audit_id}")

        if not dry_run and created:
            store.db.commit()
        print(f"Done. {created} task(s) {'would be ' if dry_run else ''}created for audit {audit_id}.")
        return 0
    finally:
        store.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed web demo tasks with justification")
    parser.add_argument("--repo-root", type=Path, default=default_repo_root())
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    return seed_web_tasks(repo_root=args.repo_root.resolve(), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
