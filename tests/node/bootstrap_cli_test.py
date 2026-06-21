import importlib.util
import io
import json
import multiprocessing
import sqlite3
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from runtime.coordinator.claims import ClaimRegistry
from runtime.node.bootstrap import BootstrapLockInfo, NodeBootstrap
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity, derive_node_proof


CLI_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "capiforge_cli.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("capiforge_cli", CLI_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def hold_bootstrap_lock(repo_root: str, node_home: str, command: str, hold_seconds: float, ready_queue) -> None:
    bootstrap = NodeBootstrap(repo_root=repo_root, node_home=node_home)
    with bootstrap.bootstrap_session(
        command=command,
        timeout=1.0,
        interactive=False,
        verbose=False,
        recover_stale_lock=False,
    ):
        ready_queue.put("locked")
        time.sleep(hold_seconds)


def hold_bootstrap_lock_with_age(
    repo_root: str,
    node_home: str,
    command: str,
    hold_seconds: float,
    age_seconds: float,
    ready_queue,
) -> None:
    bootstrap = NodeBootstrap(repo_root=repo_root, node_home=node_home)
    bootstrap.node_home.mkdir(parents=True, exist_ok=True)
    lock_handle = bootstrap.lock_path.open("a+")
    try:
        import fcntl

        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        acquired_at = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat().replace("+00:00", "Z")
        bootstrap._write_lock_metadata(
            lock_handle,
            BootstrapLockInfo(
                owner_node_id=bootstrap.local_node_id,
                pid=multiprocessing.current_process().pid,
                command=command,
                acquired_at=acquired_at,
                last_seen_at=acquired_at,
            ),
        )
        ready_queue.put("locked")
        time.sleep(hold_seconds)
    finally:
        bootstrap._release_bootstrap_lock(lock_handle)


def acquire_bootstrap_lock_once(repo_root: str, node_home: str, command: str, hold_seconds: float, result_queue) -> None:
    bootstrap = NodeBootstrap(repo_root=repo_root, node_home=node_home)
    with bootstrap.bootstrap_session(
        command=command,
        timeout=1.0,
        interactive=False,
        verbose=False,
        recover_stale_lock=False,
    ):
        result_queue.put(
            {
                "event": "acquired",
                "inode": bootstrap.lock_path.stat().st_ino,
                "command": command,
            }
        )
        time.sleep(hold_seconds)


def attempt_bootstrap_command(repo_root: str, node_home: str, command: str, timeout: float, result_queue) -> None:
    bootstrap = NodeBootstrap(repo_root=repo_root, node_home=node_home)
    try:
        with bootstrap.bootstrap_session(
            command=command,
            timeout=timeout,
            interactive=False,
            verbose=False,
            recover_stale_lock=False,
        ):
            result_queue.put({"status": "acquired"})
    except SurfaceError as exc:
        result_queue.put({"status": exc.code})


def downgrade_owner_local_tasks_schema(db_path: Path) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.execute("DROP INDEX IF EXISTS idx_tasks_project_lifecycle_key")
        connection.execute("ALTER TABLE tasks DROP COLUMN lifecycle_key")
        connection.execute("PRAGMA user_version = 0")
        connection.commit()
    finally:
        connection.close()


def read_owner_local_schema_state(db_path: Path) -> tuple[int, list[str]]:
    connection = sqlite3.connect(db_path)
    try:
        user_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = [row[1] for row in connection.execute("PRAGMA table_info(tasks)").fetchall()]
        return user_version, columns
    finally:
        connection.close()


def write_incompatible_owner_local_schema(db_path: Path, *, user_version: int, include_project_id: bool) -> None:
    connection = sqlite3.connect(db_path)
    try:
        connection.executescript(
            """
            DROP TABLE IF EXISTS tasks;
            CREATE TABLE tasks (
              task_id TEXT PRIMARY KEY
            );
            """
        )
        if include_project_id:
            connection.execute("ALTER TABLE tasks ADD COLUMN project_id TEXT NOT NULL DEFAULT 'prj_1'")
        connection.execute("ALTER TABLE tasks ADD COLUMN lifecycle_key TEXT")
        connection.execute(f"PRAGMA user_version = {user_version}")
        connection.commit()
    finally:
        connection.close()


class BootstrapPersistenceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo_root = Path(self.tempdir.name) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.bootstrap = NodeBootstrap(repo_root=self.repo_root)

    def test_fresh_init_persists_initialized_state(self) -> None:
        state = self.bootstrap.open_or_init()

        self.assertEqual(state.state, "initialized")
        self.assertIsNone(state.adopted_project)
        self.assertTrue((self.repo_root / ".capiforge" / "node" / "bootstrap.json").exists())
        self.assertTrue((self.repo_root / ".capiforge" / "node" / "node.sqlite3").exists())

    def test_init_is_idempotent_for_existing_bootstrap(self) -> None:
        first = self.bootstrap.open_or_init()
        second = self.bootstrap.open_or_init()

        self.assertEqual(first, second)

    def test_adopt_rejects_before_initialization(self) -> None:
        with self.assertRaises(SurfaceError) as ctx:
            self.bootstrap.adopt_repo()

        self.assertEqual(ctx.exception.code, "INVALID_BOOTSTRAP_STATE")

    def test_same_repo_adopt_is_idempotent(self) -> None:
        self.bootstrap.open_or_init()

        first = self.bootstrap.adopt_repo()
        second = self.bootstrap.adopt_repo()

        self.assertEqual(first, second)
        self.assertEqual(first.state, "adopted")
        self.assertEqual(first.adopted_project["repo_root"], str(self.repo_root.resolve()))

        store = NodeStore.from_file(self.repo_root / ".capiforge" / "node" / "node.sqlite3")
        self.addCleanup(store.close)
        workspace = store.get_workspace(first.adopted_project["workspace_id"])
        project = store.get_project(first.adopted_project["project_id"])
        self.assertIsNotNone(workspace)
        self.assertIsNotNone(project)
        self.assertEqual(workspace["name"], self.repo_root.parent.name)
        self.assertEqual(workspace["canonical_link"], f"workspace://{self.repo_root.parent.name}")
        self.assertEqual(project["name"], self.repo_root.name)
        self.assertEqual(project["canonical_link"], f"project://{self.repo_root.name}")
        self.assertEqual(project["owner_node_id"], first.local_node_id)

    def test_adopt_rejects_non_repo_root_target(self) -> None:
        self.bootstrap.open_or_init()
        other_repo = self.repo_root.parent / "other-repo"
        other_repo.mkdir(parents=True, exist_ok=True)

        with self.assertRaises(SurfaceError) as ctx:
            self.bootstrap.adopt_repo(other_repo)

        self.assertEqual(ctx.exception.code, "TRUST_BOUNDARY_VIOLATION")

    def test_open_or_init_rejects_tampered_manifest_before_creating_expected_db(self) -> None:
        self.node_home = self.repo_root / ".capiforge" / "node"
        self.node_home.mkdir(parents=True, exist_ok=True)
        escaped_db_path = (self.repo_root / ".." / "escaped.sqlite3").resolve()
        manifest_path = self.node_home / "bootstrap.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "state": "initialized",
                    "local_node_id": self.bootstrap.local_node_id,
                    "node_home": str(self.node_home.resolve()),
                    "node_db_path": str(escaped_db_path),
                    "adopted_project": None,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        with self.assertRaises(SurfaceError) as ctx:
            self.bootstrap.open_or_init()

        self.assertEqual(ctx.exception.code, "INVALID_BOOTSTRAP_STATE")
        self.assertFalse((self.node_home / "node.sqlite3").exists())
        self.assertFalse(escaped_db_path.exists())

    def test_open_or_init_waits_for_active_lock_owner(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock,
            args=(str(self.repo_root), str(self.bootstrap.node_home), "init", 0.3, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        started_at = time.monotonic()
        state = self.bootstrap.open_or_init(lock_timeout_seconds=1.0, interactive=False)
        elapsed = time.monotonic() - started_at

        holder.join(timeout=2.0)
        self.assertFalse(holder.is_alive())
        self.assertEqual(state.state, "initialized")
        self.assertGreaterEqual(elapsed, 0.2)

    def test_bootstrap_session_times_out_when_owner_does_not_release_lock(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock,
            args=(str(self.repo_root), str(self.bootstrap.node_home), "status", 0.5, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        with self.assertRaises(SurfaceError) as ctx:
            with self.bootstrap.bootstrap_session(
                command="status",
                timeout=0.1,
                interactive=False,
                verbose=False,
                recover_stale_lock=False,
            ):
                self.fail("bootstrap_session should not acquire the lock before timeout")

        holder.join(timeout=2.0)
        self.assertEqual(ctx.exception.code, "BOOTSTRAP_LOCK_TIMEOUT")
        self.assertEqual(ctx.exception.details["liveness"], "alive")
        self.assertEqual(ctx.exception.details["owner_node_id"], self.bootstrap.local_node_id)

    def test_bootstrap_session_requires_explicit_recovery_for_stale_lock_file(self) -> None:
        self.bootstrap.node_home.mkdir(parents=True, exist_ok=True)
        self.bootstrap.lock_path.write_text(
            json.dumps(
                {
                    "owner_node_id": self.bootstrap.local_node_id,
                    "pid": 999999,
                    "command": "init",
                    "acquired_at": "2026-06-19T00:00:00Z",
                    "last_seen_at": "2026-06-19T00:00:00Z",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        with self.assertRaises(SurfaceError) as ctx:
            with self.bootstrap.bootstrap_session(
                command="status",
                timeout=0.1,
                interactive=False,
                verbose=False,
                recover_stale_lock=False,
            ):
                self.fail("stale lock recovery should require explicit approval")

        self.assertEqual(ctx.exception.code, "BOOTSTRAP_LOCK_SUSPECT")
        self.assertEqual(ctx.exception.details["liveness"], "dead")

        with self.bootstrap.bootstrap_session(
            command="status",
            timeout=0.1,
            interactive=False,
            verbose=False,
            recover_stale_lock=True,
        ) as outcome:
            self.assertEqual(outcome.status, "acquired")

    def test_bootstrap_session_treats_old_active_lock_owner_as_suspect(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock_with_age,
            args=(str(self.repo_root), str(self.bootstrap.node_home), "status", 0.5, 31.0, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        with self.assertRaises(SurfaceError) as ctx:
            with self.bootstrap.bootstrap_session(
                command="status",
                timeout=1.0,
                interactive=False,
                verbose=False,
                recover_stale_lock=False,
            ):
                self.fail("old active lock owner should require explicit recovery")

        holder.join(timeout=2.0)
        self.assertEqual(ctx.exception.code, "BOOTSTRAP_LOCK_SUSPECT")
        self.assertEqual(ctx.exception.details["liveness"], "alive")
        self.assertGreaterEqual(ctx.exception.details["lock_age_seconds"], 30.0)

    def test_lock_file_inode_stays_stable_across_release_and_reacquire(self) -> None:
        context = multiprocessing.get_context("fork")
        holder_queue = context.Queue()
        contender_queue = context.Queue()
        holder = context.Process(
            target=acquire_bootstrap_lock_once,
            args=(str(self.repo_root), str(self.bootstrap.node_home), "init", 0.2, holder_queue),
        )
        contender = context.Process(
            target=acquire_bootstrap_lock_once,
            args=(str(self.repo_root), str(self.bootstrap.node_home), "status", 0.05, contender_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        holder_result = holder_queue.get(timeout=2.0)
        self.assertEqual(holder_result["event"], "acquired")

        contender.start()
        self.addCleanup(lambda: contender.is_alive() and contender.terminate())

        holder.join(timeout=2.0)
        self.assertFalse(holder.is_alive())
        inode_after_release = self.bootstrap.lock_path.stat().st_ino
        contender_result = contender_queue.get(timeout=2.0)
        contender.join(timeout=2.0)
        self.assertFalse(contender.is_alive())

        self.assertEqual(contender_result["event"], "acquired")
        self.assertEqual(holder_result["inode"], inode_after_release)
        self.assertEqual(contender_result["inode"], inode_after_release)

    def test_read_entrypoint_keeps_lock_held_while_touching_sqlite_state(self) -> None:
        self.bootstrap.open_or_init()
        adopted = self.bootstrap.adopt_repo()

        from runtime.node.mcp import NodeMCPSurface

        original_method = NodeMCPSurface.project_entrypoint_get_local

        def guarded_entrypoint(surface, *args, **kwargs):
            context = multiprocessing.get_context("fork")
            result_queue = context.Queue()
            contender = context.Process(
                target=attempt_bootstrap_command,
                args=(str(self.repo_root), str(self.bootstrap.node_home), "status", 0.05, result_queue),
            )
            contender.start()
            try:
                result = result_queue.get(timeout=2.0)
                self.assertEqual(result["status"], "BOOTSTRAP_LOCK_TIMEOUT")
                return original_method(surface, *args, **kwargs)
            finally:
                contender.join(timeout=2.0)
                if contender.is_alive():
                    contender.terminate()

        with patch("runtime.node.mcp.NodeMCPSurface.project_entrypoint_get_local", autospec=True, side_effect=guarded_entrypoint):
            state, entrypoint = self.bootstrap.read_entrypoint(as_of="2026-06-19T13:00:00Z")

        self.assertEqual(state.state, "adopted")
        self.assertEqual(state.adopted_project, adopted.adopted_project)
        self.assertEqual(entrypoint["project_id"], adopted.adopted_project["project_id"])

    def test_open_or_init_repairs_supported_stale_adopted_schema_on_reopen(self) -> None:
        self.bootstrap.open_or_init(interactive=False)
        adopted = self.bootstrap.adopt_repo(interactive=False)

        downgrade_owner_local_tasks_schema(self.bootstrap.node_db_path)

        reopened = self.bootstrap.open_or_init(interactive=False)

        self.assertEqual(reopened.state, "adopted")
        self.assertEqual(reopened.adopted_project, adopted.adopted_project)
        user_version, columns = read_owner_local_schema_state(self.bootstrap.node_db_path)
        self.assertEqual(user_version, 2)
        self.assertIn("lifecycle_key", columns)


class BootstrapCliSurfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo_root = Path(self.tempdir.name) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.node_home = self.repo_root / ".capiforge" / "node"
        self.cli = load_cli_module()

    def invoke(self, *argv: str) -> tuple[int, dict]:
        buffer = io.StringIO()
        with redirect_stdout(buffer):
            exit_code = self.cli.main(list(argv))
        return exit_code, json.loads(buffer.getvalue())

    def invoke_subprocess(self, *argv: str) -> tuple[int, dict]:
        completed = subprocess.run(
            ["python3", str(CLI_MODULE_PATH), *argv],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode, json.loads(completed.stdout)

    def invoke_subprocess_raw(self, *argv: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", str(CLI_MODULE_PATH), *argv],
            check=False,
            capture_output=True,
            text=True,
        )

    def _seed_ready_tasks(self, project_id: str, count: int = 1) -> None:
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        for index in range(count):
            audit_id = f"aud_ready_{index}"
            task_id = f"tsk_ready_{index}"
            store.create_audit(audit_id, project_id, "published", f"Ready audit {index}", "Audit body")
            store.create_task(task_id, project_id, audit_id, "ready", "high", "low", "low", "feature", f"Ready task {index}")
        store.db.commit()

    def _seed_lifecycle_task(self, project_id: str, *, task_id: str, audit_id: str, lifecycle_key: str, state: str = "ready") -> None:
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        store.create_audit(audit_id, project_id, "published", f"Lifecycle audit {audit_id}", "Audit body")
        store.create_task(
            task_id,
            project_id,
            audit_id,
            state,
            "high",
            "low",
            "low",
            "ops",
            "Lifecycle task",
            justification_json=json.dumps(
                {
                    "summary": "Existing lifecycle task",
                    "evidence_refs": [lifecycle_key],
                    "expected_impact": "Allow lifecycle reuse",
                },
                sort_keys=True,
            ),
            execution_context_json=json.dumps({"project_id": project_id}, sort_keys=True),
            lifecycle_key=lifecycle_key,
        )
        store.db.commit()

    def _assert_owner_local_schema_upgraded(self) -> None:
        user_version, columns = read_owner_local_schema_state(self.node_home / "node.sqlite3")
        self.assertEqual(user_version, 2)
        self.assertIn("lifecycle_key", columns)

    def _seed_active_claim_for_task(self, *, task_id: str, session_id: str, plan: str) -> None:
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        invitation_fingerprint = store.ensure_local_node_actor(node_id=bootstrap.local_node_id)
        actor = ActorIdentity(
            node_id=bootstrap.local_node_id,
            agent_id="agent-conflict",
            session_id=session_id,
            node_proof=derive_node_proof(
                node_id=bootstrap.local_node_id,
                agent_id="agent-conflict",
                session_id=session_id,
                invitation_fingerprint=invitation_fingerprint,
            ),
        )
        claims = ClaimRegistry(store.db)
        claim = claims.claim_task(
            claim_id=f"clm_{task_id}",
            project_id=store.get_task(task_id)["project_id"],
            task_id=task_id,
            actor=actor,
            plan=plan,
            lease_started_at="2026-06-19T18:00:00Z",
            lease_expires_at="2099-06-19T18:10:00Z",
        )
        store.cache_claim(task_id, claim.claim_id, claim.status, claim.lease_expires_at, claim.node_id, claim.agent_id, claim.session_id, claim.plan)
        store.update_task_state(task_id, state="claimed", active_claim_session_id=session_id)
        store.db.commit()

    def test_status_reports_uninitialized_envelope(self) -> None:
        exit_code, payload = self.invoke("status", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["bootstrap_state"], "uninitialized")
        self.assertIsNone(payload["error"])

    def test_read_requires_adoption_before_access(self) -> None:
        exit_code, payload = self.invoke("read", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home), "--as-of", "2026-06-19T13:00:00Z")

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_BOOTSTRAP_STATE")

    def test_status_and_read_upgrade_supported_stale_adopted_schema(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)

        downgrade_owner_local_tasks_schema(self.node_home / "node.sqlite3")
        exit_code, status_payload = self.invoke("status", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))

        self.assertEqual(exit_code, 0)
        self.assertEqual(status_payload["status"], "ok")
        self.assertEqual(status_payload["data"]["bootstrap_state"], "adopted")
        self._assert_owner_local_schema_upgraded()

        downgrade_owner_local_tasks_schema(self.node_home / "node.sqlite3")
        exit_code, read_payload = self.invoke(
            "read",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:00:00Z",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(read_payload["status"], "ok")
        self.assertEqual(read_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(read_payload["data"]["entrypoint"]["project_id"], adopted.adopted_project["project_id"])
        self._assert_owner_local_schema_upgraded()

    def test_current_returns_adopted_project_summary(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_ready_tasks(adopted.adopted_project["project_id"], count=3)

        exit_code, payload = self.invoke(
            "current",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
            "--ready-limit",
            "2",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(payload["data"]["adopted_project"], adopted.adopted_project)
        self.assertEqual(payload["data"]["as_of"], "2026-06-19T13:45:00Z")
        self.assertEqual(payload["data"]["entrypoint"]["project_id"], adopted.adopted_project["project_id"])
        self.assertEqual(payload["data"]["entrypoint"]["generated_at"], "2026-06-19T13:45:00Z")
        self.assertEqual(payload["data"]["sync_status"]["project_id"], adopted.adopted_project["project_id"])
        self.assertTrue(payload["data"]["sync_status"]["degraded"])
        self.assertEqual(payload["data"]["ready_tasks"]["index_name"], "ready")
        self.assertEqual(payload["data"]["ready_tasks"]["limit"], 2)
        self.assertEqual(len(payload["data"]["ready_tasks"]["tasks"]), 2)

    def test_current_upgrades_supported_stale_adopted_schema_before_runtime_reads(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_ready_tasks(adopted.adopted_project["project_id"], count=1)
        downgrade_owner_local_tasks_schema(self.node_home / "node.sqlite3")

        exit_code, payload = self.invoke(
            "current",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
            "--ready-limit",
            "1",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["adopted_project"], adopted.adopted_project)
        self.assertEqual(len(payload["data"]["ready_tasks"]["tasks"]), 1)
        self._assert_owner_local_schema_upgraded()

    def test_current_reports_schema_compatibility_error_for_unsupported_owner_local_drift(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        bootstrap.adopt_repo(interactive=False)

        write_incompatible_owner_local_schema(self.node_home / "node.sqlite3", user_version=99, include_project_id=True)
        exit_code, payload = self.invoke(
            "current",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "LOCAL_SCHEMA_COMPATIBILITY_ERROR")

    def test_current_reports_schema_compatibility_error_for_unsafe_owner_local_drift(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        bootstrap.adopt_repo(interactive=False)

        write_incompatible_owner_local_schema(self.node_home / "node.sqlite3", user_version=0, include_project_id=False)
        exit_code, payload = self.invoke(
            "current",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "LOCAL_SCHEMA_COMPATIBILITY_ERROR")

    def test_current_defaults_as_of_to_normalized_utc_timestamp(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_ready_tasks(adopted.adopted_project["project_id"], count=1)

        frozen_now = datetime(2026, 6, 19, 18, 5, 7, 123456, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            exit_code, payload = self.invoke(
                "current",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["as_of"], "2026-06-19T18:05:07Z")
        self.assertEqual(payload["data"]["entrypoint"]["generated_at"], "2026-06-19T18:05:07Z")

    def test_tasks_ready_returns_adopted_ready_queue(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_ready_tasks(adopted.adopted_project["project_id"], count=3)

        exit_code, payload = self.invoke(
            "tasks-ready",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
            "--limit",
            "2",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(payload["data"]["adopted_project"], adopted.adopted_project)
        self.assertEqual(payload["data"]["index_name"], "ready")
        self.assertEqual(payload["data"]["as_of"], "2026-06-19T13:45:00Z")
        self.assertEqual(payload["data"]["count"], 2)
        self.assertEqual(payload["data"]["limit"], 2)
        self.assertEqual(len(payload["data"]["tasks"]), 2)

    def test_tasks_ready_defaults_as_of_to_normalized_utc_timestamp(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_ready_tasks(adopted.adopted_project["project_id"], count=1)

        frozen_now = datetime(2026, 6, 19, 18, 5, 7, 123456, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            exit_code, payload = self.invoke(
                "tasks-ready",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["as_of"], "2026-06-19T18:05:07Z")

    def test_tasks_ready_rejects_non_positive_limit(self) -> None:
        completed = self.invoke_subprocess_raw(
            "tasks-ready",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--limit",
            "0",
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("positive integer", payload["error"]["message"])

    def test_tasks_claim_claims_ready_task_with_generated_lease_fields(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_ready_tasks(adopted.adopted_project["project_id"], count=1)

        frozen_now = datetime(2026, 6, 19, 18, 5, 7, 123456, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            exit_code, payload = self.invoke(
                "tasks-claim",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--task-id",
                "tsk_ready_0",
                "--plan",
                "Implement the task",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "claimed")
        self.assertEqual(payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(payload["data"]["adopted_project"], adopted.adopted_project)
        self.assertEqual(payload["data"]["task_id"], "tsk_ready_0")
        self.assertEqual(payload["data"]["lease_started_at"], "2026-06-19T18:05:07Z")
        self.assertEqual(payload["data"]["lease_expires_at"], "2026-06-19T18:10:07Z")
        self.assertEqual(payload["data"]["state"], "claimed")
        self.assertEqual(payload["data"]["plan"], "Implement the task")
        self.assertTrue(payload["data"]["claim_id"].startswith("clm_"))

        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        self.assertEqual(store.get_task("tsk_ready_0")["state"], "claimed")
        cached_claim = store.get_cached_claim("tsk_ready_0")
        self.assertIsNotNone(cached_claim)
        self.assertEqual(cached_claim["plan"], "Implement the task")

    def test_tasks_claim_rejects_missing_task_id(self) -> None:
        completed = self.invoke_subprocess_raw(
            "tasks-claim",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--plan",
            "Implement the task",
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("--task-id", payload["error"]["message"])

    def test_tasks_claim_rejects_non_positive_lease_minutes(self) -> None:
        completed = self.invoke_subprocess_raw(
            "tasks-claim",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--task-id",
            "tsk_ready_0",
            "--plan",
            "Implement the task",
            "--lease-minutes",
            "0",
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("positive integer", payload["error"]["message"])

    def test_tasks_claim_rejects_non_ready_task(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        store.create_audit("aud_blocked", adopted.adopted_project["project_id"], "published", "Blocked audit", "Audit body")
        store.create_task("tsk_blocked", adopted.adopted_project["project_id"], "aud_blocked", "blocked", "high", "low", "low", "feature", "Blocked task", blocked_reason="awaiting input", blocked_evidence="artifact://blocked", blocked_next_step="wait")
        store.db.commit()

        exit_code, payload = self.invoke(
            "tasks-claim",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--task-id",
            "tsk_blocked",
            "--plan",
            "Implement the task",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_TASK_STATE")
        self.assertIn("only ready tasks can be claimed", payload["error"]["message"])

    def test_tasks_start_reuses_existing_lifecycle_task(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_lifecycle_task(
            adopted.adopted_project["project_id"],
            task_id="tsk_lifecycle_ready",
            audit_id="aud_lifecycle_ready",
            lifecycle_key="lifecycle://cli/reuse",
        )

        frozen_now = datetime(2026, 6, 19, 18, 15, 0, 654321, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            exit_code, payload = self.invoke(
                "tasks-start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://cli/reuse",
                "--plan",
                "Resume lifecycle work",
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(payload["data"]["adopted_project"], adopted.adopted_project)
        self.assertEqual(payload["data"]["task_id"], "tsk_lifecycle_ready")
        self.assertEqual(payload["data"]["state"], "in_progress")
        self.assertFalse(payload["data"]["created_task"])
        self.assertEqual(payload["data"]["lease_started_at"], "2026-06-19T18:15:00Z")

    def test_tasks_start_rejects_lifecycle_task_claimed_by_another_session(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_lifecycle_task(
            adopted.adopted_project["project_id"],
            task_id="tsk_lifecycle_claimed",
            audit_id="aud_lifecycle_claimed",
            lifecycle_key="lifecycle://cli/claimed-conflict",
        )
        self._seed_active_claim_for_task(
            task_id="tsk_lifecycle_claimed",
            session_id="sess-other-owner",
            plan="Other session is already working",
        )

        exit_code, payload = self.invoke(
            "tasks-start",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lifecycle-key",
            "lifecycle://cli/claimed-conflict",
            "--plan",
            "Attempt conflicting lifecycle start",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "CLAIM_CONFLICT")
        self.assertIn("owned by another session", payload["error"]["message"])

    def test_audit_create_and_publish_commands_return_json_envelopes(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)

        create_exit_code, create_payload = self.invoke(
            "audit-create",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T18:30:00Z",
            "--title",
            "CLI brief audit",
            "--content",
            "CLI audit body",
        )

        self.assertEqual(create_exit_code, 0)
        self.assertEqual(create_payload["status"], "accepted")
        self.assertEqual(create_payload["data"]["state"], "draft")

        publish_exit_code, publish_payload = self.invoke(
            "audit-publish",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--audit-id",
            create_payload["data"]["audit_id"],
        )

        self.assertEqual(publish_exit_code, 0)
        self.assertEqual(publish_payload["status"], "accepted")
        self.assertEqual(publish_payload["data"]["state"], "published")

        frozen_now = datetime(2026, 6, 19, 18, 35, 0, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            start_exit_code, start_payload = self.invoke(
                "tasks-start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://cli/public-compose",
                "--plan",
                "Compose public audit lifecycle start",
                "--origin-audit-id",
                publish_payload["data"]["audit_id"],
                "--description",
                "Lifecycle-created task from public audit",
                "--priority",
                "high",
                "--effort",
                "low",
                "--risk",
                "low",
                "--task-type",
                "ops",
                "--justification-json",
                '{"summary":"Create lifecycle task","evidence_refs":["artifact://cli/public-compose"],"expected_impact":"Track public lifecycle start"}',
                "--execution-context-json",
                json.dumps({"project_id": adopted.adopted_project["project_id"], "steps": ["audit_publish", "claim", "start"]}, sort_keys=True),
            )

        self.assertEqual(start_exit_code, 0)
        self.assertEqual(start_payload["status"], "accepted")
        self.assertTrue(start_payload["data"]["created_task"])
        self.assertEqual(start_payload["data"]["origin_audit_id"], publish_payload["data"]["audit_id"])

    def test_tasks_start_rejects_draft_origin_audit(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)

        create_exit_code, create_payload = self.invoke(
            "audit-create",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T18:30:00Z",
            "--title",
            "Draft CLI audit",
            "--content",
            "CLI audit body",
        )
        self.assertEqual(create_exit_code, 0)

        frozen_now = datetime(2026, 6, 19, 18, 35, 0, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            exit_code, payload = self.invoke(
                "tasks-start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://cli/draft-origin",
                "--plan",
                "Reject draft origin",
                "--origin-audit-id",
                create_payload["data"]["audit_id"],
                "--description",
                "Should fail",
                "--priority",
                "high",
                "--effort",
                "low",
                "--risk",
                "low",
                "--task-type",
                "ops",
                "--justification-json",
                '{"summary":"Reject draft audit origin","evidence_refs":["artifact://cli/draft-origin"],"expected_impact":"Prevent draft audit lifecycle create"}',
                "--execution-context-json",
                json.dumps({"project_id": adopted.adopted_project["project_id"]}, sort_keys=True),
            )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_TASK_STATE")
        self.assertIn("published origin audit", payload["error"]["message"])

    def test_audit_publish_rejects_foreign_project_audit(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        store.upsert_project("prj_other", adopted.adopted_project["workspace_id"], adopted.local_node_id, "project://other", "Other")
        store.create_audit("aud_foreign", "prj_other", "draft", "Foreign audit", "Body")
        store.db.commit()

        exit_code, payload = self.invoke(
            "audit-publish",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--audit-id",
            "aud_foreign",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_TASK_STATE")
        self.assertIn("adopted project", payload["error"]["message"])

    def test_tasks_start_creates_lifecycle_task_from_audit_seed(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        store.create_audit("aud_create", adopted.adopted_project["project_id"], "published", "Create audit", "Audit body")
        store.db.commit()

        exit_code, payload = self.invoke(
            "tasks-start",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lifecycle-key",
            "lifecycle://cli/create",
            "--plan",
            "Create lifecycle work",
            "--origin-audit-id",
            "aud_create",
            "--description",
            "Lifecycle-created task",
            "--priority",
            "high",
            "--effort",
            "low",
            "--risk",
            "low",
            "--task-type",
            "ops",
            "--justification-json",
            '{"summary":"Create lifecycle task","evidence_refs":["artifact://cli/create"],"expected_impact":"Track start automation"}',
            "--execution-context-json",
            json.dumps({"project_id": adopted.adopted_project["project_id"], "steps": ["claim", "work"]}, sort_keys=True),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertTrue(payload["data"]["created_task"])
        created = store.get_task(payload["data"]["task_id"])
        self.assertEqual(created["lifecycle_key"], "lifecycle://cli/create")
        self.assertEqual(created["state"], "in_progress")

    def test_tasks_start_rejects_cross_project_execution_context(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        store.create_audit("aud_cross", adopted.adopted_project["project_id"], "published", "Cross audit", "Audit body")
        store.db.commit()

        exit_code, payload = self.invoke(
            "tasks-start",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lifecycle-key",
            "lifecycle://cli/cross",
            "--plan",
            "Reject cross-project lifecycle work",
            "--origin-audit-id",
            "aud_cross",
            "--description",
            "Should fail",
            "--priority",
            "high",
            "--effort",
            "low",
            "--risk",
            "low",
            "--task-type",
            "ops",
            "--justification-json",
            '{"summary":"Reject bad context","evidence_refs":["artifact://cli/cross"],"expected_impact":"Prevent cross-project mutation"}',
            "--execution-context-json",
            '{"source_project_id":"prj_other"}',
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_TASK_STATE")
        self.assertIn("must stay within the adopted project", payload["error"]["message"])

    def test_tasks_finish_closes_lifecycle_task_as_done(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_lifecycle_task(
            adopted.adopted_project["project_id"],
            task_id="tsk_lifecycle_finish_done",
            audit_id="aud_lifecycle_finish_done",
            lifecycle_key="lifecycle://cli/finish-done",
        )

        frozen_now = datetime(2026, 6, 19, 18, 20, 0, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            start_exit_code, _start_payload = self.invoke(
                "tasks-start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://cli/finish-done",
                "--plan",
                "Resume lifecycle work",
            )
        self.assertEqual(start_exit_code, 0)

        exit_code, payload = self.invoke(
            "tasks-finish",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lifecycle-key",
            "lifecycle://cli/finish-done",
            "--outcome",
            "done",
            "--as-of",
            "2026-06-19T18:24:00Z",
            "--done-result",
            "Lifecycle work completed",
            "--done-artifacts",
            "artifact://cli/finish-done",
            "--done-references",
            "ref://cli/finish-done",
            "--done-expected-impact",
            "Close the lifecycle task",
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["data"]["state"], "done")
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        self.assertEqual(store.get_task("tsk_lifecycle_finish_done")["done_result"], "Lifecycle work completed")
        self.assertIsNone(store.get_cached_claim("tsk_lifecycle_finish_done"))

    def test_tasks_finish_rejects_expired_claim(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_lifecycle_task(
            adopted.adopted_project["project_id"],
            task_id="tsk_lifecycle_finish_expired",
            audit_id="aud_lifecycle_finish_expired",
            lifecycle_key="lifecycle://cli/finish-expired",
        )

        frozen_now = datetime(2026, 6, 19, 18, 20, 0, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            start_exit_code, _start_payload = self.invoke(
                "tasks-start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://cli/finish-expired",
                "--plan",
                "Resume lifecycle work",
            )
        self.assertEqual(start_exit_code, 0)

        exit_code, payload = self.invoke(
            "tasks-finish",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lifecycle-key",
            "lifecycle://cli/finish-expired",
            "--outcome",
            "blocked",
            "--as-of",
            "2026-06-19T18:26:00Z",
            "--blocked-reason",
            "Lease expired before closeout",
            "--blocked-evidence",
            "artifact://cli/finish-expired",
            "--blocked-next-step",
            "Reconcile the lifecycle task again",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "CLAIM_EXPIRED")
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        self.assertEqual(store.get_task("tsk_lifecycle_finish_expired")["state"], "ready")

    def test_tasks_finish_rejects_missing_explicit_metadata_before_runtime(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self._seed_lifecycle_task(
            adopted.adopted_project["project_id"],
            task_id="tsk_lifecycle_finish_missing_metadata",
            audit_id="aud_lifecycle_finish_missing_metadata",
            lifecycle_key="lifecycle://cli/finish-missing-metadata",
        )

        frozen_now = datetime(2026, 6, 19, 18, 20, 0, tzinfo=timezone.utc)
        with patch("runtime.node.current.datetime") as mocked_datetime:
            mocked_datetime.now.return_value = frozen_now
            mocked_datetime.fromisoformat.side_effect = datetime.fromisoformat
            start_exit_code, _start_payload = self.invoke(
                "tasks-start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://cli/finish-missing-metadata",
                "--plan",
                "Resume lifecycle work",
            )
        self.assertEqual(start_exit_code, 0)

        exit_code, payload = self.invoke(
            "tasks-finish",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lifecycle-key",
            "lifecycle://cli/finish-missing-metadata",
            "--outcome",
            "done",
            "--as-of",
            "2026-06-19T18:24:00Z",
            "--done-result",
            "Lifecycle work completed",
            "--done-artifacts",
            "artifact://cli/finish-missing-metadata",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("explicit finish metadata", payload["error"]["message"])

    def test_help_uses_english_lifecycle_terms(self) -> None:
        completed = self.invoke_subprocess_raw("--help")

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Owner-local adopted-project JSON CLI", completed.stdout)
        self.assertIn("audit-create", completed.stdout)
        self.assertIn("audit-publish", completed.stdout)
        self.assertIn("--title", completed.stdout)
        self.assertIn("--audit-id", completed.stdout)
        self.assertIn("tasks-start", completed.stdout)
        self.assertIn("tasks-finish", completed.stdout)
        self.assertIn("--lifecycle-key", completed.stdout)
        self.assertIn("--origin-audit-id", completed.stdout)
        self.assertIn("--done-result", completed.stdout)
        self.assertIn("--blocked-reason", completed.stdout)
        self.assertIn("Reconcile owner-local same-project lifecycle work", completed.stdout)
        self.assertIn("Close owner-local adopted lifecycle work", completed.stdout)

    def test_missing_command_returns_json_error_envelope(self) -> None:
        completed = self.invoke_subprocess_raw("--repo-root", str(self.repo_root), "--node-home", str(self.node_home))

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("required", payload["error"]["message"])

    def test_unknown_command_returns_json_error_envelope(self) -> None:
        completed = self.invoke_subprocess_raw(
            "destroy",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("invalid choice", payload["error"]["message"])

    def test_status_waits_with_stderr_status_and_json_stdout(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock,
            args=(str(self.repo_root), str(self.node_home), "init", 0.3, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        completed = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lock-timeout-seconds",
            "1.0",
            "--non-interactive",
        )

        holder.join(timeout=2.0)
        self.assertEqual(completed.returncode, 0)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("Waiting for bootstrap lock before running status", completed.stderr)
        self.assertNotIn('"status": "error"', completed.stdout)

    def test_verbose_wait_status_includes_owner_diagnostics(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock,
            args=(str(self.repo_root), str(self.node_home), "adopt", 0.3, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        completed = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lock-timeout-seconds",
            "1.0",
            "--non-interactive",
            "--verbose",
        )

        holder.join(timeout=2.0)
        self.assertEqual(completed.returncode, 0)
        self.assertIn("Diagnostics:", completed.stderr)
        self.assertIn("pid=", completed.stderr)
        self.assertIn("liveness=alive", completed.stderr)

    def test_timeout_error_surfaces_json_details_and_stderr_diagnostics(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock,
            args=(str(self.repo_root), str(self.node_home), "status", 0.5, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        completed = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lock-timeout-seconds",
            "0.1",
            "--non-interactive",
        )

        holder.join(timeout=2.0)
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "BOOTSTRAP_LOCK_TIMEOUT")
        self.assertEqual(payload["error"]["details"]["owner_node_id"], NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home).local_node_id)
        self.assertEqual(payload["error"]["details"]["command"], "status")
        self.assertEqual(payload["error"]["details"]["liveness"], "alive")
        self.assertIn("timed out waiting for bootstrap lock", completed.stderr)
        self.assertIn("recovery_hint=", completed.stderr)

    def test_stale_lock_prompt_and_recover_flag_map_through_cli(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        self.node_home.mkdir(parents=True, exist_ok=True)
        bootstrap.lock_path.write_text(
            json.dumps(
                {
                    "owner_node_id": bootstrap.local_node_id,
                    "pid": 999999,
                    "command": "init",
                    "acquired_at": "2026-06-19T00:00:00Z",
                    "last_seen_at": "2026-06-19T00:00:00Z",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        failed = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--non-interactive",
        )

        failed_payload = json.loads(failed.stdout)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed_payload["error"]["code"], "BOOTSTRAP_LOCK_SUSPECT")
        self.assertEqual(failed_payload["error"]["details"]["command"], "init")
        self.assertEqual(failed_payload["error"]["details"]["liveness"], "dead")
        self.assertIn("bootstrap lock requires explicit recovery", failed.stderr)

        prompted = subprocess.run(
            [
                "python3",
                str(CLI_MODULE_PATH),
                "status",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
            ],
            check=False,
            capture_output=True,
            text=True,
            input="y\n",
        )

        prompted_payload = json.loads(prompted.stdout)
        self.assertEqual(prompted.returncode, 0)
        self.assertEqual(prompted_payload["status"], "ok")
        self.assertIn("Recover it now?", prompted.stderr)

        bootstrap.lock_path.write_text(
            json.dumps(
                {
                    "owner_node_id": bootstrap.local_node_id,
                    "pid": 999999,
                    "command": "init",
                    "acquired_at": "2026-06-19T00:00:00Z",
                    "last_seen_at": "2026-06-19T00:00:00Z",
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        recovered = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--non-interactive",
            "--recover-stale-lock",
        )

        recovered_payload = json.loads(recovered.stdout)
        self.assertEqual(recovered.returncode, 0)
        self.assertEqual(recovered_payload["status"], "ok")

    def test_old_active_lock_owner_surfaces_suspect_error_through_cli(self) -> None:
        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock_with_age,
            args=(str(self.repo_root), str(self.node_home), "adopt", 0.5, 31.0, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        completed = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lock-timeout-seconds",
            "1.0",
            "--non-interactive",
        )

        holder.join(timeout=2.0)
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "BOOTSTRAP_LOCK_SUSPECT")
        self.assertEqual(payload["error"]["details"]["command"], "adopt")
        self.assertEqual(payload["error"]["details"]["liveness"], "alive")
        self.assertGreaterEqual(payload["error"]["details"]["lock_age_seconds"], 30.0)
        self.assertIn("bootstrap lock requires explicit recovery", completed.stderr)

    def test_negative_lock_timeout_is_rejected_as_invalid_arguments(self) -> None:
        completed = self.invoke_subprocess_raw(
            "status",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lock-timeout-seconds",
            "-1",
        )

        self.assertEqual(completed.returncode, 1)
        self.assertEqual(completed.stderr, "")
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("greater than or equal to 0", payload["error"]["message"])
        self.assertFalse(self.node_home.exists())

    def test_adopt_timeout_leaves_persisted_state_untouched(self) -> None:
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        initialized = bootstrap.open_or_init()

        context = multiprocessing.get_context("fork")
        ready_queue = context.Queue()
        holder = context.Process(
            target=hold_bootstrap_lock,
            args=(str(self.repo_root), str(self.node_home), "status", 0.5, ready_queue),
        )
        holder.start()
        self.addCleanup(lambda: holder.is_alive() and holder.terminate())
        self.assertEqual(ready_queue.get(timeout=2.0), "locked")

        completed = self.invoke_subprocess_raw(
            "adopt",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--lock-timeout-seconds",
            "0.1",
            "--non-interactive",
        )

        holder.join(timeout=2.0)
        self.assertFalse(holder.is_alive())
        self.assertEqual(completed.returncode, 1)
        payload = json.loads(completed.stdout)
        self.assertEqual(payload["error"]["code"], "BOOTSTRAP_LOCK_TIMEOUT")

        persisted = bootstrap.status(interactive=False)
        self.assertEqual(persisted.state, initialized.state)
        self.assertIsNone(persisted.adopted_project)

        store = NodeStore.from_file(bootstrap.node_db_path)
        self.addCleanup(store.close)
        expected_metadata = bootstrap._build_adopted_project(self.repo_root)
        self.assertIsNone(store.get_workspace(expected_metadata["workspace_id"]))
        self.assertIsNone(store.get_project(expected_metadata["project_id"]))

    def test_read_returns_adopted_repo_entrypoint_without_persisting_cache(self) -> None:
        init_exit, init_payload = self.invoke("init", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))
        adopt_exit, adopt_payload = self.invoke("adopt", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))
        read_exit, read_payload = self.invoke("read", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home), "--as-of", "2026-06-19T13:00:00Z")

        self.assertEqual((init_exit, adopt_exit, read_exit), (0, 0, 0))
        self.assertEqual(init_payload["status"], "accepted")
        self.assertEqual(adopt_payload["status"], "accepted")
        self.assertEqual(read_payload["status"], "ok")
        self.assertEqual(read_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(read_payload["data"]["project"]["repo_root"], str(self.repo_root.resolve()))
        self.assertEqual(read_payload["data"]["entrypoint"]["project_id"], adopt_payload["data"]["adopted_project"]["project_id"])
        self.assertEqual(read_payload["data"]["entrypoint"]["generated_at"], "2026-06-19T13:00:00Z")

        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        state = bootstrap.require_adopted()
        store = NodeStore.from_file(state.node_db_path)
        self.addCleanup(store.close)
        self.assertIsNone(store.get_project_entrypoint(state.adopted_project["project_id"]))

    def test_reopen_persists_adoption_and_read_payloads_are_deterministic(self) -> None:
        self.invoke("init", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))
        adopt_exit, adopt_payload = self.invoke("adopt", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))
        status_exit, status_payload = self.invoke("status", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))
        first_read_exit, first_read_payload = self.invoke("read", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home), "--as-of", "2026-06-19T13:30:00Z")
        second_read_exit, second_read_payload = self.invoke("read", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home), "--as-of", "2026-06-19T13:30:00Z")

        self.assertEqual((adopt_exit, status_exit, first_read_exit, second_read_exit), (0, 0, 0, 0))
        self.assertEqual(status_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(status_payload["data"]["adopted_project"], adopt_payload["data"]["adopted_project"])
        self.assertEqual(first_read_payload, second_read_payload)
        self.assertEqual(first_read_payload["data"]["entrypoint"]["generated_at"], "2026-06-19T13:30:00Z")
        self.assertEqual(first_read_payload["data"]["entrypoint"]["project_id"], adopt_payload["data"]["adopted_project"]["project_id"])
        self.assertEqual(first_read_payload["data"]["entrypoint"]["project_name"], self.repo_root.name)
        self.assertEqual(
            first_read_payload["data"]["entrypoint"]["queue_counts"],
            {"ready": 0, "blocked": 0, "done": 0, "critical": 0, "expired_claim": 0},
        )

        reopened = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home).require_adopted()
        self.assertEqual(reopened.adopted_project, adopt_payload["data"]["adopted_project"])

    def test_sequential_cli_flow_works_across_real_processes(self) -> None:
        status_exit, status_payload = self.invoke_subprocess(
            "status", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home)
        )
        init_exit, init_payload = self.invoke_subprocess(
            "init", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home)
        )
        adopt_exit, adopt_payload = self.invoke_subprocess(
            "adopt", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home)
        )
        read_exit, read_payload = self.invoke_subprocess(
            "read",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
        )

        self.assertEqual((status_exit, init_exit, adopt_exit, read_exit), (0, 0, 0, 0))
        self.assertEqual(status_payload["status"], "ok")
        self.assertEqual(status_payload["data"]["bootstrap_state"], "uninitialized")
        self.assertEqual(init_payload["status"], "accepted")
        self.assertEqual(init_payload["data"]["bootstrap_state"], "initialized")
        self.assertEqual(adopt_payload["status"], "accepted")
        self.assertEqual(adopt_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(read_payload["status"], "ok")
        self.assertEqual(read_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(read_payload["data"]["project"], adopt_payload["data"]["adopted_project"])
        self.assertEqual(read_payload["data"]["entrypoint"]["project_id"], adopt_payload["data"]["adopted_project"]["project_id"])
        self.assertEqual(read_payload["data"]["entrypoint"]["generated_at"], "2026-06-19T13:45:00Z")

    def test_require_adopted_rejects_tampered_manifest_node_db_path(self) -> None:
        self.invoke("init", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))
        self.invoke("adopt", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))

        manifest_path = self.node_home / "bootstrap.json"
        manifest = json.loads(manifest_path.read_text())
        tampered = deepcopy(manifest)
        tampered["node_db_path"] = str((self.repo_root / ".." / "escaped.sqlite3").resolve())
        manifest_path.write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")

        exit_code, payload = self.invoke(
            "read",
            "--repo-root",
            str(self.repo_root),
            "--node-home",
            str(self.node_home),
            "--as-of",
            "2026-06-19T13:45:00Z",
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_BOOTSTRAP_STATE")
        self.assertIn("unexpected node database path", payload["error"]["message"])

    def test_init_rejects_tampered_manifest_without_creating_expected_db(self) -> None:
        self.node_home.mkdir(parents=True, exist_ok=True)
        escaped_db_path = (self.repo_root / ".." / "escaped.sqlite3").resolve()
        manifest_path = self.node_home / "bootstrap.json"
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        manifest_path.write_text(
            json.dumps(
                {
                    "state": "initialized",
                    "local_node_id": bootstrap.local_node_id,
                    "node_home": str(self.node_home.resolve()),
                    "node_db_path": str(escaped_db_path),
                    "adopted_project": None,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

        exit_code, payload = self.invoke("init", "--repo-root", str(self.repo_root), "--node-home", str(self.node_home))

        self.assertEqual(exit_code, 1)
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_BOOTSTRAP_STATE")
        self.assertFalse((self.node_home / "node.sqlite3").exists())
        self.assertFalse(escaped_db_path.exists())
