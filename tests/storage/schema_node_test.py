import sqlite3
import tempfile
import unittest
from pathlib import Path

from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError


def load_schema(name: str) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.execute("PRAGMA foreign_keys = ON")
    sql = Path("storage", name).read_text()
    connection.executescript(sql)
    return connection


class NodeSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = load_schema("node-schema.sql")
        self.addCleanup(self.db.close)
        self.db.execute("INSERT INTO workspaces VALUES ('ws_1','workspace://ws_1','Workspace')")
        self.db.execute("INSERT INTO projects VALUES ('prj_1','ws_1','node_owner','project://prj_1','Project')")
        self.db.execute("INSERT INTO audits VALUES ('aud_1','prj_1','published','Audit','body',NULL)")

    def test_closed_audits_are_immutable(self) -> None:
        self.db.execute("UPDATE audits SET state = 'closed' WHERE audit_id = 'aud_1'")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "closed audits are immutable"):
            self.db.execute("UPDATE audits SET content = 'changed' WHERE audit_id = 'aud_1'")

    def test_task_state_requires_blocked_and_done_metadata(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json) VALUES ('tsk_bad','prj_1','aud_1','blocked','high','low','low','fix','desc','{}','{}')")
        self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_done','prj_1','aud_1','done','high','low','low','fix','desc','{}','{}',NULL,NULL,NULL,NULL,NULL,'result','artifacts','refs','impact')")

    def test_non_owner_canonical_mutation_is_rejected(self) -> None:
        self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_1','prj_1','aud_1','ready','high','low','low','fix','desc','{}','{}',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "canonical writes require owner node"):
            self.db.execute("INSERT INTO task_mutations (mutation_id,task_id,actor_node_id,actor_agent_id,actor_session_id,justification_json,authority_mode) VALUES ('mut_1','tsk_1','node_other','agent_1','sess_1','{}','canonical')")

    def test_lifecycle_key_is_unique_per_project_but_allows_null_back_compat(self) -> None:
        self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_null_1','prj_1','aud_1','ready','high','low','low','fix','desc 1','{}','{}',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_null_2','prj_1','aud_1','ready','high','low','low','fix','desc 2','{}','{}',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        self.db.execute("INSERT INTO projects VALUES ('prj_2','ws_1','node_owner','project://prj_2','Project 2')")
        self.db.execute("INSERT INTO audits VALUES ('aud_2','prj_2','published','Audit 2','body',NULL)")
        self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_key_1','prj_1','aud_1','ready','high','low','low','fix','desc 3','{}','{}',NULL,'lifecycle://same',NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_key_2','prj_2','aud_2','ready','high','low','low','fix','desc 4','{}','{}',NULL,'lifecycle://same',NULL,NULL,NULL,NULL,NULL,NULL,NULL)")

        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_key_dup','prj_1','aud_1','ready','high','low','low','fix','dup','{}','{}',NULL,'lifecycle://same',NULL,NULL,NULL,NULL,NULL,NULL,NULL)")

    def test_store_lookup_by_lifecycle_key_is_exact_and_deterministic(self) -> None:
        store = NodeStore(self.db)
        store.create_task(
            "tsk_lifecycle",
            "prj_1",
            "aud_1",
            "ready",
            "high",
            "low",
            "low",
            "fix",
            "Lifecycle task",
            lifecycle_key="lifecycle://agent/start",
        )

        task = store.get_task("tsk_lifecycle")
        self.assertEqual(task["lifecycle_key"], "lifecycle://agent/start")
        self.assertEqual(
            store.get_task_by_lifecycle_key("prj_1", "lifecycle://agent/start")["task_id"],
            "tsk_lifecycle",
        )
        self.assertIsNone(store.get_task_by_lifecycle_key("prj_1", "lifecycle://agent/other"))

    def test_canonical_schema_sets_owner_local_user_version(self) -> None:
        self.assertEqual(self.db.execute("PRAGMA user_version").fetchone()[0], 1)

    def test_from_file_repairs_missing_lifecycle_key_and_index_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            db_path = Path(tempdir) / "node.sqlite3"
            connection = sqlite3.connect(db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                PRAGMA foreign_keys = ON;
                PRAGMA user_version = 0;

                CREATE TABLE workspaces (
                  workspace_id TEXT PRIMARY KEY,
                  canonical_link TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL
                );

                CREATE TABLE projects (
                  project_id TEXT PRIMARY KEY,
                  workspace_id TEXT NOT NULL REFERENCES workspaces(workspace_id) ON DELETE CASCADE,
                  owner_node_id TEXT NOT NULL,
                  canonical_link TEXT NOT NULL UNIQUE,
                  name TEXT NOT NULL
                );

                CREATE TABLE audits (
                  audit_id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                  state TEXT NOT NULL CHECK (state IN ('draft','published','closed','superseded')),
                  title TEXT NOT NULL,
                  content TEXT NOT NULL,
                  addendum_of_audit_id TEXT REFERENCES audits(audit_id)
                );

                CREATE TABLE tasks (
                  task_id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
                  origin_audit_id TEXT NOT NULL REFERENCES audits(audit_id),
                  state TEXT NOT NULL CHECK (state IN ('proposed','ready','claimed','in_progress','blocked','done','cancelled')),
                  priority TEXT NOT NULL CHECK (priority IN ('low','medium','high','critical')),
                  effort TEXT NOT NULL CHECK (effort IN ('low','medium','high')),
                  risk TEXT NOT NULL CHECK (risk IN ('low','medium','high')),
                  type TEXT NOT NULL CHECK (type IN ('fix','feature','audit_followup','doc','refactor','ops')),
                  description TEXT NOT NULL,
                  justification_json TEXT NOT NULL,
                  execution_context_json TEXT NOT NULL,
                  active_claim_session_id TEXT,
                  blocked_reason TEXT,
                  blocked_evidence TEXT,
                  blocked_next_step TEXT,
                  done_result TEXT,
                  done_artifacts TEXT,
                  done_references TEXT,
                  done_expected_impact TEXT,
                  CHECK (state != 'blocked' OR (blocked_reason IS NOT NULL AND blocked_evidence IS NOT NULL AND blocked_next_step IS NOT NULL)),
                  CHECK (state != 'done' OR (done_result IS NOT NULL AND done_artifacts IS NOT NULL AND done_references IS NOT NULL AND done_expected_impact IS NOT NULL)),
                  CHECK (state NOT IN ('claimed','in_progress') OR active_claim_session_id IS NOT NULL)
                );

                INSERT INTO workspaces VALUES ('ws_1','workspace://ws_1','Workspace');
                INSERT INTO projects VALUES ('prj_1','ws_1','node_owner','project://prj_1','Project');
                INSERT INTO audits VALUES ('aud_1','prj_1','published','Audit','body',NULL);
                INSERT INTO tasks (
                  task_id, project_id, origin_audit_id, state, priority, effort, risk, type, description,
                  justification_json, execution_context_json, active_claim_session_id, blocked_reason,
                  blocked_evidence, blocked_next_step, done_result, done_artifacts, done_references,
                  done_expected_impact
                ) VALUES (
                  'tsk_1', 'prj_1', 'aud_1', 'ready', 'high', 'low', 'low', 'fix', 'desc',
                  '{}', '{}', NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL
                );
                """
            )
            connection.commit()
            connection.close()

            store = NodeStore.from_file(db_path)
            try:
                columns = [row[1] for row in store.db.execute("PRAGMA table_info(tasks)").fetchall()]
                self.assertIn("lifecycle_key", columns)
                self.assertEqual(store.db.execute("PRAGMA user_version").fetchone()[0], 1)

                index_row = store.db.execute(
                    "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = 'idx_tasks_project_lifecycle_key'"
                ).fetchone()
                self.assertIsNotNone(index_row)
                self.assertIn("WHERE lifecycle_key IS NOT NULL", index_row[0])

                store.db.execute("UPDATE tasks SET lifecycle_key = 'lifecycle://same' WHERE task_id = 'tsk_1'")
                with self.assertRaises(sqlite3.IntegrityError):
                    store.db.execute(
                        "INSERT INTO tasks (task_id,project_id,origin_audit_id,state,priority,effort,risk,type,description,justification_json,execution_context_json,active_claim_session_id,lifecycle_key,blocked_reason,blocked_evidence,blocked_next_step,done_result,done_artifacts,done_references,done_expected_impact) VALUES ('tsk_2','prj_1','aud_1','ready','high','low','low','fix','desc 2','{}','{}',NULL,'lifecycle://same',NULL,NULL,NULL,NULL,NULL,NULL,NULL)"
                    )
                store.db.rollback()
            finally:
                store.close()

            reopened = NodeStore.from_file(db_path)
            try:
                self.assertEqual(reopened.db.execute("PRAGMA user_version").fetchone()[0], 1)
                columns = [row[1] for row in reopened.db.execute("PRAGMA table_info(tasks)").fetchall()]
                self.assertIn("lifecycle_key", columns)
            finally:
                reopened.close()

    def test_from_file_rejects_unsupported_owner_local_drift_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            future_db_path = Path(tempdir) / "future.sqlite3"
            connection = sqlite3.connect(future_db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE tasks (
                  task_id TEXT PRIMARY KEY,
                  project_id TEXT NOT NULL,
                  lifecycle_key TEXT
                );
                PRAGMA user_version = 99;
                """
            )
            connection.commit()
            connection.close()

            with self.assertRaises(SurfaceError) as future_ctx:
                NodeStore.from_file(future_db_path)

            self.assertEqual(future_ctx.exception.code, "LOCAL_SCHEMA_COMPATIBILITY_ERROR")
            reopened = sqlite3.connect(future_db_path)
            try:
                self.assertEqual(reopened.execute("PRAGMA user_version").fetchone()[0], 99)
            finally:
                reopened.close()

            unsafe_db_path = Path(tempdir) / "unsafe.sqlite3"
            connection = sqlite3.connect(unsafe_db_path)
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE tasks (
                  task_id TEXT PRIMARY KEY,
                  lifecycle_key TEXT
                );
                PRAGMA user_version = 0;
                """
            )
            connection.commit()
            connection.close()

            with self.assertRaises(SurfaceError) as unsafe_ctx:
                NodeStore.from_file(unsafe_db_path)

            self.assertEqual(unsafe_ctx.exception.code, "LOCAL_SCHEMA_COMPATIBILITY_ERROR")
            reopened = sqlite3.connect(unsafe_db_path)
            try:
                self.assertEqual(reopened.execute("PRAGMA user_version").fetchone()[0], 0)
                columns = [row[1] for row in reopened.execute("PRAGMA table_info(tasks)").fetchall()]
                self.assertNotIn("project_id", columns)
                self.assertEqual(columns, ["task_id", "lifecycle_key"])
            finally:
                reopened.close()


if __name__ == "__main__":
    unittest.main()
