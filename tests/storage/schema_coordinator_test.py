import sqlite3
import unittest
from pathlib import Path


class CoordinatorSchemaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.addCleanup(self.db.close)
        self.db.execute("PRAGMA foreign_keys = ON")
        self.db.executescript(Path("storage/coordinator-schema.sql").read_text())
        self.db.execute("INSERT INTO nodes VALUES ('node_1','Owner','fingerprint-1','active',NULL)")
        self.db.execute("INSERT INTO nodes VALUES ('node_2','Worker','fingerprint-2','active',NULL)")

    def test_one_active_claim_per_task(self) -> None:
        self.db.execute("INSERT INTO claim_leases VALUES ('clm_1','prj_1','tsk_1','node_1','agent_1','sess_1','plan','active','2026-01-01','2026-01-02')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO claim_leases VALUES ('clm_2','prj_1','tsk_1','node_2','agent_2','sess_2','plan','active','2026-01-01','2026-01-02')")

    def test_one_owner_per_project(self) -> None:
        self.db.execute("INSERT INTO project_owners VALUES ('prj_1','node_1','human_1','2026-01-01')")
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("INSERT INTO project_owners VALUES ('prj_1','node_2','human_2','2026-01-02')")


if __name__ == "__main__":
    unittest.main()
