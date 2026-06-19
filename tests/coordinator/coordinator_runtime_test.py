import sqlite3
import unittest
from pathlib import Path

from runtime.coordinator.claims import ClaimConflictError, ClaimRegistry
from runtime.coordinator.enrollment import EnrollmentRegistry
from runtime.coordinator.mcp import CoordinatorMCPSurface
from runtime.coordinator.routes import MutationRouteRegistry, RouteValidationError
from runtime.shared.errors import SurfaceError
from runtime.shared.contracts import JustificationPayload
from runtime.shared.ids import ActorIdentity, derive_node_proof


class CoordinatorRuntimeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(Path("storage/coordinator-schema.sql").read_text())
        self.enrollment = EnrollmentRegistry(self.db)
        self.claims = ClaimRegistry(self.db)
        self.routes = MutationRouteRegistry(self.db)
        self.coordinator = CoordinatorMCPSurface(self.routes, enrollment=self.enrollment)
        self.node_fingerprints = {"node_owner": "signed:owner", "node_worker": "signed:worker"}

        self.enrollment.invite_node(
            node_id="node_owner",
            display_name="Owner",
            invitation_fingerprint="signed:owner",
            invited_by_human_actor_id="human_1",
            issued_at="2026-06-18T12:00:00Z",
        )
        self.enrollment.invite_node(
            node_id="node_worker",
            display_name="Worker",
            invitation_fingerprint="signed:worker",
            invited_by_human_actor_id="human_1",
            issued_at="2026-06-18T12:00:00Z",
        )
        self.enrollment.accept_invitation(
            node_id="node_owner",
            invitation_fingerprint="signed:owner",
            enrolled_at="2026-06-18T12:01:00Z",
        )
        self.enrollment.accept_invitation(
            node_id="node_worker",
            invitation_fingerprint="signed:worker",
            enrolled_at="2026-06-18T12:01:30Z",
        )
        self.enrollment.invite_node(
            node_id="node_observer",
            display_name="Observer",
            invitation_fingerprint="signed:observer",
            invited_by_human_actor_id="human_1",
            issued_at="2026-06-18T12:00:00Z",
            authority=self.actor("node_owner", "human_operator", "sess_bootstrap", human_actor_id="human_1"),
        )
        self.enrollment.accept_invitation(
            node_id="node_observer",
            invitation_fingerprint="signed:observer",
            enrolled_at="2026-06-18T12:01:45Z",
        )
        self.node_fingerprints["node_observer"] = "signed:observer"
        admin = self.actor("node_owner", "human_operator", "sess_admin", human_actor_id="human_1")
        self.enrollment.assign_owner(
            project_id="prj_main",
            owner_node_id="node_owner",
            assigned_by_human_actor_id="human_1",
            assigned_at="2026-06-18T12:02:00Z",
            authority=admin,
        )
        self.enrollment.assign_owner(
            project_id="prj_remote",
            owner_node_id="node_worker",
            assigned_by_human_actor_id="human_1",
            assigned_at="2026-06-18T12:02:15Z",
            authority=admin,
        )
        self.db.execute(
            "INSERT INTO notice_approvals (approval_id, source_project_id, target_project_id, notice_recorded_at, approved_by_human_actor_id, approval_status, routed_to_owner_node_id) VALUES (?,?,?,?,?,?,?)",
            ("notice_main", "prj_remote", "prj_main", "2026-06-18T12:02:30Z", "human_1", "approved", "node_owner"),
        )

    def actor(self, node_id: str, agent_id: str, session_id: str, *, human_actor_id: str | None = None, node_proof: str | None = None) -> ActorIdentity:
        proof = node_proof if node_proof is not None else derive_node_proof(
            node_id=node_id,
            agent_id=agent_id,
            session_id=session_id,
            invitation_fingerprint=self.node_fingerprints[node_id],
        )
        return ActorIdentity(node_id=node_id, agent_id=agent_id, session_id=session_id, human_actor_id=human_actor_id, node_proof=proof)

    def test_claim_collision_requires_exclusive_lease(self) -> None:
        worker = self.actor("node_worker", "agent_1", "sess_1")
        owner = self.actor("node_owner", "agent_2", "sess_2")
        first = self.claims.claim_task(
            claim_id="clm_1",
            project_id="prj_main",
            task_id="tsk_1",
            actor=worker,
            plan="Investigate outage",
            lease_started_at="2026-06-18T12:05:00Z",
            lease_expires_at="2026-06-18T12:10:00Z",
        )
        self.assertEqual(first.status, "active")
        with self.assertRaises(ClaimConflictError):
            self.claims.claim_task(
                claim_id="clm_2",
                project_id="prj_main",
                task_id="tsk_1",
                actor=owner,
                plan="Take over same task",
                lease_started_at="2026-06-18T12:06:00Z",
                lease_expires_at="2026-06-18T12:11:00Z",
            )

    def test_expiry_recovery_surfaces_stale_claims(self) -> None:
        worker = self.actor("node_worker", "agent_1", "sess_1")
        self.claims.claim_task(
            claim_id="clm_1",
            project_id="prj_main",
            task_id="tsk_1",
            actor=worker,
            plan="Initial work",
            lease_started_at="2026-06-18T12:05:00Z",
            lease_expires_at="2026-06-18T12:06:00Z",
        )
        stale = self.claims.list_stale_claims(as_of="2026-06-18T12:07:00Z")
        self.assertEqual([(row["claim_id"], row["status"]) for row in stale], [("clm_1", "expired")])
        recovered = self.claims.claim_task(
            claim_id="clm_2",
            project_id="prj_main",
            task_id="tsk_1",
            actor=self.actor("node_owner", "agent_owner", "sess_owner"),
            plan="Recover ownership",
            lease_started_at="2026-06-18T12:07:30Z",
            lease_expires_at="2026-06-18T12:12:30Z",
        )
        self.assertEqual((recovered.claim_id, recovered.status), ("clm_2", "active"))

    def test_renewal_extends_existing_lease(self) -> None:
        worker = self.actor("node_worker", "agent_1", "sess_1")
        self.claims.claim_task(
            claim_id="clm_renew",
            project_id="prj_main",
            task_id="tsk_renew",
            actor=worker,
            plan="Keep working",
            lease_started_at="2026-06-18T12:05:00Z",
            lease_expires_at="2026-06-18T12:10:00Z",
        )
        renewed = self.claims.renew_claim(
            claim_id="clm_renew",
            actor=worker,
            lease_expires_at="2026-06-18T12:15:00Z",
            renewed_at="2026-06-18T12:08:00Z",
        )
        self.assertEqual(renewed.status, "renewed")
        self.assertEqual(renewed.lease_expires_at, "2026-06-18T12:15:00Z")
        active = self.claims.get_active_claim(project_id="prj_main", task_id="tsk_renew", as_of="2026-06-18T12:09:00Z")
        self.assertEqual(active.claim_id, "clm_renew")

    def test_routed_mutation_requires_owner_acceptance(self) -> None:
        worker = self.actor("node_worker", "agent_1", "sess_1")
        self.claims.claim_task(
            claim_id="clm_route_access",
            project_id="prj_main",
            task_id="tsk_route_access",
            actor=worker,
            plan="Establish project participation before routing",
            lease_started_at="2026-06-18T12:07:00Z",
            lease_expires_at="2026-06-18T12:12:00Z",
        )
        proposal = self.routes.submit_proposal(
            route_id="rte_1",
            destination_project_id="prj_main",
            actor=worker,
            request_kind="task_transition",
            justification=JustificationPayload(
                summary="Need owner to block task",
                evidence_refs=("artifact://evidence/1",),
                expected_impact="Prevent conflicting work",
            ),
            created_at="2026-06-18T12:08:00Z",
        )
        self.assertEqual((proposal.status, proposal.destination_owner_node_id), ("proposed", "node_owner"))
        routed = self.routes.mark_routed(route_id="rte_1")
        self.assertEqual(routed.status, "routed")
        with self.assertRaises(RouteValidationError):
            self.routes.owner_decision(
                route_id="rte_1",
                owner_actor=self.actor("node_worker", "agent_1", "sess_1"),
                accept=True,
            )
        accepted = self.routes.owner_decision(
            route_id="rte_1",
            owner_actor=self.actor("node_owner", "agent_owner", "sess_owner"),
            accept=True,
        )
        self.assertEqual(accepted.status, "accepted")

    def test_cross_project_request_requires_coordinator_notice_approval(self) -> None:
        self.db.execute(
            "DELETE FROM notice_approvals WHERE source_project_id = ? AND target_project_id = ?",
            ("prj_remote", "prj_main"),
        )
        with self.assertRaises(SurfaceError) as ctx:
            self.coordinator.cross_project_request(
                route_id="rte_missing_notice",
                destination_project_id="prj_main",
                actor=self.actor("node_worker", "agent_worker", "sess_worker_missing_notice"),
                justification=JustificationPayload(
                    summary="Missing coordinator approval",
                    evidence_refs=("artifact://evidence/missing-notice",),
                    expected_impact="Should be blocked",
                ),
                created_at="2026-06-18T12:08:15Z",
                source_project_id="prj_remote",
            )
        self.assertEqual(ctx.exception.code, "CROSS_PROJECT_APPROVAL_REQUIRED")

    def test_owner_acceptance_rechecks_cross_project_approval_state(self) -> None:
        self.claims.claim_task(
            claim_id="clm_cross_project_access",
            project_id="prj_remote",
            task_id="tsk_remote_access",
            actor=self.actor("node_worker", "agent_worker", "sess_worker_access"),
            plan="Establish project participation before routing",
            lease_started_at="2026-06-18T12:07:00Z",
            lease_expires_at="2026-06-18T12:12:00Z",
        )
        proposal = self.coordinator.cross_project_request(
            route_id="rte_cross_project_recheck",
            destination_project_id="prj_main",
            actor=self.actor("node_worker", "agent_worker", "sess_worker_access"),
            justification=JustificationPayload(
                summary="Create approved cross-project work",
                evidence_refs=("artifact://evidence/recheck",),
                expected_impact="Require approval at accept time too",
            ),
            created_at="2026-06-18T12:08:20Z",
            source_project_id="prj_remote",
        )
        self.assertEqual(proposal["status"], "routed")
        self.db.execute(
            "UPDATE notice_approvals SET approval_status = 'revoked' WHERE source_project_id = ? AND target_project_id = ?",
            ("prj_remote", "prj_main"),
        )
        with self.assertRaises(RouteValidationError):
            self.routes.owner_decision(
                route_id="rte_cross_project_recheck",
                owner_actor=self.actor("node_owner", "agent_owner", "sess_owner_recheck"),
                accept=True,
            )

    def test_trusted_node_proof_is_required_for_sensitive_routes(self) -> None:
        with self.assertRaises(RouteValidationError):
            self.routes.submit_proposal(
                route_id="rte_untrusted",
                destination_project_id="prj_main",
                actor=ActorIdentity(node_id="node_worker", agent_id="agent_1", session_id="sess_1"),
                request_kind="task_transition",
                justification=JustificationPayload(
                    summary="Missing proof",
                    evidence_refs=("artifact://evidence/2",),
                    expected_impact="Should fail",
                ),
                created_at="2026-06-18T12:08:00Z",
            )

    def test_outage_degradation_keeps_coordinator_non_authoritative(self) -> None:
        self.claims.claim_task(
            claim_id="clm_outage_worker",
            project_id="prj_main",
            task_id="tsk_outage",
            actor=self.actor("node_worker", "agent_sync", "sess_sync"),
            plan="Observe coordinator degradation",
            lease_started_at="2026-06-18T12:08:30Z",
            lease_expires_at="2026-06-18T12:13:30Z",
        )
        self.routes.announce_sync_status(
            announcement_id="ann_1",
            node_id="node_owner",
            actor=self.actor("node_owner", "agent_owner", "sess_owner"),
            project_id="prj_main",
            sync_status="offline",
            summary={"queue_depth": 0, "note": "owner still works locally"},
            announced_at="2026-06-18T12:09:00Z",
        )
        self.routes.announce_sync_status(
            announcement_id="ann_2",
            node_id="node_worker",
            actor=self.actor("node_worker", "agent_sync", "sess_sync"),
            project_id="prj_main",
            sync_status="degraded",
            summary={"queue_depth": 1, "note": "shared visibility stale"},
            announced_at="2026-06-18T12:09:30Z",
        )
        summary = self.routes.project_sync_summary("prj_main")
        self.assertTrue(summary["degraded"])
        self.assertEqual(summary["owner_node_id"], "node_owner")
        self.assertEqual(summary["coordinator_authority"], "non_authoritative")
        self.assertEqual(summary["canonical_write_path"], "owner_node_local")
        self.assertEqual([row["sync_status"] for row in summary["node_statuses"]], ["offline", "degraded"])

    def test_sync_announcement_requires_reporting_node_actor_and_project_access(self) -> None:
        with self.assertRaises(RouteValidationError):
            self.routes.announce_sync_status(
                announcement_id="ann_bad_reporter",
                node_id="node_owner",
                actor=self.actor("node_worker", "agent_1", "sess_1"),
                project_id="prj_main",
                sync_status="healthy",
                summary={"queue_depth": 0},
                announced_at="2026-06-18T12:09:00Z",
            )

    def test_routed_mutation_rejects_enrolled_but_unauthorized_node(self) -> None:
        with self.assertRaises(RouteValidationError):
            self.routes.submit_proposal(
                route_id="rte_unauthorized",
                destination_project_id="prj_main",
                actor=self.actor("node_observer", "agent_observer", "sess_observer"),
                request_kind="task_transition",
                justification=JustificationPayload(
                    summary="Unauthorized proposal",
                    evidence_refs=("artifact://evidence/unauthorized",),
                    expected_impact="Should be rejected",
                ),
                created_at="2026-06-18T12:10:00Z",
            )

    def test_coordinator_surface_rejects_unauthorized_route_request(self) -> None:
        with self.assertRaises(SurfaceError):
            self.coordinator.route_request(
                route_id="rte_surface_unauthorized",
                destination_project_id="prj_main",
                actor=self.actor("node_observer", "agent_observer", "sess_observer"),
                request_kind="tasks.transition",
                justification=JustificationPayload(
                    summary="Unauthorized surface proposal",
                    evidence_refs=("artifact://evidence/surface-unauthorized",),
                    expected_impact="Should be rejected",
                ),
                created_at="2026-06-18T12:10:30Z",
            )
        with self.assertRaises(RouteValidationError):
            self.routes.announce_sync_status(
                announcement_id="ann_bad_scope",
                node_id="node_worker",
                actor=self.actor("node_worker", "agent_1", "sess_1"),
                project_id="prj_other",
                sync_status="healthy",
                summary={"queue_depth": 0},
                announced_at="2026-06-18T12:09:30Z",
            )

    def test_released_claim_does_not_grant_ongoing_project_access(self) -> None:
        worker = self.actor("node_worker", "agent_worker", "sess_claim_access")
        self.claims.claim_task(
            claim_id="clm_access",
            project_id="prj_main",
            task_id="tsk_access",
            actor=worker,
            plan="Temporary access",
            lease_started_at="2026-06-18T12:09:00Z",
            lease_expires_at="2026-06-18T12:14:00Z",
        )
        self.assertEqual(self.coordinator.sync_status(project_id="prj_main", actor=worker)["status"], "ok")
        self.claims.release_claim(claim_id="clm_access", actor=worker)
        with self.assertRaises(SurfaceError) as ctx:
            self.coordinator.sync_status(project_id="prj_main", actor=worker)
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_resolved_route_does_not_grant_ongoing_project_access(self) -> None:
        worker = self.actor("node_worker", "agent_worker", "sess_route_access")
        self.claims.claim_task(
            claim_id="clm_route_access_window",
            project_id="prj_main",
            task_id="tsk_route_access_window",
            actor=worker,
            plan="Temporary project access for routed request",
            lease_started_at="2026-06-18T12:09:00Z",
            lease_expires_at="2026-06-18T12:14:00Z",
        )
        route = self.coordinator.route_request(
            route_id="rte_access_window",
            destination_project_id="prj_main",
            actor=worker,
            request_kind="tasks.transition",
            justification=JustificationPayload(
                summary="Need owner review",
                evidence_refs=("artifact://evidence/route-access",),
                expected_impact="Allow pending route visibility only",
            ),
            created_at="2026-06-18T12:10:00Z",
        )
        self.assertEqual(route["status"], "proposal_emitted")
        self.claims.release_claim(claim_id="clm_route_access_window", actor=worker)

        self.assertEqual(self.coordinator.sync_status(project_id="prj_main", actor=worker)["status"], "ok")

        self.routes.owner_decision(
            route_id="rte_access_window",
            owner_actor=self.actor("node_owner", "agent_owner", "sess_owner_route_access"),
            accept=False,
        )

        with self.assertRaises(SurfaceError) as ctx:
            self.coordinator.sync_status(project_id="prj_main", actor=worker)
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
