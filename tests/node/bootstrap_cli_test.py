import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from copy import deepcopy
from pathlib import Path

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError


CLI_MODULE_PATH = Path(__file__).resolve().parents[2] / "scripts" / "capiforge_cli.py"


def load_cli_module():
    spec = importlib.util.spec_from_file_location("capiforge_cli", CLI_MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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
