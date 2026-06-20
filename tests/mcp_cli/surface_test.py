import sqlite3
import unittest
import json
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


class MCPSurfaceIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = NodeStore.from_schema()
        self.addCleanup(self.store.close)
        self.store.create_workspace("ws_1", "workspace://ws_1", "Workspace")
        self.store.upsert_project("prj_main", "ws_1", "node_owner", "project://prj_main", "Main")
        self.store.upsert_project("prj_linked", "ws_1", "node_linked_owner", "project://prj_linked", "Linked")
        self.store.create_audit("aud_main", "prj_main", "published", "Audit", "body")
        self.store.create_audit("aud_closed", "prj_main", "closed", "Closed", "sealed")
        self.store.create_audit("aud_linked", "prj_linked", "published", "Linked", "body")
        self.store.create_task("tsk_ready", "prj_main", "aud_main", "ready", "high", "low", "low", "fix", "Ready task")
        self.store.create_task("tsk_linked", "prj_linked", "aud_linked", "ready", "high", "low", "low", "feature", "Linked task")
        self.store.approve_project_link("prj_main", "prj_linked", "human_1")
        self.store.approve_project_link("prj_linked", "prj_main", "human_1")
        self.store.record_cross_project_approval("apr_1", "prj_main", "prj_linked", "2026-06-18T12:00:00Z", "human_1")

        self.coordinator_db = sqlite3.connect(":memory:")
        self.addCleanup(self.coordinator_db.close)
        self.coordinator_db.execute("PRAGMA foreign_keys = ON")
        self.coordinator_db.executescript(Path("storage/coordinator-schema.sql").read_text())
        self.enrollment = EnrollmentRegistry(self.coordinator_db)
        self.claims = ClaimRegistry(self.coordinator_db)
        self.routes = MutationRouteRegistry(self.coordinator_db)
        self.coordinator = CoordinatorMCPSurface(self.routes, enrollment=self.enrollment)

        nodes = (
            ("node_owner", "Owner", "signed:owner", "2026-06-18T12:01:00Z"),
            ("node_remote", "Remote", "signed:remote", "2026-06-18T12:01:30Z"),
            ("node_linked_owner", "Linked Owner", "signed:linked-owner", "2026-06-18T12:02:00Z"),
            ("node_observer", "Observer", "signed:observer", "2026-06-18T12:02:30Z"),
        )
        self.node_fingerprints = {node_id: fingerprint for node_id, _display, fingerprint, _enrolled_at in nodes}
        for node_id, display, fingerprint, _enrolled_at in nodes:
            self.enrollment.invite_node(node_id=node_id, display_name=display, invitation_fingerprint=fingerprint, invited_by_human_actor_id="human_1", issued_at="2026-06-18T12:00:00Z")
        for node_id, _display, fingerprint, enrolled_at in nodes:
            self.enrollment.accept_invitation(node_id=node_id, invitation_fingerprint=fingerprint, enrolled_at=enrolled_at)
        admin = self.actor("node_owner", "human_operator", "sess_admin", human_actor_id="human_1")
        self.enrollment.assign_owner(project_id="prj_main", owner_node_id="node_owner", assigned_by_human_actor_id="human_1", assigned_at="2026-06-18T12:03:00Z", authority=admin)
        self.enrollment.assign_owner(project_id="prj_linked", owner_node_id="node_linked_owner", assigned_by_human_actor_id="human_1", assigned_at="2026-06-18T12:03:30Z", authority=admin)
        self.coordinator_db.execute(
            "INSERT INTO notice_approvals (approval_id, source_project_id, target_project_id, notice_recorded_at, approved_by_human_actor_id, approval_status, routed_to_owner_node_id) VALUES (?,?,?,?,?,?,?)",
            ("notice_1", "prj_main", "prj_linked", "2026-06-18T12:00:00Z", "human_1", "approved", "node_linked_owner"),
        )

        router = NodeRouter(self.store)
        self.owner_surface = NodeMCPSurface(store=self.store, router=router, claims=self.claims, coordinator=self.coordinator, enrollment=self.enrollment, local_node_id="node_owner")
        self.remote_surface = NodeMCPSurface(store=self.store, router=router, claims=self.claims, coordinator=self.coordinator, enrollment=self.enrollment, local_node_id="node_remote")
        self.linked_owner_surface = NodeMCPSurface(store=self.store, router=router, claims=self.claims, coordinator=self.coordinator, enrollment=self.enrollment, local_node_id="node_linked_owner")
        self.observer_surface = NodeMCPSurface(store=self.store, router=router, claims=self.claims, coordinator=self.coordinator, enrollment=self.enrollment, local_node_id="node_observer")
        self.owner_surface_degraded = NodeMCPSurface(store=self.store, router=router, claims=self.claims, coordinator=None, enrollment=self.enrollment, local_node_id="node_owner")
        self.observer_surface_degraded = NodeMCPSurface(store=self.store, router=router, claims=self.claims, coordinator=None, enrollment=self.enrollment, local_node_id="node_observer")
        self.surface = self.owner_surface

    def actor(self, node_id: str, agent_id: str, session_id: str, *, human_actor_id: str | None = None, invitation_fingerprint: str | None = None, node_proof: str | None = None) -> ActorIdentity:
        fingerprint = invitation_fingerprint or self.node_fingerprints[node_id]
        proof = node_proof if node_proof is not None else derive_node_proof(
            node_id=node_id,
            agent_id=agent_id,
            session_id=session_id,
            invitation_fingerprint=fingerprint,
        )
        return ActorIdentity(node_id=node_id, agent_id=agent_id, session_id=session_id, human_actor_id=human_actor_id, node_proof=proof)

    def test_transition_requires_justification_metadata(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.tasks_transition(
                project_id="prj_main",
                task_id="tsk_ready",
                mutation_id="mut_1",
                actor=actor,
                requested_state="blocked",
                justification=JustificationPayload(summary="", evidence_refs=(), expected_impact=""),
                metadata={"blocked_reason": "waiting", "blocked_evidence": "artifact://1", "blocked_next_step": "retry"},
            )
        self.assertEqual(ctx.exception.code, "JUSTIFICATION_REQUIRED")

    def test_closed_audit_rejects_direct_content_mutation(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.audit_content_update(
                audit_id="aud_closed",
                content="rewrite",
                actor=self.actor("node_owner", "human_operator", "sess_human_closed", human_actor_id="human_1"),
            )
        self.assertEqual(ctx.exception.code, "AUDIT_CLOSED_IMMUTABLE")

    def test_audit_content_update_requires_owner_human_actor(self) -> None:
        with self.assertRaises(SurfaceError) as ai_ctx:
            self.surface.audit_content_update(
                audit_id="aud_main",
                content="rewrite",
                actor=self.actor("node_owner", "agent_owner", "sess_ai"),
            )
        self.assertEqual(ai_ctx.exception.code, "INVALID_TASK_STATE")

        with self.assertRaises(SurfaceError) as non_owner_ctx:
            self.remote_surface.audit_content_update(
                audit_id="aud_main",
                content="rewrite",
                actor=self.actor("node_remote", "human_remote", "sess_remote_human", human_actor_id="human_1"),
            )
        self.assertEqual(non_owner_ctx.exception.code, "NON_OWNER_CANONICAL_WRITE")

    def test_owner_human_can_update_open_audit_content(self) -> None:
        updated = self.surface.audit_content_update(
            audit_id="aud_main",
            content="updated body",
            actor=self.actor("node_owner", "human_operator", "sess_human_update", human_actor_id="human_1"),
        )
        self.assertEqual(updated["status"], "accepted")
        self.assertEqual(self.store.get_audit("aud_main")["content"], "updated body")

    def test_cross_project_request_routes_after_recorded_approval(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        response = self.owner_surface.cross_project_request(
            route_id="route_1",
            source_project_id="prj_main",
            destination_project_id="prj_linked",
            actor=actor,
            justification=JustificationPayload(
                summary="Need linked project follow-up",
                evidence_refs=("artifact://main/1",),
                expected_impact="Route approved linked work",
            ),
            created_at="2026-06-18T12:05:00Z",
        )
        self.assertEqual(response["status"], "routed")
        self.assertEqual(response["data"]["destination_owner_node_id"], "node_linked_owner")
        pending = self.coordinator.sync_status(project_id="prj_linked", actor=actor)
        self.assertEqual(pending["data"]["pending_routes"], 1)
        accepted = self.routes.owner_decision(
            route_id="route_1",
            owner_actor=self.actor("node_linked_owner", "agent_owner", "sess_linked_owner"),
            accept=True,
        )
        self.assertEqual(accepted.status, "accepted")
        applied = self.linked_owner_surface.apply_accepted_cross_project_request(
            route_id="route_1",
            project_id="prj_linked",
            audit_id="aud_linked",
            task_id="tsk_linked_followup",
            mutation_id="mut_linked_followup",
            actor=self.actor("node_linked_owner", "agent_owner", "sess_linked_owner"),
            priority="medium",
            effort="low",
            risk="low",
            task_type="feature",
            description="Follow up approved cross-project work",
            execution_context={"requested_by": "prj_main"},
        )
        self.assertEqual(applied["status"], "accepted")
        self.assertEqual(self.store.get_task("tsk_linked_followup")["project_id"], "prj_linked")

    def test_cross_project_request_requires_coordinator_approval_record(self) -> None:
        self.coordinator_db.execute("DELETE FROM notice_approvals WHERE source_project_id = ? AND target_project_id = ?", ("prj_main", "prj_linked"))
        with self.assertRaises(SurfaceError) as ctx:
            self.owner_surface.cross_project_request(
                route_id="route_missing_notice",
                source_project_id="prj_main",
                destination_project_id="prj_linked",
                actor=self.actor("node_owner", "agent_owner", "sess_owner_missing_notice"),
                justification=JustificationPayload(
                    summary="Local approval only should not be enough",
                    evidence_refs=("artifact://main/local-only",),
                    expected_impact="Reject coordinator route",
                ),
                created_at="2026-06-18T12:05:30Z",
            )
        self.assertEqual(ctx.exception.code, "CROSS_PROJECT_APPROVAL_REQUIRED")

    def test_create_task_from_audit_preserves_origin_audit(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        response = self.surface.tasks_create_from_audit(
            task_id="tsk_from_audit",
            project_id="prj_main",
            audit_id="aud_main",
            mutation_id="mut_create",
            actor=actor,
            priority="high",
            effort="medium",
            risk="low",
            task_type="audit_followup",
            description="Follow up the audit finding",
            justification=JustificationPayload(
                summary="Audit finding requires action",
                evidence_refs=("artifact://audit/1",),
                expected_impact="Track follow-up work",
            ),
            execution_context={"steps": ["reproduce", "fix"]},
        )
        self.assertEqual(response["status"], "accepted")
        stored = self.store.get_task("tsk_from_audit")
        self.assertEqual(stored["origin_audit_id"], "aud_main")
        self.assertEqual(stored["state"], "proposed")

    def test_create_task_from_audit_persists_lifecycle_key_metadata(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner_lifecycle")
        response = self.surface.tasks_create_from_audit(
            task_id="tsk_lifecycle_created",
            project_id="prj_main",
            audit_id="aud_main",
            mutation_id="mut_lifecycle_create",
            actor=actor,
            priority="high",
            effort="medium",
            risk="low",
            task_type="ops",
            description="Lifecycle-created task",
            justification=JustificationPayload(
                summary="Lifecycle wrapper created a task",
                evidence_refs=("lifecycle://agent-capiforge-auto-task-lifecycle",),
                expected_impact="Allow deterministic task reuse",
            ),
            execution_context={"project_id": "prj_main", "lifecycle_key": "lifecycle://agent-capiforge-auto-task-lifecycle"},
            initial_state="ready",
            lifecycle_key="lifecycle://agent-capiforge-auto-task-lifecycle",
        )
        self.assertEqual(response["status"], "accepted")
        stored = self.store.get_task("tsk_lifecycle_created")
        self.assertEqual(stored["lifecycle_key"], "lifecycle://agent-capiforge-auto-task-lifecycle")
        mutation = self.store.get_task_mutation("mut_lifecycle_create")
        self.assertIsNotNone(mutation)
        payload = json.loads(mutation["justification_json"])
        self.assertEqual(payload["lifecycle_key"], "lifecycle://agent-capiforge-auto-task-lifecycle")
        self.assertEqual(payload["lifecycle_creator"]["session_id"], "sess_owner_lifecycle")

    def test_transition_to_ready_requires_readiness_inputs(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        self.surface.tasks_create_from_audit(
            task_id="tsk_proposed",
            project_id="prj_main",
            audit_id="aud_main",
            mutation_id="mut_create_ready",
            actor=actor,
            priority="medium",
            effort="low",
            risk="low",
            task_type="fix",
            description="Ready candidate",
            justification=JustificationPayload(
                summary="Enough evidence exists",
                evidence_refs=("artifact://audit/2",),
                expected_impact="Promote to execution-ready",
            ),
            execution_context={"owner": "team-a", "inputs": ["artifact://audit/2"]},
        )
        response = self.surface.tasks_transition(
            project_id="prj_main",
            task_id="tsk_proposed",
            mutation_id="mut_ready",
            actor=actor,
            requested_state="ready",
            justification=JustificationPayload(
                summary="Ready for execution",
                evidence_refs=("artifact://audit/2",),
                expected_impact="Allow an agent to claim work",
            ),
            metadata={"conflict_status": "clear"},
        )
        self.assertEqual(response["status"], "accepted")
        self.assertEqual(self.store.get_task("tsk_proposed")["state"], "ready")

    def test_human_override_reopens_finished_task(self) -> None:
        actor = self.actor("node_owner", "human_operator", "sess_human", human_actor_id="human_1")
        self.surface.tasks_create_from_audit(
            task_id="tsk_reopen",
            project_id="prj_main",
            audit_id="aud_main",
            mutation_id="mut_seed_reopen",
            actor=self.actor("node_owner", "agent_owner", "sess_owner"),
            priority="high",
            effort="low",
            risk="low",
            task_type="fix",
            description="Task to reopen",
            justification=JustificationPayload(
                summary="Need a reopenable task",
                evidence_refs=("artifact://main/reopen",),
                expected_impact="Exercise override flow",
            ),
            execution_context={"playbook": "runbook"},
            initial_state="ready",
        )
        response = self.surface.tasks_override(
            project_id="prj_main",
            task_id="tsk_reopen",
            mutation_id="mut_done",
            actor=actor,
            requested_state="done",
            metadata={
                "reason": "Confirm closure",
                "done_result": "completed",
                "done_artifacts": "artifact://main/2",
                "done_references": "ref://main/2",
                "done_expected_impact": "Close the item",
            },
        )
        self.assertEqual(response["status"], "accepted")
        reopened = self.surface.tasks_override(
            project_id="prj_main",
            task_id="tsk_reopen",
            mutation_id="mut_reopen",
            actor=actor,
            requested_state="ready",
            metadata={"reason": "Need another pass", "conflict_status": "clear"},
        )
        self.assertEqual(reopened["status"], "accepted")
        reopened_task = self.store.get_task("tsk_reopen")
        self.assertEqual(reopened_task["state"], "ready")
        self.assertIsNone(reopened_task["done_result"])

    def test_release_clears_active_execution_state(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        claimed = self.surface.tasks_claim(
            claim_id="clm_release",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=actor,
            plan="Take the task",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:11:00Z",
        )
        self.assertEqual(claimed["status"], "claimed")
        released = self.surface.tasks_release(
            project_id="prj_main",
            task_id="tsk_ready",
            claim_id="clm_release",
            actor=actor,
        )
        self.assertEqual(released["status"], "accepted")
        self.assertEqual(self.store.get_task("tsk_ready")["state"], "ready")

    def test_transition_to_in_progress_requires_real_active_claim(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.tasks_transition(
                project_id="prj_main",
                task_id="tsk_ready",
                mutation_id="mut_claim_guard",
                actor=actor,
                requested_state="in_progress",
                justification=JustificationPayload(
                    summary="Start execution",
                    evidence_refs=("artifact://main/3",),
                    expected_impact="Move task into active work",
                ),
                metadata={"active_claim_session_id": actor.session_id, "as_of": "2026-06-18T12:07:00Z"},
            )
        self.assertEqual(ctx.exception.code, "INVALID_TASK_STATE")

    def test_expired_claim_demotes_task_out_of_active_execution(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        self.surface.tasks_claim(
            claim_id="clm_expire",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=actor,
            plan="Active work",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:07:00Z",
        )
        self.surface.tasks_transition(
            project_id="prj_main",
            task_id="tsk_ready",
            mutation_id="mut_progress",
            actor=actor,
            requested_state="in_progress",
            justification=JustificationPayload(
                summary="Execution started",
                evidence_refs=("artifact://main/5",),
                expected_impact="Track active work",
            ),
            metadata={"active_claim_session_id": actor.session_id, "as_of": "2026-06-18T12:06:30Z"},
        )
        with self.assertRaises(SurfaceError):
            self.surface.tasks_transition(
                project_id="prj_main",
                task_id="tsk_ready",
                mutation_id="mut_stale_progress",
                actor=actor,
                requested_state="in_progress",
                justification=JustificationPayload(
                    summary="Keep working",
                    evidence_refs=("artifact://main/5",),
                    expected_impact="Continue active work",
                ),
                metadata={"active_claim_session_id": actor.session_id, "as_of": "2026-06-18T12:08:00Z"},
            )
        self.assertEqual(self.store.get_task("tsk_ready")["state"], "ready")

    def test_done_transition_persists_closeout_metadata_with_active_claim(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_done")
        self.surface.tasks_claim(
            claim_id="clm_done",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=actor,
            plan="Complete the task",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:11:00Z",
        )
        self.surface.tasks_transition(
            project_id="prj_main",
            task_id="tsk_ready",
            mutation_id="mut_done_finish",
            actor=actor,
            requested_state="done",
            justification=JustificationPayload(
                summary="Finished the lifecycle task",
                evidence_refs=("artifact://main/done",),
                expected_impact="Close the task with deterministic metadata",
            ),
            metadata={
                "done_result": "completed",
                "done_artifacts": "artifact://main/done",
                "done_references": "ref://main/done",
                "done_expected_impact": "Ship the completed work",
            },
        )
        task = self.store.get_task("tsk_ready")
        self.assertEqual(task["state"], "done")
        self.assertEqual(task["done_result"], "completed")

    def test_blocked_transition_persists_closeout_metadata_with_active_claim(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_blocked")
        self.surface.tasks_claim(
            claim_id="clm_blocked_finish",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=actor,
            plan="Block the task",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:11:00Z",
        )
        self.surface.tasks_transition(
            project_id="prj_main",
            task_id="tsk_ready",
            mutation_id="mut_blocked_finish",
            actor=actor,
            requested_state="blocked",
            justification=JustificationPayload(
                summary="Blocked during lifecycle closeout",
                evidence_refs=("artifact://main/blocked",),
                expected_impact="Capture the blocking dependency",
            ),
            metadata={
                "blocked_reason": "awaiting dependency",
                "blocked_evidence": "artifact://main/blocked",
                "blocked_next_step": "Retry once dependency is resolved",
            },
        )
        task = self.store.get_task("tsk_ready")
        self.assertEqual(task["state"], "blocked")
        self.assertEqual(task["blocked_reason"], "awaiting dependency")

    def test_expired_claim_rejects_further_active_execution_and_demotes_task(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_done_expired")
        self.surface.tasks_claim(
            claim_id="clm_done_expired",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=actor,
            plan="Start then expire",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:07:00Z",
        )
        self.surface.tasks_transition(
            project_id="prj_main",
            task_id="tsk_ready",
            mutation_id="mut_done_progress",
            actor=actor,
            requested_state="in_progress",
            justification=JustificationPayload(
                summary="Execution started",
                evidence_refs=("artifact://main/done-expired",),
                expected_impact="Track active work before closeout",
            ),
            metadata={"active_claim_session_id": actor.session_id, "as_of": "2026-06-18T12:06:30Z"},
        )
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.tasks_transition(
                project_id="prj_main",
                task_id="tsk_ready",
                mutation_id="mut_done_expired_finish",
                actor=actor,
                requested_state="in_progress",
                justification=JustificationPayload(
                    summary="Attempt stale closeout",
                    evidence_refs=("artifact://main/done-expired",),
                    expected_impact="Reject stale ownership",
                ),
                metadata={"active_claim_session_id": actor.session_id, "as_of": "2026-06-18T12:08:00Z"},
            )
        self.assertEqual(ctx.exception.code, "INVALID_TASK_STATE")
        self.assertEqual(self.store.get_task("tsk_ready")["state"], "ready")

    def test_non_owner_transition_signals_owner_acceptance(self) -> None:
        actor = self.actor("node_linked_owner", "agent_linked", "sess_linked")
        self.linked_owner_surface.tasks_claim(
            claim_id="clm_linked_transition",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=actor,
            plan="Establish authorized participation before proposing",
            lease_started_at="2026-06-18T12:05:00Z",
            lease_expires_at="2026-06-18T12:10:00Z",
        )
        response = self.linked_owner_surface.tasks_transition(
            project_id="prj_main",
            task_id="tsk_ready",
            mutation_id="route_transition",
            actor=actor,
            requested_state="blocked",
            justification=JustificationPayload(
                summary="Need owner to block work",
                evidence_refs=("artifact://main/4",),
                expected_impact="Queue owner decision",
            ),
            metadata={"blocked_reason": "awaiting dependency", "blocked_evidence": "artifact://main/4", "blocked_next_step": "wait"},
        )
        self.assertEqual(response["status"], "proposal_emitted")
        self.assertEqual(response["data"]["acceptance_signal"], "ROUTE_OWNER_ACCEPTANCE_REQUIRED")
        self.assertEqual(self.linked_owner_surface.sync_status(project_id="prj_main", actor=actor)["data"]["pending_routes"], 1)

    def test_claim_requires_matching_project_and_ready_state(self) -> None:
        actor = self.actor("node_owner", "agent_owner", "sess_owner")
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.tasks_claim(
                claim_id="clm_wrong_project",
                project_id="prj_linked",
                task_id="tsk_ready",
                actor=actor,
                plan="Wrong project",
                lease_started_at="2026-06-18T12:06:00Z",
                lease_expires_at="2026-06-18T12:11:00Z",
            )
        self.assertEqual(ctx.exception.code, "INVALID_TASK_STATE")

    def test_release_rejects_wrong_claim_mapping(self) -> None:
        owner = self.actor("node_owner", "agent_owner", "sess_owner")
        self.surface.tasks_claim(
            claim_id="clm_real",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=owner,
            plan="Claim real task",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:11:00Z",
        )
        self.store.create_task("tsk_second", "prj_main", "aud_main", "ready", "medium", "low", "low", "fix", "Second task")
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.tasks_release(project_id="prj_main", task_id="tsk_second", claim_id="clm_real", actor=owner)
        self.assertEqual(ctx.exception.code, "INVALID_TASK_STATE")
        self.assertEqual(self.store.get_task("tsk_ready")["state"], "claimed")

    def test_read_surfaces_require_trusted_enrolled_actor(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.project_entrypoint_get(project_id="prj_main", as_of="2026-06-18T12:10:00Z")
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_workspace_get_returns_workspace_shape_for_authorized_local_actor(self) -> None:
        response = self.owner_surface.workspace_get(
            workspace_id="ws_1",
            actor=self.actor("node_owner", "agent_owner", "sess_workspace_owner"),
        )
        self.assertEqual(response["status"], "ok")
        self.assertEqual(response["data"]["workspace_id"], "ws_1")
        self.assertEqual(response["data"]["canonical_link"], "workspace://ws_1")
        self.assertEqual(response["data"]["name"], "Workspace")
        self.assertEqual(
            [project["project_id"] for project in response["data"]["projects"]],
            ["prj_linked", "prj_main"],
        )

    def test_workspace_get_rejects_unknown_workspace(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.owner_surface.workspace_get(
                workspace_id="ws_missing",
                actor=self.actor("node_owner", "agent_owner", "sess_workspace_missing"),
            )
        self.assertEqual(ctx.exception.code, "UNKNOWN_RESOURCE")

    def test_workspace_get_filters_projects_to_actor_scope(self) -> None:
        self.store.upsert_project("prj_private", "ws_1", "node_private", "project://prj_private", "Private")

        owner_response = self.owner_surface.workspace_get(
            workspace_id="ws_1",
            actor=self.actor("node_owner", "agent_owner", "sess_workspace_filter_owner"),
        )
        observer_response = self.observer_surface.workspace_get(
            workspace_id="ws_1",
            actor=self.actor("node_observer", "agent_observer", "sess_workspace_filter_observer"),
        )

        self.assertEqual(
            [project["project_id"] for project in owner_response["data"]["projects"]],
            ["prj_linked", "prj_main"],
        )
        self.assertEqual(observer_response["status"], "ok")
        self.assertEqual(observer_response["data"]["workspace_id"], "ws_1")
        self.assertEqual(observer_response["data"]["projects"], [])

    def test_workspace_get_requires_trusted_local_actor_context(self) -> None:
        actors = {
            "missing": None,
            "foreign_local_actor": self.actor("node_remote", "agent_remote", "sess_workspace_remote"),
        }
        for label, actor in actors.items():
            with self.subTest(actor=label):
                with self.assertRaises(SurfaceError) as ctx:
                    self.owner_surface.workspace_get(workspace_id="ws_1", actor=actor)
                self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_claim_rejects_missing_or_forged_node_proof(self) -> None:
        actors = {
            "missing": ActorIdentity(node_id="node_owner", agent_id="agent_owner", session_id="sess_missing", node_proof=None),
            "forged": self.actor("node_owner", "agent_owner", "sess_forged", node_proof="forged-proof"),
        }
        for label, actor in actors.items():
            with self.subTest(proof=label):
                with self.assertRaises(SurfaceError) as ctx:
                    self.surface.tasks_claim(
                        claim_id=f"clm_bad_{label}",
                        project_id="prj_main",
                        task_id="tsk_ready",
                        actor=actor,
                        plan="Should fail",
                        lease_started_at="2026-06-18T12:06:00Z",
                        lease_expires_at="2026-06-18T12:11:00Z",
                    )
                self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_release_rejects_missing_or_forged_node_proof(self) -> None:
        owner = self.actor("node_owner", "agent_owner", "sess_release")
        self.surface.tasks_claim(
            claim_id="clm_release_proof",
            project_id="prj_main",
            task_id="tsk_ready",
            actor=owner,
            plan="Create releasable claim",
            lease_started_at="2026-06-18T12:06:00Z",
            lease_expires_at="2026-06-18T12:11:00Z",
        )
        actors = {
            "missing": ActorIdentity(node_id="node_owner", agent_id="agent_owner", session_id="sess_release", node_proof=None),
            "forged": self.actor("node_owner", "agent_owner", "sess_release", node_proof="forged-proof"),
        }
        for label, actor in actors.items():
            with self.subTest(proof=label):
                with self.assertRaises(SurfaceError) as ctx:
                    self.surface.tasks_release(
                        project_id="prj_main",
                        task_id="tsk_ready",
                        claim_id="clm_release_proof",
                        actor=actor,
                    )
                self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_project_scoped_sync_status_rejects_enrolled_but_unrelated_node(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.coordinator.sync_status(project_id="prj_main", actor=self.actor("node_observer", "agent_observer", "sess_observer"))
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_degraded_sync_status_requires_project_authorization(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.observer_surface_degraded.sync_status(
                project_id="prj_main",
                actor=self.actor("node_observer", "agent_observer", "sess_observer_degraded"),
            )
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_degraded_sync_status_allows_authorized_project_reader(self) -> None:
        response = self.owner_surface_degraded.sync_status(
            project_id="prj_main",
            actor=self.actor("node_owner", "agent_owner", "sess_owner_degraded"),
        )
        self.assertEqual(response["status"], "ok")
        self.assertTrue(response["data"]["degraded"])
        self.assertEqual(response["data"]["project_id"], "prj_main")

    def test_project_entrypoint_rejects_enrolled_but_unrelated_node(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.observer_surface.project_entrypoint_get(
                project_id="prj_main",
                as_of="2026-06-18T12:10:00Z",
                actor=self.actor("node_observer", "agent_observer", "sess_observer"),
            )
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_tasks_list_by_index_rejects_enrolled_but_unrelated_node(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.observer_surface.tasks_list_by_index(
                project_id="prj_main",
                index_name="ready",
                as_of="2026-06-18T12:10:00Z",
                actor=self.actor("node_observer", "agent_observer", "sess_observer"),
            )
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_claim_rejects_enrolled_but_unrelated_node(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.observer_surface.tasks_claim(
                claim_id="clm_observer",
                project_id="prj_main",
                task_id="tsk_ready",
                actor=self.actor("node_observer", "agent_observer", "sess_observer"),
                plan="Should not gain access by claiming",
                lease_started_at="2026-06-18T12:06:00Z",
                lease_expires_at="2026-06-18T12:11:00Z",
            )
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_transition_route_rejects_enrolled_but_unrelated_node(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.observer_surface.tasks_transition(
                project_id="prj_main",
                task_id="tsk_ready",
                mutation_id="route_transition_denied",
                actor=self.actor("node_observer", "agent_observer", "sess_observer"),
                requested_state="blocked",
                justification=JustificationPayload(
                    summary="Unauthorized route attempt",
                    evidence_refs=("artifact://main/unauthorized",),
                    expected_impact="Should be rejected before proposal creation",
                ),
                metadata={"blocked_reason": "none", "blocked_evidence": "artifact://main/unauthorized", "blocked_next_step": "stop"},
            )
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_local_surface_rejects_foreign_node_actor_even_if_enrolled(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.surface.project_entrypoint_get(project_id="prj_main", as_of="2026-06-18T12:10:00Z", actor=self.actor("node_remote", "agent_remote", "sess_remote"))
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")

    def test_rejected_route_does_not_grant_destination_project_reads(self) -> None:
        remote_actor = self.actor("node_remote", "agent_remote", "sess_remote_route_access")
        self.claims.claim_task(
            claim_id="clm_remote_route_access",
            project_id="prj_main",
            task_id="tsk_remote_route_access",
            actor=remote_actor,
            plan="Temporary access before routing",
            lease_started_at="2026-06-18T12:08:00Z",
            lease_expires_at="2026-06-18T12:13:00Z",
        )
        route = self.coordinator.route_request(
            route_id="route_rejected_access",
            destination_project_id="prj_main",
            actor=remote_actor,
            request_kind="tasks.transition",
            justification=JustificationPayload(
                summary="Need owner review",
                evidence_refs=("artifact://remote/rejected-access",),
                expected_impact="Create a pending route only",
            ),
            created_at="2026-06-18T12:09:00Z",
        )
        self.assertEqual(route["status"], "proposal_emitted")
        self.claims.release_claim(claim_id="clm_remote_route_access", actor=remote_actor)
        self.assertEqual(self.coordinator.sync_status(project_id="prj_main", actor=remote_actor)["status"], "ok")

        self.routes.owner_decision(
            route_id="route_rejected_access",
            owner_actor=self.actor("node_owner", "agent_owner", "sess_owner_reject_route_access"),
            accept=False,
        )

        with self.assertRaises(SurfaceError) as ctx:
            self.coordinator.sync_status(project_id="prj_main", actor=remote_actor)
        self.assertEqual(ctx.exception.code, "AUTHORIZATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
