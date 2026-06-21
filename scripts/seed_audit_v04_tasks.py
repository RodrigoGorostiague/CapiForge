#!/usr/bin/env python3
"""Seed v0.4 expanded-hub audit-derived tasks as ready queue items."""

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
    {
        "lifecycle_key": "audit/v0.4/scope-audit",
        "description": "Publish audit v0.4 expanded hub document in repo and CapiForge.",
        "priority": "critical",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/architecture-update",
        "description": "Update architecture-v01, AGENTS.md, and create mvp-v04.md with 17 MCP tools.",
        "priority": "high",
        "effort": "medium",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/supersede-future-tasks",
        "description": "Close audit/future/* tasks with references to v0.4 RFC lifecycle keys.",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "ops",
    },
    {
        "lifecycle_key": "audit/v0.4/multi-project-switcher",
        "description": "Web navigation between adopted projects in a workspace without losing context.",
        "priority": "high",
        "effort": "medium",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.4/multi-project-registry-hardening",
        "description": "Harden project-repos.json registry, per-project paths, and tests.",
        "priority": "high",
        "effort": "medium",
        "risk": "medium",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.4/multi-project-entrypoint",
        "description": "Home/header reflects active project; document MCP bootstrap vs web registry.",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/onboarding-hub-page",
        "description": "Web onboarding block: install, skills, milestone contract, demo links.",
        "priority": "high",
        "effort": "medium",
        "risk": "low",
        "task_type": "feature",
    },
    {
        "lifecycle_key": "audit/v0.4/docs-indexer",
        "description": "Script indexing docs/**/*.md into local_documents.",
        "priority": "medium",
        "effort": "medium",
        "risk": "low",
        "task_type": "ops",
    },
    {
        "lifecycle_key": "audit/v0.4/demo-v04",
        "description": "Write updated 5-minute demo script for v0.4 hub.",
        "priority": "medium",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/rfc-sync-coordinator",
        "description": "RFC for v0.5 LAN coordinator sync activation (supersedes audit/future/sync-coordinator).",
        "priority": "medium",
        "effort": "medium",
        "risk": "medium",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/rfc-multi-user-workspaces",
        "description": "RFC for v0.6 multi-user invitations and permissions (supersedes audit/future/multi-user-workspaces).",
        "priority": "medium",
        "effort": "medium",
        "risk": "medium",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/rfc-admin-dashboards",
        "description": "RFC for v1.0 admin BI dashboards (supersedes audit/future/admin-dashboards).",
        "priority": "low",
        "effort": "medium",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/release/baseline-checklist",
        "description": "Run manual mvp-v04.md baseline and document pass/fail/blocked items.",
        "priority": "high",
        "effort": "low",
        "risk": "low",
        "task_type": "doc",
    },
    {
        "lifecycle_key": "audit/v0.4/release/full-test-suite",
        "description": "Run full unittest suite; fix regressions until green.",
        "priority": "critical",
        "effort": "high",
        "risk": "medium",
        "task_type": "ops",
    },
    {
        "lifecycle_key": "audit/v0.4/release/version-bump",
        "description": "Bump version to 0.4.0 in pyproject.toml and debian/changelog.",
        "priority": "high",
        "effort": "low",
        "risk": "low",
        "task_type": "ops",
    },
    {
        "lifecycle_key": "audit/v0.4/release/git-tag-v040",
        "description": "Create annotated git tag v0.4.0 after release gate is green.",
        "priority": "high",
        "effort": "low",
        "risk": "low",
        "task_type": "ops",
    },
]


def _mutation_id(*parts: str) -> str:
    return f"mut_{uuid5(NAMESPACE_URL, ':'.join(parts)).hex[:16]}"


def _build_actor(store: NodeStore, *, node_id: str) -> ActorIdentity:
    invitation_fingerprint = store.ensure_local_node_actor(node_id=node_id)
    agent_id = "capiforge-seed-script"
    session_id = "seed-audit-v04"
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
    with bootstrap.bootstrap_session(command="seed_audit_v04", timeout=30.0, interactive=False):
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
            as_of = "2026-06-21T18:00:00Z"
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
                    expected_impact="Close MVP v0.4 expanded hub gaps.",
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
    parser = argparse.ArgumentParser(description="Seed v0.4 expanded-hub audit-derived ready tasks.")
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
