import importlib.util
import io
import json
import multiprocessing
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from runtime.node.bootstrap import BootstrapLockInfo, NodeBootstrap
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError


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
