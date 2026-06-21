import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from runtime.coordinator.claims import ClaimRegistry
from runtime.node.bootstrap import NodeBootstrap
from runtime.node.current import audit_create_brief, audit_publish, project_page_get, project_page_upsert, tasks_reconcile_finish, tasks_reconcile_start
from runtime.node.store import NodeStore
from runtime.shared.ids import ActorIdentity, derive_node_proof


class TasksReconcileStartIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo_root = Path(self.tempdir.name) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.bootstrap = NodeBootstrap(repo_root=self.repo_root)
        self.bootstrap.open_or_init(interactive=False)
        self.state = self.bootstrap.adopt_repo(interactive=False)
        self.node_db_path = self.repo_root / ".capiforge" / "node" / "node.sqlite3"

    def _store(self) -> NodeStore:
        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        return store

    def _seed_actor(self, store: NodeStore, *, agent_id: str, session_id: str) -> ActorIdentity:
        invitation_fingerprint = store.ensure_local_node_actor(node_id=self.state.local_node_id)
        return ActorIdentity(
            node_id=self.state.local_node_id,
            agent_id=agent_id,
            session_id=session_id,
            node_proof=derive_node_proof(
                node_id=self.state.local_node_id,
                agent_id=agent_id,
                session_id=session_id,
                invitation_fingerprint=invitation_fingerprint,
            ),
        )

    def _seed_audit(self, store: NodeStore, audit_id: str = "aud_lifecycle") -> None:
        store.create_audit(audit_id, self.state.adopted_project["project_id"], "published", "Lifecycle Audit", "Audit body")
        store.db.commit()

    def _downgrade_owner_local_tasks_schema(self) -> None:
        connection = sqlite3.connect(self.node_db_path)
        try:
            connection.execute("DROP INDEX IF EXISTS idx_tasks_project_lifecycle_key")
            connection.execute("ALTER TABLE tasks DROP COLUMN lifecycle_key")
            connection.execute("PRAGMA user_version = 0")
            connection.commit()
        finally:
            connection.close()

    def _read_owner_local_schema_state(self) -> tuple[int, list[str]]:
        connection = sqlite3.connect(self.node_db_path)
        try:
            user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            columns = [row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()]
            return user_version, columns
        finally:
            connection.close()

    def _start_lifecycle_task(self, *, lifecycle_key: str, session_id: str, task_description: str = "Lifecycle-created task") -> dict:
        store = NodeStore.from_file(self.node_db_path)
        self._seed_audit(store)
        store.close()
        frozen_now = datetime(2026, 6, 19, 18, 0, 0, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            return tasks_reconcile_start(
                self.bootstrap,
                lifecycle_key=lifecycle_key,
                plan="Start lifecycle work",
                lease_minutes=5,
                origin_audit_id="aud_lifecycle",
                description=task_description,
                priority="high",
                effort="medium",
                risk="low",
                task_type="ops",
                justification={
                    "summary": "No reusable lifecycle task exists",
                    "evidence_refs": ["artifact://audit/lifecycle"],
                    "expected_impact": "Create same-project lifecycle work",
                },
                execution_context={"project_id": self.state.adopted_project["project_id"], "steps": ["claim", "start"]},
                agent_id="agent-lifecycle",
                session_id=session_id,
            )

    def test_audit_create_brief_creates_draft_for_adopted_project(self) -> None:
        result = audit_create_brief(
            self.bootstrap,
            title="Public runtime audit",
            content="Brief audit body",
            as_of="2026-06-19T18:00:00Z",
            agent_id="agent-audit",
            session_id="sess-audit-create",
        )

        self.assertEqual(result["state"], "draft")
        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        persisted = store.get_audit(result["audit_id"])
        self.assertEqual(persisted["project_id"], self.state.adopted_project["project_id"])
        self.assertEqual(persisted["title"], "Public runtime audit")
        self.assertEqual(persisted["state"], "draft")

    def test_audit_publish_promotes_adopted_project_draft_and_rejects_foreign_audit(self) -> None:
        created = audit_create_brief(
            self.bootstrap,
            title="Publish runtime audit",
            content="Brief audit body",
            as_of="2026-06-19T18:00:00Z",
            agent_id="agent-audit",
            session_id="sess-audit-publish",
        )

        published = audit_publish(
            self.bootstrap,
            audit_id=created["audit_id"],
            agent_id="agent-audit",
            session_id="sess-audit-publish",
        )
        self.assertEqual(published["state"], "published")

        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        store.upsert_project("prj_other", self.state.adopted_project["workspace_id"], self.state.local_node_id, "project://other", "Other")
        store.create_audit("aud_other", "prj_other", "draft", "Foreign", "Body")
        store.db.commit()

        with self.assertRaisesRegex(ValueError, "adopted project"):
            audit_publish(
                self.bootstrap,
                audit_id="aud_other",
                agent_id="agent-audit",
                session_id="sess-audit-publish",
            )

    def test_reconcile_start_creates_missing_task_from_audit_and_claims_it(self) -> None:
        store = NodeStore.from_file(self.node_db_path)
        self._seed_audit(store)
        store.close()

        result = tasks_reconcile_start(
            self.bootstrap,
            lifecycle_key="lifecycle://runtime/start",
            plan="Start lifecycle work",
            lease_minutes=5,
            origin_audit_id="aud_lifecycle",
            description="Lifecycle-created task",
            priority="high",
            effort="medium",
            risk="low",
            task_type="ops",
            justification={
                "summary": "No reusable lifecycle task exists",
                "evidence_refs": ["artifact://audit/lifecycle"],
                "expected_impact": "Create same-project lifecycle work",
            },
            execution_context={"project_id": self.state.adopted_project["project_id"], "steps": ["claim", "start"]},
            agent_id="agent-lifecycle",
            session_id="sess-create",
        )

        self.assertEqual(result["state"], "in_progress")
        self.assertTrue(result["created_task"])
        self.assertEqual(result["origin_audit_id"], "aud_lifecycle")
        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        persisted = store.get_task(result["task_id"])
        self.assertEqual(persisted["lifecycle_key"], "lifecycle://runtime/start")
        self.assertEqual(persisted["state"], "in_progress")
        execution_context = json.loads(persisted["execution_context_json"])
        self.assertEqual(execution_context["project_id"], self.state.adopted_project["project_id"])
        self.assertEqual(execution_context["lifecycle_creator"]["session_id"], "sess-create")

    def test_reconcile_start_composes_public_audit_publish_before_create_on_miss(self) -> None:
        created = audit_create_brief(
            self.bootstrap,
            title="Lifecycle public audit",
            content="Published before lifecycle start",
            as_of="2026-06-19T18:00:00Z",
            agent_id="agent-audit",
            session_id="sess-public-compose",
        )
        published = audit_publish(
            self.bootstrap,
            audit_id=created["audit_id"],
            agent_id="agent-audit",
            session_id="sess-public-compose",
        )

        result = tasks_reconcile_start(
            self.bootstrap,
            lifecycle_key="lifecycle://runtime/public-compose",
            plan="Compose public audit lifecycle start",
            lease_minutes=5,
            origin_audit_id=published["audit_id"],
            description="Lifecycle task from public audit",
            priority="high",
            effort="medium",
            risk="low",
            task_type="ops",
            justification={
                "summary": "No reusable lifecycle task exists",
                "evidence_refs": [published["audit_id"]],
                "expected_impact": "Create lifecycle work from the published public audit",
            },
            execution_context={"project_id": self.state.adopted_project["project_id"], "steps": ["audit_publish", "claim", "start"]},
            agent_id="agent-lifecycle",
            session_id="sess-public-compose",
        )

        self.assertTrue(result["created_task"])
        self.assertEqual(result["origin_audit_id"], published["audit_id"])
        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        persisted = store.get_task(result["task_id"])
        self.assertEqual(persisted["origin_audit_id"], published["audit_id"])

    def test_reconcile_start_rejects_non_published_origin_audit_on_create_miss(self) -> None:
        created = audit_create_brief(
            self.bootstrap,
            title="Draft lifecycle audit",
            content="Still a draft",
            as_of="2026-06-19T18:00:00Z",
            agent_id="agent-audit",
            session_id="sess-draft-origin",
        )

        with self.assertRaisesRegex(ValueError, "published origin audit"):
            tasks_reconcile_start(
                self.bootstrap,
                lifecycle_key="lifecycle://runtime/draft-origin",
                plan="Reject draft origin audit",
                lease_minutes=5,
                origin_audit_id=created["audit_id"],
                description="Should fail",
                priority="high",
                effort="low",
                risk="low",
                task_type="ops",
                justification={
                    "summary": "Reject draft audit origin",
                    "evidence_refs": [created["audit_id"]],
                    "expected_impact": "Prevent task creation from a draft audit",
                },
                execution_context={"project_id": self.state.adopted_project["project_id"]},
                agent_id="agent-lifecycle",
                session_id="sess-draft-origin",
            )

    def test_reconcile_start_reuses_ready_claimed_in_progress_and_blocked_tasks(self) -> None:
        scenarios = (
            ("ready", None),
            ("claimed", "claimed"),
            ("in_progress", "in_progress"),
            ("blocked", None),
        )
        for index, (state, active_state) in enumerate(scenarios):
            with self.subTest(state=state):
                store = NodeStore.from_file(self.node_db_path)
                task_id = f"tsk_lifecycle_{state}_{index}"
                audit_id = f"aud_lifecycle_{state}_{index}"
                session_id = f"sess-{state}-{index}"
                self._seed_audit(store, audit_id)
                store.create_task(
                    task_id,
                    self.state.adopted_project["project_id"],
                    audit_id,
                    state,
                    "high",
                    "low",
                    "low",
                    "ops",
                    f"Lifecycle task {state}",
                    justification_json=json.dumps(
                        {
                            "summary": "Existing lifecycle task",
                            "evidence_refs": [f"artifact://{state}"],
                            "expected_impact": "Allow reuse",
                        },
                        sort_keys=True,
                    ),
                    execution_context_json=json.dumps({"project_id": self.state.adopted_project["project_id"], "inputs": [state]}, sort_keys=True),
                    active_claim_session_id=(session_id if state in {"claimed", "in_progress"} else None),
                    lifecycle_key=f"lifecycle://reuse/{state}",
                    blocked_reason=("awaiting retry" if state == "blocked" else None),
                    blocked_evidence=("artifact://blocked" if state == "blocked" else None),
                    blocked_next_step=("re-run" if state == "blocked" else None),
                )
                if active_state:
                    actor = self._seed_actor(store, agent_id="agent-lifecycle", session_id=session_id)
                    claims = ClaimRegistry(store.db)
                    claims.claim_task(
                        claim_id=f"clm_{state}_{index}",
                        project_id=self.state.adopted_project["project_id"],
                        task_id=task_id,
                        actor=actor,
                        plan=f"Reuse {state}",
                        lease_started_at="2026-06-19T18:00:00Z",
                        lease_expires_at="2026-06-19T18:10:00Z",
                    )
                store.db.commit()
                store.close()

                result = tasks_reconcile_start(
                    self.bootstrap,
                    lifecycle_key=f"lifecycle://reuse/{state}",
                    plan=f"Resume {state} lifecycle work",
                    lease_minutes=5,
                    agent_id="agent-lifecycle",
                    session_id=session_id,
                )

                self.assertEqual(result["task_id"], task_id)
                self.assertEqual(result["state"], "in_progress")
                self.assertFalse(result["created_task"])
                self.assertIsNotNone(result["claim_id"])
                store = NodeStore.from_file(self.node_db_path)
                self.addCleanup(store.close)
                self.assertEqual(store.get_task(task_id)["state"], "in_progress")

    def test_reconcile_start_rejects_cross_project_execution_context(self) -> None:
        store = NodeStore.from_file(self.node_db_path)
        self._seed_audit(store)
        store.close()

        with self.assertRaisesRegex(ValueError, "must stay within the adopted project"):
            tasks_reconcile_start(
                self.bootstrap,
                lifecycle_key="lifecycle://runtime/guard",
                plan="Guard same-project scope",
                lease_minutes=5,
                origin_audit_id="aud_lifecycle",
                description="Should fail",
                priority="high",
                effort="low",
                risk="low",
                task_type="ops",
                justification={
                    "summary": "Attempt cross-project execution",
                    "evidence_refs": ["artifact://guard"],
                    "expected_impact": "Reject mismatched project context",
                },
                execution_context={"source_project_id": "prj_other"},
                agent_id="agent-lifecycle",
                session_id="sess-guard",
            )

    def test_reconcile_finish_closes_done_task_and_releases_claim_cache(self) -> None:
        started = self._start_lifecycle_task(lifecycle_key="lifecycle://runtime/finish/done", session_id="sess-finish-done")

        result = tasks_reconcile_finish(
            self.bootstrap,
            lifecycle_key="lifecycle://runtime/finish/done",
            outcome="done",
            as_of="2026-06-19T18:04:00Z",
            done_result="Implemented the lifecycle closeout",
            done_artifacts="artifact://runtime/finish/done",
            done_references="ref://runtime/finish/done",
            done_expected_impact="Record deterministic completion",
            agent_id="agent-lifecycle",
            session_id="sess-finish-done",
        )

        self.assertEqual(result["task_id"], started["task_id"])
        self.assertEqual(result["state"], "done")
        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        persisted = store.get_task(started["task_id"])
        self.assertEqual(persisted["done_result"], "Implemented the lifecycle closeout")
        self.assertIsNone(store.get_cached_claim(started["task_id"]))
        self.assertIsNone(ClaimRegistry(store.db).get_active_claim(project_id=self.state.adopted_project["project_id"], task_id=started["task_id"], as_of="2026-06-19T18:04:00Z"))

    def test_reconcile_finish_rejects_expired_claim_without_terminal_mutation(self) -> None:
        started = self._start_lifecycle_task(lifecycle_key="lifecycle://runtime/finish/expired", session_id="sess-finish-expired")

        with self.assertRaisesRegex(ValueError, "reconcile-start again after lease expiry"):
            tasks_reconcile_finish(
                self.bootstrap,
                lifecycle_key="lifecycle://runtime/finish/expired",
                outcome="blocked",
                as_of="2026-06-19T18:06:00Z",
                blocked_reason="Lease expired before closeout",
                blocked_evidence="artifact://runtime/finish/expired",
                blocked_next_step="Reconcile the task again",
                agent_id="agent-lifecycle",
                session_id="sess-finish-expired",
            )

        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        persisted = store.get_task(started["task_id"])
        self.assertEqual(persisted["state"], "ready")
        self.assertIsNone(persisted["done_result"])
        self.assertIsNone(persisted["blocked_reason"])

    def test_reconcile_finish_rejects_missing_explicit_metadata(self) -> None:
        started = self._start_lifecycle_task(lifecycle_key="lifecycle://runtime/finish/missing-metadata", session_id="sess-finish-missing")

        with self.assertRaisesRegex(ValueError, "lifecycle finish requires: done_references, done_expected_impact"):
            tasks_reconcile_finish(
                self.bootstrap,
                lifecycle_key="lifecycle://runtime/finish/missing-metadata",
                outcome="done",
                as_of="2026-06-19T18:04:00Z",
                done_result="Implemented the lifecycle closeout",
                done_artifacts="artifact://runtime/finish/missing-metadata",
                agent_id="agent-lifecycle",
                session_id="sess-finish-missing",
            )

        store = NodeStore.from_file(self.node_db_path)
        self.addCleanup(store.close)
        persisted = store.get_task(started["task_id"])
        self.assertEqual(persisted["state"], "in_progress")
        self.assertIsNone(persisted["done_result"])

    def test_reconcile_start_and_finish_upgrade_stale_owner_local_schema_before_lifecycle_access(self) -> None:
        self._downgrade_owner_local_tasks_schema()
        user_version, columns = self._read_owner_local_schema_state()
        self.assertEqual(user_version, 0)
        self.assertNotIn("lifecycle_key", columns)

        started = self._start_lifecycle_task(
            lifecycle_key="lifecycle://runtime/stale-upgrade",
            session_id="sess-stale-upgrade",
            task_description="Lifecycle task on stale schema",
        )

        self.assertEqual(started["state"], "in_progress")
        self.assertTrue(started["created_task"])
        user_version, columns = self._read_owner_local_schema_state()
        self.assertEqual(user_version, 2)
        self.assertIn("lifecycle_key", columns)

        finished = tasks_reconcile_finish(
            self.bootstrap,
            lifecycle_key="lifecycle://runtime/stale-upgrade",
            outcome="done",
            as_of="2026-06-19T18:04:00Z",
            done_result="Completed lifecycle work after auto-upgrade",
            done_artifacts="artifact://runtime/stale-upgrade",
            done_references="ref://runtime/stale-upgrade",
            done_expected_impact="Prove stale owner-local lifecycle reconciliation succeeds",
            agent_id="agent-lifecycle",
            session_id="sess-stale-upgrade",
        )

        self.assertEqual(finished["task_id"], started["task_id"])
        self.assertEqual(finished["state"], "done")


class ProjectPageRuntimeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo_root = Path(self.tempdir.name) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.bootstrap = NodeBootstrap(repo_root=self.repo_root)
        self.bootstrap.open_or_init(interactive=False)
        self.state = self.bootstrap.adopt_repo(interactive=False)
        self.project_id = self.state.adopted_project["project_id"]

    def test_project_page_get_returns_unknown_resource_when_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "unknown project page type"):
            project_page_get(self.bootstrap, page_type="purpose")

    def test_project_page_upsert_and_get_round_trip(self) -> None:
        upserted = project_page_upsert(
            self.bootstrap,
            page_type="architecture",
            title="Architecture",
            content="System overview",
            as_of="2026-06-21T17:00:00Z",
        )
        self.assertEqual(upserted["page_type"], "architecture")
        self.assertEqual(upserted["content"], "System overview")

        fetched = project_page_get(self.bootstrap, page_type="architecture", as_of="2026-06-21T17:00:00Z")
        self.assertEqual(fetched["page_id"], upserted["page_id"])
        self.assertEqual(fetched["content"], "System overview")
        self.assertEqual(fetched["adopted_project"]["project_id"], self.project_id)


if __name__ == "__main__":
    unittest.main()
