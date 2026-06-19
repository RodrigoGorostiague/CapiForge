import json
import unittest

from runtime.node.index import NodeIndexBuilder
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import CrossProjectGuardError, NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload
from runtime.shared.ids import ActorIdentity


class NodeRuntimeIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.store = NodeStore.from_schema()
        self.addCleanup(self.store.close)
        self.store.create_workspace("ws_1", "workspace://ws_1", "Workspace")
        self.store.upsert_project("prj_main", "ws_1", "node_owner", "project://prj_main", "Main")
        self.store.upsert_project("prj_linked", "ws_1", "node_linked_owner", "project://prj_linked", "Linked")
        self.store.create_audit("aud_main", "prj_main", "published", "Audit", "body")
        self.store.create_audit("aud_linked", "prj_linked", "published", "Linked Audit", "body")
        self.store.create_audit("aud_closed", "prj_main", "closed", "Closed", "body")
        self.store.create_task("tsk_ready_a", "prj_main", "aud_main", "ready", "critical", "low", "low", "fix", "Critical ready")
        self.store.create_task("tsk_ready_b", "prj_main", "aud_main", "ready", "medium", "low", "low", "fix", "Normal ready")
        self.store.create_task("tsk_blocked", "prj_main", "aud_main", "blocked", "high", "low", "low", "fix", "Blocked", blocked_reason="waiting", blocked_evidence="artifact://1", blocked_next_step="unblock")
        self.store.create_task("tsk_done", "prj_main", "aud_main", "done", "low", "low", "low", "doc", "Done", done_result="done", done_artifacts="artifact://1", done_references="ref://1", done_expected_impact="impact")
        self.store.create_task("tsk_claimed", "prj_main", "aud_main", "claimed", "high", "low", "low", "ops", "Claimed", active_claim_session_id="sess-expired")
        self.store.cache_claim("tsk_claimed", "clm_1", "active", "2026-06-18T12:00:00Z", "node_owner", "agent_1", "sess-expired", "plan")
        self.store.add_artifact_ref("art_1", "prj_main", "artifact://main/1", "summary", task_id="tsk_done", audit_id="aud_main")
        self.store.add_local_document("doc_1", "prj_main", "/tmp/doc.md", task_id="tsk_done")
        self.store.approve_project_link("prj_main", "prj_linked", "human_1")
        self.store.approve_project_link("prj_linked", "prj_main", "human_1")

    def test_deterministic_traversal_builds_entrypoint_indexes(self) -> None:
        result = NodeIndexBuilder(self.store).build_project_entrypoint("prj_main", "2026-06-18T12:10:00Z")
        self.assertEqual([task["task_id"] for task in result["indexes"]["ready"]], ["tsk_ready_a", "tsk_ready_b"])
        self.assertEqual([task["task_id"] for task in result["indexes"]["blocked"]], ["tsk_blocked"])
        self.assertEqual([task["task_id"] for task in result["indexes"]["done"]], ["tsk_done"])
        self.assertEqual([task["task_id"] for task in result["indexes"]["critical"]], ["tsk_ready_a"])
        self.assertEqual([task["task_id"] for task in result["indexes"]["expired_claim"]], ["tsk_claimed"])
        stored = self.store.get_project_entrypoint("prj_main")
        summary = json.loads(stored["summary_json"])
        self.assertEqual(summary["owner_node_id"], "node_owner")
        self.assertEqual([project["project_id"] for project in summary["linked_projects"]], ["prj_linked"])
        self.assertEqual([audit["audit_id"] for audit in summary["active_audits"]], ["aud_main"])

    def test_cross_project_guards_route_non_owner_mutations(self) -> None:
        self.store.create_task("tsk_linked", "prj_linked", "aud_linked", "ready", "high", "low", "low", "feature", "Linked ready")
        router = NodeRouter(self.store)
        actor = ActorIdentity(node_id="node_remote", agent_id="agent_1", session_id="sess_1")
        payload = JustificationPayload(summary="need linked work", evidence_refs=("artifact://main/1",), expected_impact="sync")
        with self.assertRaises(CrossProjectGuardError):
            router.submit_task_mutation("prj_linked", "tsk_linked", "mut_blocked", actor, payload, "blocked", source_project_id="prj_main")
        self.store.record_cross_project_approval("apr_1", "prj_main", "prj_linked", "2026-06-18T11:59:00Z", "human_1")
        proposal = router.submit_task_mutation("prj_linked", "tsk_linked", "mut_proposal", actor, payload, "blocked", source_project_id="prj_main")
        self.assertEqual((proposal.status, proposal.owner_node_id, proposal.authority_mode), ("proposal_emitted", "node_linked_owner", "proposal"))
        accepted = router.accept_proposal("mut_proposal", "mut_accept", ActorIdentity(node_id="node_linked_owner", agent_id="agent_owner", session_id="sess_owner"))
        self.assertEqual((accepted.status, accepted.authority_mode), ("accepted", "canonical"))

    def test_offline_owner_reads_and_writes_stay_local(self) -> None:
        router = NodeRouter(self.store)
        payload = JustificationPayload(summary="owner update", evidence_refs=("artifact://main/1",), expected_impact="advance")
        decision = router.submit_task_mutation("prj_main", "tsk_ready_b", "mut_owner", ActorIdentity(node_id="node_owner", agent_id="agent_owner", session_id="sess_owner"), payload, "in_progress")
        self.assertEqual((decision.status, decision.authority_mode), ("accepted", "canonical"))
        self.assertEqual(router.resolve_owner_node_id("prj_main"), "node_owner")
        entrypoint = NodeIndexBuilder(self.store).build_project_entrypoint("prj_main", "2026-06-18T12:10:00Z")
        self.assertEqual(entrypoint["entrypoint"]["owner_node_id"], "node_owner")

    def test_local_read_helper_returns_ephemeral_entrypoint(self) -> None:
        surface = NodeMCPSurface(store=self.store, router=NodeRouter(self.store), local_node_id="node_owner")

        result = surface.project_entrypoint_get_local(project_id="prj_main", as_of="2026-06-18T12:10:00Z")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["data"]["project_id"], "prj_main")
        self.assertEqual(result["data"]["owner_node_id"], "node_owner")
        self.assertEqual(result["data"]["generated_at"], "2026-06-18T12:10:00Z")
        self.assertIsNone(self.store.get_project_entrypoint("prj_main"))

    def test_sync_export_excludes_long_form_documents_and_retains_metadata(self) -> None:
        earlier = self.store.export_sync_payload("prj_main", as_of="2026-06-18T12:10:00Z")
        later = self.store.export_sync_payload("prj_main", as_of="2026-08-18T12:10:00Z")
        self.assertEqual([artifact["artifact_ref_id"] for artifact in earlier["artifact_refs"]], ["art_1"])
        self.assertEqual(earlier["artifact_refs"], later["artifact_refs"])
        self.assertNotIn("local_documents", earlier)


if __name__ == "__main__":
    unittest.main()
