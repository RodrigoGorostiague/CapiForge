#!/usr/bin/env python3
"""Seed v0.3 scope-pivot audit-derived tasks as ready queue items."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.coordinator.claims import ClaimRegistry
from runtime.node.bootstrap import NodeBootstrap
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload
from runtime.shared.ids import ActorIdentity, canonical_id, derive_node_proof

TASK_SPECS = [
    # Fase 0
    {
        "lifecycle_key": "audit/v0.3/scope-pivot-audit",
        "description": "Publish audit v0.3 scope pivot document in repo and CapiForge.",
        "priority": "critical",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.3/vision-docs",
        "description": "Rewrite mvp.md, architecture-v01.md, and AGENTS.md with documentation-hub pivot.",
        "priority": "high",
        "effort": "medium",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.3/engram-boundary",
        "description": "Document boundaries between CapiForge, Engram, and OpenSpec in architecture and skills.",
        "priority": "high",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    # Fase 1
    {
        "lifecycle_key": "audit/v0.3/skill-publish-milestone",
        "description": "Create capiforge-publish-milestone skill with milestone publication contract.",
        "priority": "critical",
        "effort": "medium",
        "risk": "low",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/skills-realign",
        "description": "Update pickup/start/close skills as optional; align data-layer with hybrid truth model.",
        "priority": "high",
        "effort": "medium",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.3/agents-decision-tree",
        "description": "Update AGENTS.md with milestone-first decision tree for agents.",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    # Fase 2
    {
        "lifecycle_key": "audit/v0.3/schema-project-pages",
        "description": "Design and migrate project_pages table (purpose, architecture, custom types).",
        "priority": "high",
        "effort": "high",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/mcp-project-pages",
        "description": "Expose MCP read/upsert for project pages (or UI-only MVP path).",
        "priority": "medium",
        "effort": "medium",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/seed-project-docs",
        "description": "Seed CapiForge purpose and architecture content into project pages.",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    # Fase 3
    {
        "lifecycle_key": "audit/v0.3/ui-project-home",
        "description": "Web UI home/onboarding page with purpose, architecture summary, and project state.",
        "priority": "high",
        "effort": "high",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/ui-doc-editor",
        "description": "Web UI markdown editor for project pages.",
        "priority": "high",
        "effort": "high",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/ui-task-create",
        "description": "Web UI human task creation from the task database view.",
        "priority": "medium",
        "effort": "medium",
        "risk": "low",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/ui-local-docs-viewer",
        "description": "Web UI viewer for local_documents repo file references.",
        "priority": "low",
        "effort": "medium",
        "risk": "low",
        "task_type": "feature",
    },
    # Fase 4
    {
        "lifecycle_key": "audit/v0.3/mcp-milestone-batch",
        "description": "Optional milestone_publish MCP tool (audit + task closure in one call).",
        "priority": "medium",
        "effort": "medium",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.3/mvp-checklist-v03",
        "description": "Write MVP v0.3 acceptance checklist in docs/.",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    # Fase 5 backlog
    {
        "lifecycle_key": "audit/future/multi-user-workspaces",
        "description": "Design multi-user workspace invitations and permissions (post-MVP).",
        "priority": "low",
        "effort": "high",
        "risk": "high",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/future/sync-coordinator",
        "description": "Activate multi-machine sync via LAN coordinator (post-MVP).",
        "priority": "low",
        "effort": "high",
        "risk": "high",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/future/admin-dashboards",
        "description": "Design cross-project admin BI dashboards (post-MVP).",
        "priority": "low",
        "effort": "high",
        "risk": "medium",
        "task_type": "doc",
    },
]


def _mutation_id(*parts: str) -> str:
    return f"mut_{uuid5(NAMESPACE_URL, ':'.join(parts)).hex[:16]}"


def _build_actor(store: NodeStore, *, node_id: str) -> ActorIdentity:
    invitation_fingerprint = store.ensure_local_node_actor(node_id=node_id)
    agent_id = "capiforge-seed-script"
    session_id = "seed-audit-v03"
    return ActorIdentity(
        node_id=node_id,
        agent_id=agent_id,
        session_id=session_id,
        node_proof=derive_node_proof(
            node_id=node_id,
            agent_id=agent_id,
            session_id=session_id,
            invitation_fingerprint=invitation_fingerprint,
        ),
    )


def seed_tasks(*, repo_root: Path, audit_id: str, dry_run: bool = False) -> list[dict]:
    bootstrap = NodeBootstrap(repo_root=str(repo_root))
    created: list[dict] = []
    with bootstrap.bootstrap_session(command="seed_audit_v03", timeout=30.0, interactive=False):
        state, store = bootstrap._open_adopted_store_unlocked()
        try:
            project_id = state.adopted_project["project_id"]
            audit = store.get_audit(audit_id)
            if not audit or audit["state"] != "published":
                raise RuntimeError(f"audit must be published: {audit_id}")
            actor = _build_actor(store, node_id=state.local_node_id)
            surface = NodeMCPSurface(
                store=store,
                router=NodeRouter(store),
                local_node_id=state.local_node_id,
                claims=ClaimRegistry(store.db),
            )
            as_of = "2026-06-21T16:30:00Z"
            for spec in TASK_SPECS:
                lifecycle_key = spec["lifecycle_key"]
                existing = store.get_task_by_lifecycle_key(project_id, lifecycle_key)
                if existing:
                    created.append({"lifecycle_key": lifecycle_key, "task_id": existing["task_id"], "status": "exists"})
                    continue
                task_id = canonical_id("task", project_id, lifecycle_key)
                justification = JustificationPayload(
                    summary=f"Derived from audit {audit_id}: {spec['description']}",
                    evidence_refs=(f"audit://{audit_id}", f"lifecycle://{lifecycle_key}"),
                    expected_impact="Close v0.3 scope-pivot gaps identified in audit v0.3.",
                )
                execution_context = {
                    "project_id": project_id,
                    "lifecycle_key": lifecycle_key,
                    "origin_audit_id": audit_id,
                    "audit_title": audit["title"],
                }
                if dry_run:
                    created.append({"lifecycle_key": lifecycle_key, "task_id": task_id, "status": "dry_run"})
                    continue
                surface.tasks_create_from_audit(
                    task_id=task_id,
                    project_id=project_id,
                    audit_id=audit_id,
                    mutation_id=_mutation_id(task_id, "seed", as_of),
                    actor=actor,
                    priority=spec["priority"],
                    effort=spec["effort"],
                    risk=spec["risk"],
                    task_type=spec["task_type"],
                    description=spec["description"],
                    justification=justification,
                    execution_context=execution_context,
                    initial_state="ready",
                    lifecycle_key=lifecycle_key,
                )
                created.append({"lifecycle_key": lifecycle_key, "task_id": task_id, "status": "created"})
            store.db.commit()
        finally:
            store.close()
    return created


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed v0.3 audit-derived ready tasks.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = seed_tasks(repo_root=Path(args.repo_root), audit_id=args.audit_id, dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"audit_id": args.audit_id, "tasks": result}, indent=2, sort_keys=True))
    else:
        for item in result:
            print(f"{item['status']}: {item['lifecycle_key']} -> {item['task_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
