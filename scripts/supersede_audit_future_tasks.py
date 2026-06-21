#!/usr/bin/env python3
"""Cancel audit/future/* ready tasks superseded by audit/v0.4 RFC tasks."""

from __future__ import annotations

import argparse
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
from runtime.shared.ids import ActorIdentity, derive_node_proof

SUPERSESSIONS = {
    "audit/future/sync-coordinator": "audit/v0.4/rfc-sync-coordinator",
    "audit/future/multi-user-workspaces": "audit/v0.4/rfc-multi-user-workspaces",
    "audit/future/admin-dashboards": "audit/v0.4/rfc-admin-dashboards",
}


def _mutation_id(*parts: str) -> str:
    return f"mut_{uuid5(NAMESPACE_URL, ':'.join(parts)).hex[:16]}"


def _build_actor(store: NodeStore, *, node_id: str) -> ActorIdentity:
    invitation_fingerprint = store.ensure_local_node_actor(node_id=node_id)
    agent_id = "capiforge-seed-script"
    session_id = "supersede-audit-future"
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


def supersede(*, repo_root: Path, dry_run: bool = False) -> list[dict]:
    bootstrap = NodeBootstrap(repo_root=str(repo_root))
    results: list[dict] = []
    with bootstrap.bootstrap_session(command="supersede_audit_future", timeout=30.0, interactive=False):
        state, store = bootstrap._open_adopted_store_unlocked()
        try:
            project_id = state.adopted_project["project_id"]
            actor = _build_actor(store, node_id=state.local_node_id)
            surface = NodeMCPSurface(
                store=store,
                router=NodeRouter(store),
                local_node_id=state.local_node_id,
                claims=ClaimRegistry(store.db),
            )
            as_of = "2026-06-21T18:00:00Z"
            for lifecycle_key, replacement in SUPERSESSIONS.items():
                task = store.get_task_by_lifecycle_key(project_id, lifecycle_key)
                if not task:
                    results.append({"lifecycle_key": lifecycle_key, "status": "missing"})
                    continue
                if task["state"] == "cancelled":
                    results.append({"lifecycle_key": lifecycle_key, "task_id": task["task_id"], "status": "already_cancelled"})
                    continue
                if dry_run:
                    results.append({"lifecycle_key": lifecycle_key, "task_id": task["task_id"], "status": "dry_run"})
                    continue
                surface.tasks_transition(
                    project_id=project_id,
                    task_id=task["task_id"],
                    mutation_id=_mutation_id("cancel", task["task_id"], as_of),
                    actor=actor,
                    requested_state="cancelled",
                    justification=JustificationPayload(
                        summary=f"Superseded by {replacement}",
                        evidence_refs=(f"lifecycle://{replacement}",),
                        expected_impact="Remove stale future backlog in favor of v0.4 RFC tasks.",
                    ),
                    metadata={
                        "done_result": f"Superseded by {replacement}",
                        "done_artifacts": "docs/audits/audit-v04-expanded-hub.md",
                        "done_references": replacement,
                        "done_expected_impact": "v0.4 RFC track replaces audit/future backlog item",
                    },
                )
                results.append({"lifecycle_key": lifecycle_key, "task_id": task["task_id"], "status": "cancelled"})
            store.db.commit()
        finally:
            store.close()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Cancel superseded audit/future ready tasks.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    for item in supersede(repo_root=Path(args.repo_root), dry_run=args.dry_run):
        print(f"{item['status']}: {item['lifecycle_key']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
