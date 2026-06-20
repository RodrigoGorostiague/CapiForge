import json
import tempfile
import unittest
from pathlib import Path

from runtime.coordinator.claims import ClaimConflictError, ClaimRegistry
from runtime.node.bootstrap import NodeBootstrap
from runtime.node.current import claim_ready_task, renew_task_claim, transition_task
from runtime.node.store import NodeStore
from runtime.shared.ids import ActorIdentity, canonical_id, derive_node_proof


class MultiAgentClaimsIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo_root = Path(self.tempdir.name) / "repo"
        self.repo_root.mkdir()
        self.node_home = self.repo_root / ".capiforge" / "node"
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self.project_id = adopted.adopted_project["project_id"]
        self.bootstrap = bootstrap

        store = NodeStore.from_file(bootstrap.node_db_path)
        self.addCleanup(store.close)
        store.create_audit("aud_multi", self.project_id, "published", "Multi-agent audit", "body")
        store.create_task(
            "tsk_multi",
            self.project_id,
            "aud_multi",
            "ready",
            "high",
            "low",
            "low",
            "feature",
            "Multi-agent task",
        )
        store.db.commit()

    def _actor(self, store: NodeStore, *, agent_id: str, session_id: str, node_id: str) -> ActorIdentity:
        fingerprint = store.ensure_local_node_actor(node_id=node_id)
        return ActorIdentity(
            node_id=node_id,
            agent_id=agent_id,
            session_id=session_id,
            node_proof=derive_node_proof(
                node_id=node_id,
                agent_id=agent_id,
                session_id=session_id,
                invitation_fingerprint=fingerprint,
            ),
        )

    def test_two_sessions_cannot_claim_same_ready_task(self) -> None:
        first = claim_ready_task(
            self.bootstrap,
            task_id="tsk_multi",
            plan="Agent A work",
            lease_minutes=5,
            lock_timeout_seconds=30.0,
            recover_stale_lock=False,
            agent_id="agent-a",
            session_id="session-a",
        )
        self.assertEqual(first["state"], "claimed")

        with self.assertRaises(Exception):
            claim_ready_task(
                self.bootstrap,
                task_id="tsk_multi",
                plan="Agent B work",
                lease_minutes=5,
                lock_timeout_seconds=30.0,
                recover_stale_lock=False,
                agent_id="agent-b",
                session_id="session-b",
            )

    def test_claim_renew_extends_lease_for_same_session(self) -> None:
        claimed = claim_ready_task(
            self.bootstrap,
            task_id="tsk_multi",
            plan="Long work",
            lease_minutes=5,
            lock_timeout_seconds=30.0,
            recover_stale_lock=False,
            agent_id="agent-a",
            session_id="session-a",
        )
        renewed = renew_task_claim(
            self.bootstrap,
            task_id="tsk_multi",
            claim_id=claimed["claim_id"],
            lease_minutes=10,
            lock_timeout_seconds=30.0,
            recover_stale_lock=False,
            agent_id="agent-a",
            session_id="session-a",
        )
        self.assertEqual(renewed["status"], "renewed")
        self.assertGreater(renewed["lease_expires_at"], claimed["lease_expires_at"])

    def test_transition_requires_matching_claim_session(self) -> None:
        claimed = claim_ready_task(
            self.bootstrap,
            task_id="tsk_multi",
            plan="Session-bound work",
            lease_minutes=5,
            lock_timeout_seconds=30.0,
            recover_stale_lock=False,
            agent_id="agent-a",
            session_id="session-a",
        )
        with self.assertRaises(Exception):
            transition_task(
                self.bootstrap,
                task_id="tsk_multi",
                requested_state="in_progress",
                summary="Wrong session",
                agent_id="agent-b",
                session_id="session-b",
            )
        started = transition_task(
            self.bootstrap,
            task_id="tsk_multi",
            requested_state="in_progress",
            summary="Matching session",
            agent_id="agent-a",
            session_id="session-a",
        )
        self.assertEqual(started["state"], "in_progress")
        self.assertEqual(claimed["task_id"], "tsk_multi")


if __name__ == "__main__":
    unittest.main()
