from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.coordinator.claims import ClaimRegistry
from runtime.coordinator.enrollment import EnrollmentRegistry
from runtime.coordinator.mcp import CoordinatorMCPSurface
from runtime.coordinator.routes import MutationRouteRegistry
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity, canonical_id, derive_node_proof


COORDINATOR_SCHEMA = REPO_ROOT / "storage" / "coordinator-schema.sql"


def connect_coordinator(db_path: Path):
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(COORDINATOR_SCHEMA.read_text())
    return connection


def open_node_store(db_path: Path) -> NodeStore:
    return NodeStore.from_file(db_path)


def mirror_audit(source: NodeStore, destination: NodeStore, audit_id: str) -> None:
    audit = source.get_audit(audit_id)
    if not audit:
        raise ValueError(f"unknown audit: {audit_id}")
    if destination.get_audit(audit_id):
        return
    destination.create_audit(audit_id, audit["project_id"], audit["state"], audit["title"], audit["content"])


def mirror_task(source: NodeStore, destination: NodeStore, task_id: str) -> None:
    task = source.get_task(task_id)
    if not task:
        raise ValueError(f"unknown task: {task_id}")
    if destination.get_task(task_id):
        destination.update_task_state(
            task_id,
            state=task["state"],
            active_claim_session_id=task["active_claim_session_id"],
            blocked_reason=task["blocked_reason"],
            blocked_evidence=task["blocked_evidence"],
            blocked_next_step=task["blocked_next_step"],
            done_result=task["done_result"],
            done_artifacts=task["done_artifacts"],
            done_references=task["done_references"],
            done_expected_impact=task["done_expected_impact"],
        )
        return
    destination.create_task(
        task_id,
        task["project_id"],
        task["origin_audit_id"],
        task["state"],
        task["priority"],
        task["effort"],
        task["risk"],
        task["type"],
        task["description"],
        justification_json=task["justification_json"],
        execution_context_json=task["execution_context_json"],
        active_claim_session_id=task["active_claim_session_id"],
        blocked_reason=task["blocked_reason"],
        blocked_evidence=task["blocked_evidence"],
        blocked_next_step=task["blocked_next_step"],
        done_result=task["done_result"],
        done_artifacts=task["done_artifacts"],
        done_references=task["done_references"],
        done_expected_impact=task["done_expected_impact"],
    )


def bootstrap_project(store: NodeStore, *, workspace_id: str, workspace_name: str, project_id: str, project_name: str, owner_node_id: str) -> None:
    if not store.get_workspace(workspace_id):
        store.create_workspace(workspace_id, f"workspace://{workspace_name}", workspace_name)
    store.upsert_project(project_id, workspace_id, owner_node_id, f"project://{workspace_name}/{project_name}", project_name)


