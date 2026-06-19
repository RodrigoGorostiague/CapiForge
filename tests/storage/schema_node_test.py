import sqlite3
import unittest
from pathlib import Path


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
        self.db.execute("INSERT INTO tasks VALUES ('tsk_done','prj_1','aud_1','done','high','low','low','fix','desc','{}','{}',NULL,NULL,NULL,NULL,'result','artifacts','refs','impact')")

    def test_non_owner_canonical_mutation_is_rejected(self) -> None:
        self.db.execute("INSERT INTO tasks VALUES ('tsk_1','prj_1','aud_1','ready','high','low','low','fix','desc','{}','{}',NULL,NULL,NULL,NULL,NULL,NULL,NULL,NULL)")
        with self.assertRaisesRegex(sqlite3.IntegrityError, "canonical writes require owner node"):
            self.db.execute("INSERT INTO task_mutations (mutation_id,task_id,actor_node_id,actor_agent_id,actor_session_id,justification_json,authority_mode) VALUES ('mut_1','tsk_1','node_other','agent_1','sess_1','{}','canonical')")


if __name__ == "__main__":
    unittest.main()
