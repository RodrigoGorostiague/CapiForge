import json
import os
import sqlite3
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path

from runtime.coordinator.claims import ClaimRegistry
from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore
from runtime.shared.ids import ActorIdentity, derive_node_proof


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


class MCPStdioServerSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.command_path = _materialize_console_script()

    @classmethod
    def tearDownClass(cls) -> None:
        if hasattr(cls, "command_path"):
            install_root = cls.command_path.parent
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
        store.create_audit("aud_lifecycle", self.project_id, "published", "Lifecycle audit", "Audit body")
        store.create_task(
            "tsk_lifecycle_ready",
            self.project_id,
            "aud_lifecycle",
            "ready",
            "high",
            "low",
            "low",
            "ops",
            "Lifecycle ready task",
            justification_json=json.dumps(
                {
                    "summary": "Existing lifecycle task",
                    "evidence_refs": ["lifecycle://stdio/reuse"],
                    "expected_impact": "Allow reuse",
                },
                sort_keys=True,
            ),
            execution_context_json=json.dumps({"project_id": self.project_id}, sort_keys=True),
            lifecycle_key="lifecycle://stdio/reuse",
        )
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
        self.assertIn("owner-local node tools", initialize["result"]["instructions"])

        self._notify("notifications/initialized")

        tools = self._request(2, "tools/list")
        tool_descriptions = {tool["name"]: tool["description"] for tool in tools["result"]["tools"]}
        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        self.assertEqual(
            tool_names,
            {
                "audit_create_brief",
                "audit_publish",
                "workspace_get_current",
                "project_entrypoint_get",
                "tasks_list_by_index",
                "sync_status",
                "current_get",
                "tasks_ready_get",
                "tasks_claim",
                "tasks_transition",
                "tasks_release",
                "tasks_claim_renew",
                "tasks_reconcile_start",
                "tasks_reconcile_finish",
                "milestone_publish",
                "project_page_get",
                "project_page_upsert",
            },
        )
        self.assertEqual(
            tool_descriptions["audit_create_brief"],
            "Create a draft brief audit for the adopted project using the public owner-local surface.",
        )
        self.assertEqual(
            tool_descriptions["audit_publish"],
            "Publish a draft brief audit for the adopted project using the public owner-local surface.",
        )
        self.assertEqual(
            tool_descriptions["tasks_reconcile_start"],
            "Reconcile owner-local same-project lifecycle work into an adopted in-progress task, creating on miss only from a published same-project audit.",
        )
        self.assertEqual(
            tool_descriptions["tasks_reconcile_finish"],
            "Close owner-local adopted lifecycle work to done or blocked when the active claim is still valid and explicit finish metadata is supplied.",
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
        self.assertEqual({task["task_id"] for task in tasks_payload["data"]["tasks"]}, {"tsk_ready", "tsk_lifecycle_ready"})

        sync_payload = self._tool_payload(
            self._request(6, "tools/call", {"name": "sync_status", "arguments": {}})
        )
        self.assertEqual(sync_payload["status"], "ok")
        self.assertTrue(sync_payload["data"]["degraded"])
        self.assertEqual(sync_payload["data"]["pending_routes"], 0)

        current_payload = self._tool_payload(
            self._request(
                7,
                "tools/call",
                {
                    "name": "current_get",
                    "arguments": {"as_of": "2026-06-19T13:45:00Z", "ready_limit": 1},
                },
            )
        )
        self.assertEqual(current_payload["status"], "ok")
        self.assertEqual(current_payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(current_payload["data"]["as_of"], "2026-06-19T13:45:00Z")
        self.assertEqual(current_payload["data"]["ready_tasks"]["limit"], 1)
        self.assertEqual(len(current_payload["data"]["ready_tasks"]["tasks"]), 1)

        ready_payload = self._tool_payload(
            self._request(
                8,
                "tools/call",
                {
                    "name": "tasks_ready_get",
                    "arguments": {"as_of": "2026-06-19T13:45:00Z", "limit": 1},
                },
            )
        )
        self.assertEqual(ready_payload["status"], "ok")
        self.assertEqual(ready_payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(ready_payload["data"]["index_name"], "ready")
        self.assertEqual(ready_payload["data"]["as_of"], "2026-06-19T13:45:00Z")
        self.assertEqual(ready_payload["data"]["limit"], 1)
        self.assertEqual(ready_payload["data"]["count"], 1)
        self.assertEqual(len(ready_payload["data"]["tasks"]), 1)

        cli_current = subprocess.run(
            [
                str(self.command_path),
                "current",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--as-of",
                "2026-06-19T13:45:00Z",
                "--ready-limit",
                "1",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli_current.returncode, 0)
        self.assertEqual(current_payload["data"], json.loads(cli_current.stdout)["data"])

        cli_ready = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "ready",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--as-of",
                "2026-06-19T13:45:00Z",
                "--limit",
                "1",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli_ready.returncode, 0)
        self.assertEqual(ready_payload["data"], json.loads(cli_ready.stdout)["data"])

    def test_stdio_server_supports_tasks_claim_tool_flow(self) -> None:
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

        self._notify("notifications/initialized")

        claim_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "tasks_claim",
                    "arguments": {
                        "task_id": "tsk_ready",
                        "plan": "Implement the ready task",
                    },
                },
            )
        )
        self.assertEqual(claim_payload["status"], "claimed")
        self.assertEqual(claim_payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(claim_payload["data"]["task_id"], "tsk_ready")
        self.assertEqual(claim_payload["data"]["state"], "claimed")
        self.assertEqual(claim_payload["data"]["plan"], "Implement the ready task")

        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        try:
            store.create_task(
                "tsk_ready_cli",
                self.project_id,
                "aud_ready",
                "ready",
                "high",
                "low",
                "low",
                "feature",
                "CLI ready task",
            )
            store.db.commit()
        finally:
            store.close()

        cli_claim = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "claim",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--task-id",
                "tsk_ready_cli",
                "--plan",
                "Implement the ready task",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli_claim.returncode, 0)
        cli_payload = json.loads(cli_claim.stdout)
        self.assertEqual(cli_payload["status"], "claimed")
        self.assertEqual(set(claim_payload["data"].keys()), set(cli_payload["data"].keys()))
        self.assertEqual(cli_payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(cli_payload["data"]["task_id"], "tsk_ready_cli")
        self.assertEqual(cli_payload["data"]["state"], "claimed")
        self.assertEqual(cli_payload["data"]["plan"], "Implement the ready task")

        start_payload = self._tool_payload(
            self._request(
                4,
                "tools/call",
                {
                    "name": "tasks_transition",
                    "arguments": {
                        "task_id": "tsk_ready",
                        "requested_state": "in_progress",
                        "summary": "Begin active work on the claimed task",
                    },
                },
            )
        )
        self.assertEqual(start_payload["status"], "accepted")
        self.assertEqual(start_payload["data"]["task_id"], "tsk_ready")
        self.assertEqual(start_payload["data"]["previous_state"], "claimed")
        self.assertEqual(start_payload["data"]["state"], "in_progress")

        ready_after_claim = self._tool_payload(
            self._request(
                5,
                "tools/call",
                {
                    "name": "tasks_ready_get",
                    "arguments": {"as_of": claim_payload["data"]["lease_started_at"], "limit": 5},
                },
            )
        )
        self.assertEqual(ready_after_claim["status"], "ok")
        self.assertEqual(ready_after_claim["data"]["count"], 1)
        self.assertEqual(ready_after_claim["data"]["tasks"][0]["task_id"], "tsk_lifecycle_ready")

    def test_stdio_server_supports_tasks_reconcile_start_tool_flow(self) -> None:
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

        self._notify("notifications/initialized")

        reuse_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "tasks_reconcile_start",
                    "arguments": {
                        "lifecycle_key": "lifecycle://stdio/reuse",
                        "plan": "Resume lifecycle work",
                    },
                },
            )
        )
        self.assertEqual(reuse_payload["status"], "accepted")
        self.assertEqual(reuse_payload["data"]["task_id"], "tsk_lifecycle_ready")
        self.assertEqual(reuse_payload["data"]["state"], "in_progress")
        self.assertFalse(reuse_payload["data"]["created_task"])

        cli_start = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://stdio/create",
                "--plan",
                "Create lifecycle work",
                "--origin-audit-id",
                "aud_lifecycle",
                "--description",
                "CLI lifecycle task",
                "--priority",
                "high",
                "--effort",
                "low",
                "--risk",
                "low",
                "--task-type",
                "ops",
                "--justification-json",
                '{"summary":"Create lifecycle task","evidence_refs":["artifact://stdio/create"],"expected_impact":"Track lifecycle start"}',
                "--execution-context-json",
                json.dumps({"project_id": self.project_id, "steps": ["claim", "work"]}, sort_keys=True),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(cli_start.returncode, 0)
        cli_payload = json.loads(cli_start.stdout)
        self.assertEqual(cli_payload["status"], "accepted")
        self.assertEqual(cli_payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(cli_payload["data"]["lifecycle_key"], "lifecycle://stdio/create")
        self.assertTrue(cli_payload["data"]["created_task"])

        invalid_response = self._request(
            3,
            "tools/call",
            {
                "name": "tasks_reconcile_start",
                "arguments": {
                    "lifecycle_key": "lifecycle://stdio/cross",
                    "plan": "Reject cross-project lifecycle work",
                    "origin_audit_id": "aud_lifecycle",
                    "description": "Should fail",
                    "priority": "high",
                    "effort": "low",
                    "risk": "low",
                    "task_type": "ops",
                    "justification": {
                        "summary": "Reject bad context",
                        "evidence_refs": ["artifact://stdio/cross"],
                        "expected_impact": "Prevent cross-project mutation",
                    },
                    "execution_context": {"source_project_id": "prj_other"},
                },
            },
        )
        self.assertIn("result", invalid_response)
        self.assertTrue(invalid_response["result"]["isError"])
        invalid_payload = json.loads(invalid_response["result"]["content"][0]["text"])
        self.assertEqual(invalid_payload["status"], "error")
        self.assertEqual(invalid_payload["error"]["code"], "INVALID_TASK_STATE")
        self.assertIn("must stay within the adopted project", invalid_payload["error"]["message"])

    def test_stdio_server_composes_public_audit_publish_before_lifecycle_create(self) -> None:
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
        self._notify("notifications/initialized")

        create_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "audit_create_brief",
                    "arguments": {
                        "title": "Composed stdio audit",
                        "content": "Created before lifecycle start",
                        "as_of": "2026-06-19T18:00:00Z",
                    },
                },
            )
        )
        publish_payload = self._tool_payload(
            self._request(
                3,
                "tools/call",
                {
                    "name": "audit_publish",
                    "arguments": {"audit_id": create_payload["data"]["audit_id"]},
                },
            )
        )
        start_payload = self._tool_payload(
            self._request(
                4,
                "tools/call",
                {
                    "name": "tasks_reconcile_start",
                    "arguments": {
                        "lifecycle_key": "lifecycle://stdio/public-compose",
                        "plan": "Compose public audit lifecycle start",
                        "origin_audit_id": publish_payload["data"]["audit_id"],
                        "description": "MCP lifecycle task from public audit",
                        "priority": "high",
                        "effort": "medium",
                        "risk": "low",
                        "task_type": "ops",
                        "justification": {
                            "summary": "Create lifecycle task",
                            "evidence_refs": [publish_payload["data"]["audit_id"]],
                            "expected_impact": "Track public lifecycle start",
                        },
                        "execution_context": {"project_id": self.project_id, "steps": ["audit_publish", "claim", "start"]},
                    },
                },
            )
        )

        self.assertEqual(start_payload["status"], "accepted")
        self.assertTrue(start_payload["data"]["created_task"])
        self.assertEqual(start_payload["data"]["origin_audit_id"], publish_payload["data"]["audit_id"])

    def test_stdio_server_rejects_draft_origin_audit_for_lifecycle_create(self) -> None:
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
        self._notify("notifications/initialized")

        create_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "audit_create_brief",
                    "arguments": {
                        "title": "Draft stdio audit",
                        "content": "Still draft",
                        "as_of": "2026-06-19T18:00:00Z",
                    },
                },
            )
        )
        response = self._request(
            3,
            "tools/call",
            {
                "name": "tasks_reconcile_start",
                "arguments": {
                    "lifecycle_key": "lifecycle://stdio/draft-origin",
                    "plan": "Reject draft audit origin",
                    "origin_audit_id": create_payload["data"]["audit_id"],
                    "description": "Should fail",
                    "priority": "high",
                    "effort": "low",
                    "risk": "low",
                    "task_type": "ops",
                    "justification": {
                        "summary": "Reject draft audit origin",
                        "evidence_refs": [create_payload["data"]["audit_id"]],
                        "expected_impact": "Prevent draft audit lifecycle create",
                    },
                    "execution_context": {"project_id": self.project_id},
                },
            },
        )

        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_TASK_STATE")
        self.assertIn("published origin audit", payload["error"]["message"])

    def test_stdio_server_reports_claim_conflict_for_lifecycle_task_owned_by_another_session(self) -> None:
        self._seed_active_claim_for_task(
            task_id="tsk_lifecycle_ready",
            session_id="sess-other-owner",
            plan="Other session is already working",
        )

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
        self._notify("notifications/initialized")

        response = self._request(
            2,
            "tools/call",
            {
                "name": "tasks_reconcile_start",
                "arguments": {
                    "lifecycle_key": "lifecycle://stdio/reuse",
                    "plan": "Attempt conflicting lifecycle start",
                },
            },
        )

        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "CLAIM_CONFLICT")
        self.assertIn("owned by another session", payload["error"]["message"])

    def test_stdio_server_supports_public_audit_tool_flow(self) -> None:
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
        self._notify("notifications/initialized")

        create_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "audit_create_brief",
                    "arguments": {
                        "title": "Stdio brief audit",
                        "content": "Stdio audit body",
                        "as_of": "2026-06-19T18:00:00Z",
                    },
                },
            )
        )
        self.assertEqual(create_payload["status"], "accepted")
        self.assertEqual(create_payload["data"]["state"], "draft")

        publish_payload = self._tool_payload(
            self._request(
                3,
                "tools/call",
                {
                    "name": "audit_publish",
                    "arguments": {"audit_id": create_payload["data"]["audit_id"]},
                },
            )
        )
        self.assertEqual(publish_payload["status"], "accepted")
        self.assertEqual(publish_payload["data"]["state"], "published")

        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        self.assertEqual(store.get_audit(create_payload["data"]["audit_id"])["state"], "published")

    def test_stdio_server_supports_tasks_reconcile_finish_tool_flow(self) -> None:
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
        self._notify("notifications/initialized")

        start_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "tasks_reconcile_start",
                    "arguments": {
                        "lifecycle_key": "lifecycle://stdio/reuse",
                        "plan": "Resume lifecycle work",
                    },
                },
            )
        )
        self.assertEqual(start_payload["data"]["state"], "in_progress")

        finish_payload = self._tool_payload(
            self._request(
                3,
                "tools/call",
                {
                    "name": "tasks_reconcile_finish",
                    "arguments": {
                        "lifecycle_key": "lifecycle://stdio/reuse",
                        "outcome": "blocked",
                        "as_of": "2026-06-19T18:04:00Z",
                        "blocked_reason": "Waiting on dependency",
                        "blocked_evidence": "artifact://stdio/finish",
                        "blocked_next_step": "Retry after dependency is resolved",
                    },
                },
            )
        )
        self.assertEqual(finish_payload["status"], "accepted")
        self.assertEqual(finish_payload["data"]["state"], "blocked")

        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        self.assertEqual(store.get_task("tsk_lifecycle_ready")["blocked_reason"], "Waiting on dependency")
        self.assertIsNone(store.get_cached_claim("tsk_lifecycle_ready"))

    def test_stdio_server_supports_milestone_publish_composed_flow(self) -> None:
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
        self._notify("notifications/initialized")
        payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "milestone_publish",
                    "arguments": {
                        "title": "Milestone batch audit",
                        "content": "Published in one MCP call",
                        "as_of": "2026-06-21T18:00:00Z",
                        "lifecycle": {
                            "lifecycle_key": "lifecycle://stdio/milestone-batch",
                            "plan": "Close milestone work in one call",
                            "description": "Lifecycle task from milestone_publish",
                            "priority": "high",
                            "effort": "medium",
                            "risk": "low",
                            "task_type": "ops",
                            "justification": {
                                "summary": "Batch milestone close",
                                "evidence_refs": ["milestone_publish"],
                                "expected_impact": "Reduce MCP calls for milestones",
                            },
                            "execution_context": {"project_id": self.project_id},
                            "outcome": "done",
                            "done_result": "Milestone published and lifecycle closed",
                            "done_artifacts": "runtime/node/current.py",
                            "done_references": "lifecycle://stdio/milestone-batch",
                            "done_expected_impact": "One-call milestone publication",
                        },
                    },
                },
            )
        )
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["data"]["audit_state"], "published")
        self.assertEqual(payload["data"]["lifecycle"]["state"], "done")
        self.assertEqual(payload["data"]["lifecycle"]["lifecycle_key"], "lifecycle://stdio/milestone-batch")

    def test_stdio_server_supports_project_page_get_and_upsert(self) -> None:
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
        self._notify("notifications/initialized")
        store = NodeStore.from_file(self.node_home / "node.sqlite3")
        self.addCleanup(store.close)
        store.upsert_project_page(
            page_id="pg_purpose",
            project_id=self.project_id,
            page_type="purpose",
            title="Purpose",
            content="Initial purpose",
            updated_at="2026-06-21T12:00:00Z",
        )
        store.db.commit()

        get_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {"name": "project_page_get", "arguments": {"page_type": "purpose"}},
            )
        )
        self.assertEqual(get_payload["status"], "ok")
        self.assertEqual(get_payload["data"]["content"], "Initial purpose")

        upsert_payload = self._tool_payload(
            self._request(
                3,
                "tools/call",
                {
                    "name": "project_page_upsert",
                    "arguments": {
                        "page_type": "purpose",
                        "title": "Purpose",
                        "content": "Updated purpose via MCP",
                    },
                },
            )
        )
        self.assertEqual(upsert_payload["status"], "accepted")
        self.assertEqual(upsert_payload["data"]["content"], "Updated purpose via MCP")

    def test_stdio_server_rejects_finish_without_explicit_metadata(self) -> None:
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
        self._notify("notifications/initialized")

        start_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "tasks_reconcile_start",
                    "arguments": {
                        "lifecycle_key": "lifecycle://stdio/reuse",
                        "plan": "Resume lifecycle work",
                    },
                },
            )
        )
        self.assertEqual(start_payload["data"]["state"], "in_progress")

        response = self._request(
            3,
            "tools/call",
            {
                "name": "tasks_reconcile_finish",
                "arguments": {
                    "lifecycle_key": "lifecycle://stdio/reuse",
                    "outcome": "done",
                    "as_of": "2026-06-19T18:04:00Z",
                    "done_result": "Completed the lifecycle work",
                    "done_artifacts": "artifact://stdio/finish-missing",
                },
            },
        )

        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "INVALID_ARGUMENTS")
        self.assertIn("explicit finish metadata", payload["error"]["message"])

    def test_stdio_server_upgrades_stale_owner_local_schema_before_lifecycle_reconcile_start(self) -> None:
        downgrade_owner_local_tasks_schema(self.node_home / "node.sqlite3")
        user_version, columns = read_owner_local_schema_state(self.node_home / "node.sqlite3")
        self.assertEqual(user_version, 0)
        self.assertNotIn("lifecycle_key", columns)

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
        self._notify("notifications/initialized")

        start_payload = self._tool_payload(
            self._request(
                2,
                "tools/call",
                {
                    "name": "tasks_reconcile_start",
                    "arguments": {
                        "lifecycle_key": "lifecycle://stdio/stale-upgrade",
                        "plan": "Create lifecycle work on stale schema",
                        "origin_audit_id": "aud_lifecycle",
                        "description": "Stale schema lifecycle task",
                        "priority": "high",
                        "effort": "low",
                        "risk": "low",
                        "task_type": "ops",
                        "justification": {
                            "summary": "Upgrade stale owner-local schema through stdio",
                            "evidence_refs": ["artifact://stdio/stale-upgrade"],
                            "expected_impact": "Allow lifecycle reconcile start without manual SQL",
                        },
                        "execution_context": {"project_id": self.project_id, "steps": ["upgrade", "claim"]},
                    },
                },
            )
        )

        self.assertEqual(start_payload["status"], "accepted")
        self.assertEqual(start_payload["data"]["state"], "in_progress")
        self.assertTrue(start_payload["data"]["created_task"])
        user_version, columns = read_owner_local_schema_state(self.node_home / "node.sqlite3")
        self.assertEqual(user_version, 2)
        self.assertIn("lifecycle_key", columns)

    def test_stdio_server_current_get_reports_schema_compatibility_error_for_unsupported_owner_local_drift(self) -> None:
        write_incompatible_owner_local_schema(self.node_home / "node.sqlite3", user_version=99, include_project_id=True)

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
        self._notify("notifications/initialized")

        response = self._request(
            2,
            "tools/call",
            {
                "name": "current_get",
                "arguments": {"as_of": "2026-06-19T13:45:00Z", "ready_limit": 1},
            },
        )

        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "LOCAL_SCHEMA_COMPATIBILITY_ERROR")

    def test_stdio_server_current_get_reports_schema_compatibility_error_for_unsafe_owner_local_drift(self) -> None:
        write_incompatible_owner_local_schema(self.node_home / "node.sqlite3", user_version=0, include_project_id=False)

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
        self._notify("notifications/initialized")

        response = self._request(
            2,
            "tools/call",
            {
                "name": "current_get",
                "arguments": {"as_of": "2026-06-19T13:45:00Z", "ready_limit": 1},
            },
        )

        self.assertIn("result", response)
        self.assertTrue(response["result"]["isError"])
        payload = json.loads(response["result"]["content"][0]["text"])
        self.assertEqual(payload["status"], "error")
        self.assertEqual(payload["error"]["code"], "LOCAL_SCHEMA_COMPATIBILITY_ERROR")

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

    def test_installed_command_root_help_lists_tasks_claim(self) -> None:
        result = subprocess.run(
            [str(self.command_path), "--help"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("tasks", result.stdout)
        self.assertIn("Read task queues, execution claims, and lifecycle", result.stdout)
        self.assertIn("wrappers", result.stdout)
        tasks_help = subprocess.run(
            [str(self.command_path), "tasks", "--help"],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(tasks_help.returncode, 0)
        self.assertIn("claim", tasks_help.stdout)
        self.assertIn("start", tasks_help.stdout)
        self.assertIn("finish", tasks_help.stdout)
        self.assertIn("Reconcile owner-local same-project lifecycle work", tasks_help.stdout)
        self.assertIn("Close owner-local adopted lifecycle work", tasks_help.stdout)

    def test_installed_command_supports_tasks_claim_flow(self) -> None:
        result = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "claim",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--task-id",
                "tsk_ready",
                "--plan",
                "Implement the ready task",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "claimed")
        self.assertEqual(payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(payload["data"]["task_id"], "tsk_ready")
        self.assertEqual(payload["data"]["state"], "claimed")
        self.assertEqual(payload["data"]["plan"], "Implement the ready task")

    def test_installed_command_supports_tasks_finish_flow(self) -> None:
        start_result = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "start",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://stdio/reuse",
                "--plan",
                "Resume lifecycle work",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(start_result.returncode, 0)

        finish_result = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "finish",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--lifecycle-key",
                "lifecycle://stdio/reuse",
                "--outcome",
                "done",
                "--done-result",
                "Lifecycle task completed",
                "--done-artifacts",
                "artifact://stdio/finish-done",
                "--done-references",
                "ref://stdio/finish-done",
                "--done-expected-impact",
                "Close the lifecycle task",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(finish_result.returncode, 0)
        payload = json.loads(finish_result.stdout)
        self.assertEqual(payload["status"], "accepted")
        self.assertEqual(payload["data"]["state"], "done")

    def test_installed_command_supports_tasks_ready_flow(self) -> None:
        result = subprocess.run(
            [
                str(self.command_path),
                "tasks",
                "ready",
                "--repo-root",
                str(self.repo_root),
                "--node-home",
                str(self.node_home),
                "--as-of",
                "2026-06-19T13:45:00Z",
                "--limit",
                "1",
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["data"]["adopted_project"]["project_id"], self.project_id)
        self.assertEqual(payload["data"]["index_name"], "ready")
        self.assertEqual(payload["data"]["as_of"], "2026-06-19T13:45:00Z")
        self.assertEqual(payload["data"]["count"], 1)
        self.assertEqual(payload["data"]["limit"], 1)
        self.assertEqual(len(payload["data"]["tasks"]), 1)

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
