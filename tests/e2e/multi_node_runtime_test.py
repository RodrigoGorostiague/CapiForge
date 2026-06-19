import sqlite3
import tempfile
import unittest
from pathlib import Path

from runtime.coordinator.claims import ClaimRegistry
from runtime.coordinator.enrollment import EnrollmentRegistry
from runtime.coordinator.mcp import CoordinatorMCPSurface
from runtime.coordinator.routes import MutationRouteRegistry
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity, derive_node_proof


def connect_schema(db_path: Path, schema_path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(Path(schema_path).read_text())
    return connection


class MultiNodeEndToEndScenarioTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        root = Path(self.tempdir.name)

        self.owner_store = NodeStore(connect_schema(root / "owner.sqlite3", "storage/node-schema.sql"))
        self.remote_store = NodeStore(connect_schema(root / "remote.sqlite3", "storage/node-schema.sql"))
        self.coordinator_db = connect_schema(root / "coordinator.sqlite3", "storage/coordinator-schema.sql")
        self.addCleanup(self.owner_store.close)
        self.addCleanup(self.remote_store.close)
        self.addCleanup(self.coordinator_db.close)

        self.enrollment = EnrollmentRegistry(self.coordinator_db)
        self.claims = ClaimRegistry(self.coordinator_db)
        self.routes = MutationRouteRegistry(self.coordinator_db)
        self.coordinator = CoordinatorMCPSurface(self.routes, enrollment=self.enrollment)
        self.node_fingerprints = {"node_owner": "signed:owner", "node_remote": "signed:remote"}

        self.owner_surface = NodeMCPSurface(
            store=self.owner_store,
            router=NodeRouter(self.owner_store),
            claims=self.claims,
            coordinator=self.coordinator,
            enrollment=self.enrollment,
            local_node_id="node_owner",
        )
        self.remote_surface = NodeMCPSurface(
            store=self.remote_store,
            router=NodeRouter(self.remote_store),
            claims=self.claims,
            coordinator=self.coordinator,
            enrollment=self.enrollment,
            local_node_id="node_remote",
        )

        self.owner_actor = self.actor("node_owner", "agent_owner", "sess_owner")
        self.remote_actor = self.actor("node_remote", "agent_remote", "sess_remote")

        for store in (self.owner_store, self.remote_store):
            self._seed_node_store(store)
        self._seed_coordinator()

    def test_remote_traversal_reads_owner_routing_metadata(self) -> None:
        entrypoint = self.remote_surface.project_entrypoint_get(
            project_id="prj_shared",
            as_of="2026-06-18T12:10:00Z",
            actor=self.remote_actor,
        )
        self.assertEqual(entrypoint["status"], "ok")
        self.assertEqual(entrypoint["data"]["owner_node_id"], "node_owner")
        self.assertEqual(
            [project["project_id"] for project in entrypoint["data"]["linked_projects"]],
            ["prj_remote"],
        )

        ready = self.remote_surface.tasks_list_by_index(
            project_id="prj_shared",
            index_name="ready",
            as_of="2026-06-18T12:10:00Z",
            actor=self.remote_actor,
        )
        self.assertEqual([task["task_id"] for task in ready["data"]["tasks"]], ["tsk_shared_ready"])

        self.remote_surface.tasks_claim(
            claim_id="clm_shared_visibility",
            project_id="prj_shared",
            task_id="tsk_shared_ready",
            actor=self.remote_actor,
            plan="Prove project-scoped sync visibility",
            lease_started_at="2026-06-18T12:10:30Z",
            lease_expires_at="2026-06-18T12:15:30Z",
        )
        sync_status = self.remote_surface.sync_status(project_id="prj_shared", actor=self.remote_actor)
        self.assertEqual(sync_status["data"]["owner_node_id"], "node_owner")
        self.assertEqual(sync_status["data"]["coordinator_authority"], "non_authoritative")
        self.assertEqual(sync_status["data"]["canonical_write_path"], "owner_node_local")

    def test_claim_exclusivity_blocks_second_node(self) -> None:
        first = self.remote_surface.tasks_claim(
            claim_id="clm_1",
            project_id="prj_shared",
            task_id="tsk_shared_ready",
            actor=self.remote_actor,
            plan="Investigate shared issue",
            lease_started_at="2026-06-18T12:11:00Z",
            lease_expires_at="2026-06-18T12:16:00Z",
        )
        self.assertEqual(first["status"], "claimed")

        with self.assertRaises(SurfaceError) as ctx:
            self.owner_surface.tasks_claim(
                claim_id="clm_2",
                project_id="prj_shared",
                task_id="tsk_shared_ready",
                actor=self.owner_actor,
                plan="Try conflicting work",
                lease_started_at="2026-06-18T12:12:00Z",
                lease_expires_at="2026-06-18T12:17:00Z",
            )
        self.assertEqual(ctx.exception.code, "CLAIM_CONFLICT")

    def test_cross_project_request_routes_to_owner_acceptance(self) -> None:
        routed = self.remote_surface.cross_project_request(
            route_id="route_1",
            source_project_id="prj_remote",
            destination_project_id="prj_shared",
            actor=self.remote_actor,
            justification=JustificationPayload(
                summary="Need owner follow-up for shared task",
                evidence_refs=("artifact://remote/1",),
                expected_impact="Route work to canonical owner",
            ),
            created_at="2026-06-18T12:13:00Z",
        )
        self.assertEqual(routed["status"], "routed")
        self.assertEqual(routed["data"]["destination_owner_node_id"], "node_owner")

        pending = self.owner_surface.sync_status(project_id="prj_shared", actor=self.owner_actor)
        self.assertEqual(pending["data"]["pending_routes"], 1)

        accepted = self.routes.owner_decision(route_id="route_1", owner_actor=self.owner_actor, accept=True)
        self.assertEqual(accepted.status, "accepted")
        applied = self.owner_surface.apply_accepted_cross_project_request(
            route_id="route_1",
            project_id="prj_shared",
            audit_id="aud_shared",
            task_id="tsk_cross_project_followup",
            mutation_id="mut_cross_project_followup",
            actor=self.owner_actor,
            priority="medium",
            effort="low",
            risk="low",
            task_type="feature",
            description="Follow up approved remote request",
            execution_context={"requested_by": "prj_remote"},
        )
        self.assertEqual(applied["status"], "accepted")
        self.assertEqual(self.owner_store.get_task("tsk_cross_project_followup")["state"], "ready")

    def test_unrelated_enrolled_node_cannot_read_claim_or_route_foreign_project(self) -> None:
        self.enrollment.invite_node(
            node_id="node_observer",
            display_name="Observer",
            invitation_fingerprint="signed:observer",
            invited_by_human_actor_id="human_1",
            issued_at="2026-06-18T12:00:00Z",
            authority=self.actor("node_owner", "human_operator", "sess_admin_2", human_actor_id="human_1"),
        )
        self.enrollment.accept_invitation(
            node_id="node_observer",
            invitation_fingerprint="signed:observer",
            enrolled_at="2026-06-18T12:04:00Z",
        )
        self.node_fingerprints["node_observer"] = "signed:observer"
        observer_surface = NodeMCPSurface(
            store=self.remote_store,
            router=NodeRouter(self.remote_store),
            claims=self.claims,
            coordinator=self.coordinator,
            enrollment=self.enrollment,
            local_node_id="node_observer",
        )
        observer = self.actor("node_observer", "agent_observer", "sess_observer")

        with self.assertRaises(SurfaceError):
            observer_surface.project_entrypoint_get(
                project_id="prj_shared",
                as_of="2026-06-18T12:10:00Z",
                actor=observer,
            )
        with self.assertRaises(SurfaceError):
            observer_surface.tasks_list_by_index(
                project_id="prj_shared",
                index_name="ready",
                as_of="2026-06-18T12:10:00Z",
                actor=observer,
            )
        with self.assertRaises(SurfaceError):
            observer_surface.tasks_claim(
                claim_id="clm_observer",
                project_id="prj_shared",
                task_id="tsk_shared_ready",
                actor=observer,
                plan="Unauthorized claim",
                lease_started_at="2026-06-18T12:10:30Z",
                lease_expires_at="2026-06-18T12:15:30Z",
            )
        with self.assertRaises(SurfaceError):
            observer_surface.tasks_transition(
                project_id="prj_shared",
                task_id="tsk_shared_ready",
                mutation_id="mut_observer_block",
                actor=observer,
                requested_state="blocked",
                justification=JustificationPayload(
                    summary="Unauthorized transition",
                    evidence_refs=("artifact://observer/1",),
                    expected_impact="Should not enqueue a route",
                ),
                metadata={"blocked_reason": "unauthorized", "blocked_evidence": "artifact://observer/1", "blocked_next_step": "stop"},
            )

    def _seed_node_store(self, store: NodeStore) -> None:
        store.create_workspace("ws_1", "workspace://ws_1", "Workspace")
        store.upsert_project("prj_shared", "ws_1", "node_owner", "project://prj_shared", "Shared")
        store.upsert_project("prj_remote", "ws_1", "node_remote", "project://prj_remote", "Remote")
        store.create_audit("aud_shared", "prj_shared", "published", "Shared Audit", "body")
        store.create_audit("aud_remote", "prj_remote", "published", "Remote Audit", "body")
        store.create_task(
            "tsk_shared_ready",
            "prj_shared",
            "aud_shared",
            "ready",
            "high",
            "low",
            "low",
            "fix",
            "Shared ready task",
        )
        store.approve_project_link("prj_shared", "prj_remote", "human_1")
        store.approve_project_link("prj_remote", "prj_shared", "human_1")
        store.record_cross_project_approval(
            "apr_1",
            "prj_remote",
            "prj_shared",
            "2026-06-18T12:00:00Z",
            "human_1",
        )

    def _seed_coordinator(self) -> None:
        nodes = (
            ("node_owner", "Owner", "signed:owner", "2026-06-18T12:01:00Z"),
            ("node_remote", "Remote", "signed:remote", "2026-06-18T12:01:30Z"),
        )
        for node_id, display_name, fingerprint, _enrolled_at in nodes:
            self.enrollment.invite_node(
                node_id=node_id,
                display_name=display_name,
                invitation_fingerprint=fingerprint,
                invited_by_human_actor_id="human_1",
                issued_at="2026-06-18T12:00:00Z",
            )
        for node_id, _display_name, fingerprint, enrolled_at in nodes:
            self.enrollment.accept_invitation(
                node_id=node_id,
                invitation_fingerprint=fingerprint,
                enrolled_at=enrolled_at,
            )

        admin = self.actor("node_owner", "human_operator", "sess_admin", human_actor_id="human_1")
        self.enrollment.assign_owner(
            project_id="prj_shared",
            owner_node_id="node_owner",
            assigned_by_human_actor_id="human_1",
            assigned_at="2026-06-18T12:02:00Z",
            authority=admin,
        )
        self.enrollment.assign_owner(
            project_id="prj_remote",
            owner_node_id="node_remote",
            assigned_by_human_actor_id="human_1",
            assigned_at="2026-06-18T12:02:30Z",
            authority=admin,
        )
        self.coordinator_db.execute(
            "INSERT INTO notice_approvals (approval_id, source_project_id, target_project_id, notice_recorded_at, approved_by_human_actor_id, approval_status, routed_to_owner_node_id) VALUES (?,?,?,?,?,?,?)",
            ("notice_shared", "prj_remote", "prj_shared", "2026-06-18T12:02:45Z", "human_1", "approved", "node_owner"),
        )
        self.routes.announce_sync_status(
            announcement_id="ann_owner",
            node_id="node_owner",
            actor=self.actor("node_owner", "agent_owner", "sess_owner"),
            project_id="prj_shared",
            sync_status="healthy",
            summary={"queue_depth": 0},
            announced_at="2026-06-18T12:03:00Z",
        )

    def actor(self, node_id: str, agent_id: str, session_id: str, *, human_actor_id: str | None = None) -> ActorIdentity:
        return ActorIdentity(
            node_id=node_id,
            agent_id=agent_id,
            session_id=session_id,
            human_actor_id=human_actor_id,
            node_proof=derive_node_proof(
                node_id=node_id,
                agent_id=agent_id,
                session_id=session_id,
                invitation_fingerprint=self.node_fingerprints[node_id],
            ),
        )


if __name__ == "__main__":
    unittest.main()