def run_demo(output_dir: Path) -> dict:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    owner_db_path = output_dir / "owner.sqlite3"
    worker_db_path = output_dir / "worker.sqlite3"
    coordinator_db_path = output_dir / "coordinator.sqlite3"

    owner_store = open_node_store(owner_db_path)
    worker_store = open_node_store(worker_db_path)
    coordinator_db = connect_coordinator(coordinator_db_path)

    enrollment = EnrollmentRegistry(coordinator_db)
    claims = ClaimRegistry(coordinator_db)
    routes = MutationRouteRegistry(coordinator_db)
    coordinator = CoordinatorMCPSurface(routes, enrollment=enrollment)

    owner_surface = NodeMCPSurface(store=owner_store, router=NodeRouter(owner_store), claims=claims, coordinator=coordinator, enrollment=enrollment, local_node_id="node_owner")
    worker_surface = NodeMCPSurface(store=worker_store, router=NodeRouter(worker_store), claims=claims, coordinator=coordinator, enrollment=enrollment, local_node_id="node_worker")

    owner_fingerprint = "signed:owner"
    worker_fingerprint = "signed:worker"
    owner_actor = ActorIdentity(node_id="node_owner", agent_id="agent_owner", session_id="sess_owner", node_proof=derive_node_proof(node_id="node_owner", agent_id="agent_owner", session_id="sess_owner", invitation_fingerprint=owner_fingerprint))
    worker_actor = ActorIdentity(node_id="node_worker", agent_id="agent_worker", session_id="sess_worker", node_proof=derive_node_proof(node_id="node_worker", agent_id="agent_worker", session_id="sess_worker", invitation_fingerprint=worker_fingerprint))

    workspace_name = "Casa"
    project_name = "CapiForge"
    worker_project_name = "CapiForge Worker"
    workspace_id = canonical_id("workspace", workspace_name)
    project_id = canonical_id("project", workspace_name, project_name)
    worker_project_id = canonical_id("project", workspace_name, worker_project_name)
    audit_id = canonical_id("audit", project_id, "published-audit")
    task_id = canonical_id("task", project_id, audit_id, "review-runtime")

    transition_justification = JustificationPayload(
        summary="Promote validated runtime work",
        evidence_refs=("artifact://demo/runtime-validation",),
        expected_impact="Task becomes ready for coordinated execution",
    )
    route_justification = JustificationPayload(
        summary="Worker requests owner-side block",
        evidence_refs=("artifact://demo/worker-observation",),
        expected_impact="Owner must explicitly approve the mutation",
    )

    steps: list[dict] = []

    steps.append(
        {
            "step": 1,
            "action": "bootstrap owner/worker/coordinator SQLite DBs",
            "result": "ok",
            "details": {
                "owner_db": str(owner_db_path),
                "worker_db": str(worker_db_path),
                "coordinator_db": str(coordinator_db_path),
            },
        }
    )

    for store in (owner_store, worker_store):
        bootstrap_project(
            store,
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            project_id=project_id,
            project_name=project_name,
            owner_node_id="node_owner",
        )
    bootstrap_project(
        worker_store,
        workspace_id=workspace_id,
        workspace_name=workspace_name,
        project_id=worker_project_id,
        project_name=worker_project_name,
        owner_node_id="node_worker",
    )
    worker_store.approve_project_link(worker_project_id, project_id, "human_demo")
    worker_store.approve_project_link(project_id, worker_project_id, "human_demo")
    worker_store.record_cross_project_approval(
        "apr-worker-owner",
        worker_project_id,
        project_id,
        "2026-06-18T12:02:45Z",
        "human_demo",
    )
    steps.append(
        {
            "step": 2,
            "action": "create workspace Casa",
            "result": "ok",
            "details": owner_store.get_workspace(workspace_id),
        }
    )
    steps.append(
        {
            "step": 3,
            "action": "create project CapiForge",
            "result": "ok",
            "details": owner_store.get_project(project_id),
        }
    )

    invited_nodes = (
        ("node_owner", "Owner Node", owner_fingerprint, "2026-06-18T12:01:00Z"),
        ("node_worker", "Worker Node", worker_fingerprint, "2026-06-18T12:01:30Z"),
    )
    for node_id, display_name, fingerprint, _enrolled_at in invited_nodes:
        enrollment.invite_node(
            node_id=node_id,
            display_name=display_name,
            invitation_fingerprint=fingerprint,
            invited_by_human_actor_id="human_demo",
            issued_at="2026-06-18T12:00:00Z",
        )
    for node_id, _display_name, fingerprint, enrolled_at in invited_nodes:
        enrollment.accept_invitation(node_id=node_id, invitation_fingerprint=fingerprint, enrolled_at=enrolled_at)
    owner_assignment = enrollment.assign_owner(
        project_id=project_id,
        owner_node_id="node_owner",
        assigned_by_human_actor_id="human_demo",
        assigned_at="2026-06-18T12:02:00Z",
        authority=ActorIdentity(node_id="node_owner", agent_id="human_operator", session_id="sess_admin", human_actor_id="human_demo", node_proof=derive_node_proof(node_id="node_owner", agent_id="human_operator", session_id="sess_admin", invitation_fingerprint=owner_fingerprint)),
    )
    enrollment.assign_owner(
        project_id=worker_project_id,
        owner_node_id="node_worker",
        assigned_by_human_actor_id="human_demo",
        assigned_at="2026-06-18T12:02:30Z",
        authority=ActorIdentity(node_id="node_owner", agent_id="human_operator", session_id="sess_admin", human_actor_id="human_demo", node_proof=derive_node_proof(node_id="node_owner", agent_id="human_operator", session_id="sess_admin", invitation_fingerprint=owner_fingerprint)),
    )
    coordinator_db.execute(
        "INSERT INTO notice_approvals (approval_id, source_project_id, target_project_id, notice_recorded_at, approved_by_human_actor_id, approval_status, routed_to_owner_node_id) VALUES (?,?,?,?,?,?,?)",
        ("notice-worker-owner", worker_project_id, project_id, "2026-06-18T12:02:45Z", "human_demo", "approved", "node_owner"),
    )
    routes.announce_sync_status(
        announcement_id="ann-owner",
        node_id="node_owner",
        actor=owner_actor,
        project_id=project_id,
        sync_status="healthy",
        summary={"queue_depth": 0},
        announced_at="2026-06-18T12:03:00Z",
    )
    steps.append(
        {
            "step": 4,
            "action": "assign owner node",
            "result": "ok",
            "details": {
                "project_id": owner_assignment.project_id,
                "owner_node_id": owner_assignment.owner_node_id,
                "owner_status": owner_assignment.owner_status,
            },
        }
    )

    owner_store.create_audit(audit_id, project_id, "published", "CapiForge runtime audit", "Initial runtime walkthrough for Casa/CapiForge")
    mirror_audit(owner_store, worker_store, audit_id)
    steps.append(
        {
            "step": 5,
            "action": "create a published audit",
            "result": "ok",
            "details": owner_store.get_audit(audit_id),
        }
    )

    task_created = owner_surface.tasks_create_from_audit(
        task_id=task_id,
        project_id=project_id,
        audit_id=audit_id,
        mutation_id="mut-create-task",
        actor=owner_actor,
        priority="high",
        effort="medium",
        risk="low",
        task_type="ops",
        description="Run the initial V1 runtime demo flow against this repository",
        justification=transition_justification,
        execution_context={"repo_path": str(REPO_ROOT), "workspace": workspace_name, "project": project_name},
        initial_state="proposed",
    )
    steps.append(
        {
            "step": 6,
            "action": "create a task from that audit",
            "result": task_created["status"],
            "details": task_created["data"],
        }
    )

    task_ready = owner_surface.tasks_transition(
        project_id=project_id,
        task_id=task_id,
        mutation_id="mut-ready-task",
        actor=owner_actor,
        requested_state="ready",
        justification=transition_justification,
        metadata={"conflict_status": "clear"},
    )
    mirror_task(owner_store, worker_store, task_id)
    steps.append(
        {
            "step": 7,
            "action": "move it to ready",
            "result": task_ready["status"],
            "details": owner_store.get_task(task_id),
        }
    )

    first_claim = worker_surface.tasks_claim(
        claim_id="clm-worker-1",
        project_id=project_id,
        task_id=task_id,
        actor=worker_actor,
        plan="Walk the real runtime flow end-to-end",
        lease_started_at="2026-06-18T12:11:00Z",
        lease_expires_at="2026-06-18T12:16:00Z",
    )
    steps.append(
        {
            "step": 8,
            "action": "claim it from one node",
            "result": first_claim["status"],
            "details": first_claim["data"],
        }
    )

    routes.announce_sync_status(
        announcement_id="ann-worker",
        node_id="node_worker",
        actor=worker_actor,
        project_id=project_id,
        sync_status="healthy",
        summary={"queue_depth": 0},
        announced_at="2026-06-18T12:11:30Z",
    )

    conflict_details: dict
    try:
        owner_surface.tasks_claim(
            claim_id="clm-owner-conflict",
            project_id=project_id,
            task_id=task_id,
            actor=owner_actor,
            plan="Attempt conflicting claim",
            lease_started_at="2026-06-18T12:12:00Z",
            lease_expires_at="2026-06-18T12:17:00Z",
        )
        conflict_details = {"unexpected": "second claim succeeded"}
    except SurfaceError as exc:
        conflict_details = {"code": exc.code, "message": exc.message}
    steps.append(
        {
            "step": 9,
            "action": "attempt conflicting claim from another node",
            "result": "blocked" if conflict_details.get("code") == "CLAIM_CONFLICT" else "unexpected",
            "details": conflict_details,
        }
    )

    in_progress = owner_surface.tasks_transition(
        project_id=project_id,
        task_id=task_id,
        mutation_id="mut-in-progress",
        actor=owner_actor,
        requested_state="in_progress",
        justification=transition_justification,
        metadata={
            "active_claim_session_id": worker_actor.session_id,
            "as_of": "2026-06-18T12:12:30Z",
        },
    )
    mirror_task(owner_store, worker_store, task_id)
    steps.append(
        {
            "step": 10,
            "action": "move to in_progress with a real active claim",
            "result": in_progress["status"],
            "details": owner_store.get_task(task_id),
        }
    )

    released = worker_surface.tasks_release(
        project_id=project_id,
        task_id=task_id,
        claim_id="clm-worker-1",
        actor=worker_actor,
    )
    mirror_task(owner_store, worker_store, task_id)
    steps.append(
        {
            "step": 11,
            "action": "release the claim",
            "result": released["status"],
            "details": released["data"],
        }
    )

    routed = worker_surface.tasks_transition(
        project_id=project_id,
        task_id=task_id,
        mutation_id="mut-worker-block",
        actor=worker_actor,
        requested_state="blocked",
        justification=route_justification,
        source_project_id=worker_project_id,
        metadata={
            "blocked_reason": "Worker found follow-up risk requiring owner call",
            "blocked_evidence": "artifact://demo/worker-observation",
            "blocked_next_step": "Owner reviews and explicitly accepts or rejects",
        },
    )
    steps.append(
        {
            "step": 12,
            "action": "emit a routed non-owner mutation",
            "result": routed["status"],
            "details": routed["data"],
        }
    )

    summary = {
        "succeeded": conflict_details.get("code") == "CLAIM_CONFLICT" and routed["data"].get("acceptance_signal") == "ROUTE_OWNER_ACCEPTANCE_REQUIRED",
        "workspace": {"workspace_id": workspace_id, "name": workspace_name},
        "project": {"project_id": project_id, "name": project_name},
        "paths": {
            "owner_db": str(owner_db_path),
            "worker_db": str(worker_db_path),
            "coordinator_db": str(coordinator_db_path),
        },
        "steps": steps,
        "notes": [
            "Owner and worker node stores now reuse the shared persistent SQLite helper used by the owner-local bootstrap flow.",
            "Canonical task creation and state transitions ran through the owner node MCP surface; claim exclusivity and owner-acceptance routing ran through the coordinator-backed runtime.",
        ],
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the CapiForge V1 runtime SQLite demo flow")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "demo-runtime"),
        help="Directory where demo SQLite files and summary.json will be written",
    )
    args = parser.parse_args()

    summary = run_demo(Path(args.output_dir).resolve())
    print(json.dumps(summary, indent=2))
    return 0 if summary["succeeded"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
