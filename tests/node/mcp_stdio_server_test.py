import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore


REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_console_script_entrypoint() -> str:
    pyproject_path = REPO_ROOT / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text())
    return pyproject["project"]["scripts"]["capiforge"]


def _materialize_console_script() -> Path:
    install_root = Path(tempfile.mkdtemp(prefix="capiforge-console-script-"))
    command_path = install_root / "capiforge"
    entrypoint = _load_console_script_entrypoint()
    module_name, function_name = entrypoint.split(":", maxsplit=1)
    command_path.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python3",
                "from __future__ import annotations",
                "",
                "from importlib import import_module",
                "from pathlib import Path",
                "import sys",
                "",
                f'REPO_ROOT = Path(r"{REPO_ROOT}")',
                "if str(REPO_ROOT) not in sys.path:",
                "    sys.path.insert(0, str(REPO_ROOT))",
                "",
                f'main = getattr(import_module("{module_name}"), "{function_name}")',
                "raise SystemExit(main())",
                "",
            ]
        )
    )
    command_path.chmod(0o755)
    return command_path


class MCPStdioServerSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.command_path = _materialize_console_script()

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "command_path"):
            install_root = cls.command_path.parent.parent
            shutil.rmtree(install_root, ignore_errors=True)

    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.repo_root = Path(self.tempdir.name) / "repo"
        self.repo_root.mkdir(parents=True, exist_ok=True)
        self.node_home = self.repo_root / ".capiforge" / "node"
        bootstrap = NodeBootstrap(repo_root=self.repo_root, node_home=self.node_home)
        bootstrap.open_or_init(interactive=False)
        adopted = bootstrap.adopt_repo(interactive=False)
        self.project_id = adopted.adopted_project["project_id"]

        store = NodeStore.from_file(bootstrap.node_db_path)
        self.addCleanup(store.close)
        store.create_audit("aud_ready", self.project_id, "published", "Ready audit", "Audit body")
        store.create_task("tsk_ready", self.project_id, "aud_ready", "ready", "high", "low", "low", "feature", "Ready task")
        store.db.commit()

        self.process = subprocess.Popen(
            [
                str(self.command_path),
                "mcp",
                "serve",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        self.addCleanup(self._stop_process)

    def _stop_process(self) -> None:
        if self.process.stdin and not self.process.stdin.closed:
            self.process.stdin.close()
        if self.process.poll() is None:
            self.process.terminate()
            self.process.wait(timeout=5)
        if self.process.stdout and not self.process.stdout.closed:
            self.process.stdout.close()
        if self.process.stderr and not self.process.stderr.closed:
            self.process.stderr.close()

    def _request(self, message_id: int, method: str, params: dict | None = None) -> dict:
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        payload = {"jsonrpc": "2.0", "id": message_id, "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        self.assertTrue(line, f"expected response for {method}")
        return json.loads(line)

    def _notify(self, method: str, params: dict | None = None) -> None:
        assert self.process.stdin is not None
        payload = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        self.process.stdin.write(json.dumps(payload) + "\n")
        self.process.stdin.flush()

    def _tool_payload(self, response: dict) -> dict:
        self.assertIn("result", response)
        self.assertFalse(response["result"]["isError"])
        content = response["result"]["content"]
        self.assertEqual(content[0]["type"], "text")
        return json.loads(content[0]["text"])

    def test_stdio_server_supports_real_initialize_and_read_tool_flow(self) -> None:
        initialize = self._request(
            1,
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "unittest", "version": "1.0.0"},
            },
        )
        self.assertEqual(initialize["result"]["protocolVersion"], "2025-03-26")
        self.assertIn("tools", initialize["result"]["capabilities"])

        self._notify("notifications/initialized")

        tools = self._request(2, "tools/list")
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {"workspace_get_current", "project_entrypoint_get", "tasks_list_by_index", "sync_status"},
        )

        workspace_payload = self._tool_payload(
            self._request(3, "tools/call", {"name": "workspace_get_current", "arguments": {}})
        )
        self.assertEqual(workspace_payload["status"], "ok")
        self.assertEqual(workspace_payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(len(workspace_payload["data"]["workspace"]["projects"]), 1)

        entrypoint_payload = self._tool_payload(
            self._request(
                4,
                "tools/call",
                {
                    "name": "project_entrypoint_get",
                    "arguments": {"as_of": "2026-06-19T13:45:00Z"},
                },
            )
        )
        self.assertEqual(entrypoint_payload["status"], "ok")
        self.assertEqual(entrypoint_payload["data"]["entrypoint"]["project_id"], self.project_id)
        self.assertEqual(entrypoint_payload["data"]["entrypoint"]["generated_at"], "2026-06-19T13:45:00Z")

        tasks_payload = self._tool_payload(
            self._request(
                5,
                "tools/call",
                {
                    "name": "tasks_list_by_index",
                    "arguments": {
                        "index_name": "ready",
                        "as_of": "2026-06-19T13:45:00Z",
                        "limit": 10,
                    },
                },
            )
        )
        self.assertEqual(tasks_payload["status"], "ok")
        self.assertEqual(tasks_payload["data"]["tasks"][0]["task_id"], "tsk_ready")

        sync_payload = self._tool_payload(
            self._request(6, "tools/call", {"name": "sync_status", "arguments": {}})
        )
        self.assertEqual(sync_payload["status"], "ok")
        self.assertTrue(sync_payload["data"]["degraded"])
        self.assertEqual(sync_payload["data"]["pending_routes"], 0)

    def test_installed_command_reports_mcp_help_surface(self) -> None:
        result = subprocess.run(
            [str(self.command_path), "mcp", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("usage: capiforge mcp", result.stdout)
        self.assertIn("serve", result.stdout)
        self.assertIn("Start the local MCP stdio server", result.stdout)

    def test_installed_command_root_help_lists_bootstrap_commands(self) -> None:
        result = subprocess.run(
            [str(self.command_path), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("init", result.stdout)
        self.assertIn("adopt", result.stdout)
        self.assertIn("status", result.stdout)
        self.assertIn("read", result.stdout)
        self.assertIn("mcp", result.stdout)

    def test_installed_command_supports_bootstrap_flow(self) -> None:
        fresh_root = Path(self.tempdir.name) / "fresh-repo"
        fresh_root.mkdir(parents=True, exist_ok=True)
        fresh_node_home = fresh_root / ".capiforge" / "node"

        status = subprocess.run(
            [str(self.command_path), "status", "--repo-root", str(fresh_root), "--node-home", str(fresh_node_home)],
            check=False,
            capture_output=True,
            text=True,
        )
        init = subprocess.run(
            [str(self.command_path), "init", "--repo-root", str(fresh_root), "--node-home", str(fresh_node_home)],
            check=False,
            capture_output=True,
            text=True,
        )
        adopt = subprocess.run(
            [str(self.command_path), "adopt", "--repo-root", str(fresh_root), "--node-home", str(fresh_node_home)],
            check=False,
            capture_output=True,
            text=True,
        )
        read = subprocess.run(
            [
                str(self.command_path),
                "read",
                "--repo-root",
                str(fresh_root),
                "--node-home",
                str(fresh_node_home),
                "--as-of",
                "2026-06-19T13:45:00Z",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        status_payload = json.loads(status.stdout)
        init_payload = json.loads(init.stdout)
        adopt_payload = json.loads(adopt.stdout)
        read_payload = json.loads(read.stdout)

        self.assertEqual((status.returncode, init.returncode, adopt.returncode, read.returncode), (0, 0, 0, 0))
        self.assertEqual(status_payload["data"]["bootstrap_state"], "uninitialized")
        self.assertEqual(init_payload["data"]["bootstrap_state"], "initialized")
        self.assertEqual(adopt_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(read_payload["data"]["bootstrap_state"], "adopted")
        self.assertEqual(read_payload["data"]["project"], adopt_payload["data"]["adopted_project"])

    def test_pyproject_declares_runtime_cli_console_script(self) -> None:
        self.assertEqual(_load_console_script_entrypoint(), "runtime.cli:main")
