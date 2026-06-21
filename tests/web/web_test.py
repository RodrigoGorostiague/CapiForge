import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

try:
    from fastapi.testclient import TestClient

    from runtime.node.bootstrap import NodeBootstrap
    from runtime.node.store import NodeStore
    from runtime.web.app import create_app
    from runtime.web.cli import DEFAULT_HOST, DEFAULT_PORT, DEFAULT_REFRESH_SECONDS, build_parser, main as web_main
    from runtime.web.context import WebContext
    from runtime.web.markdown import render_markdown
except ModuleNotFoundError:
    TestClient = None
    create_app = None
    web_main = None
    render_markdown = None

_WEB_DEPS_INSTALLED = TestClient is not None


@unittest.skipIf(TestClient is None, "Web dependencies are not installed")
class WebCLITest(unittest.TestCase):
    def test_build_parser_defaults(self) -> None:
        args = build_parser().parse_args([])
        self.assertEqual(args.host, DEFAULT_HOST)
        self.assertEqual(args.port, DEFAULT_PORT)
        self.assertEqual(args.refresh, DEFAULT_REFRESH_SECONDS)
        self.assertFalse(args.no_open)
        self.assertFalse(args.no_realtime)

    def test_main_reports_missing_dependencies(self) -> None:
        stderr = StringIO()
        with patch("runtime.web.cli.sys.stderr", stderr):
            with patch.dict("sys.modules", {"uvicorn": None}):
                exit_code = web_main(["--no-open"], prog="capiforge web")
        self.assertEqual(exit_code, 1)
        self.assertIn("uv sync --extra web", stderr.getvalue())
        self.assertIn("capinstall update", stderr.getvalue())


@unittest.skipIf(TestClient is None, "Web dependencies are not installed")
class WebAppTest(unittest.TestCase):
    def _adopted_client(self) -> tuple[TestClient, Path]:
        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: Path(tempdir).exists() and __import__("shutil").rmtree(tempdir, ignore_errors=True))
        repo_root = Path(tempdir) / "repo"
        repo_root.mkdir(parents=True)
        bootstrap = NodeBootstrap(repo_root=repo_root)
        bootstrap.open_or_init()
        adopted = bootstrap.adopt_repo()
        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        store.create_audit("aud_web", adopted.adopted_project["project_id"], "published", "Web Audit", "## Scope\n\nHello **world**.")
        store.create_task(
            "tsk_web",
            adopted.adopted_project["project_id"],
            "aud_web",
            "ready",
            "high",
            "medium",
            "low",
            "feature",
            "Ship the web UI",
        )
        store.db.commit()
        ctx = WebContext(
            repo_root=repo_root,
            node_home=None,
            as_of="2026-06-20T12:00:00Z",
            refresh_seconds=0,
            realtime_enabled=True,
        )
        client = TestClient(create_app(ctx))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client, repo_root

    def _adopted_client_with_ctx(self, **overrides) -> tuple[TestClient, Path]:
        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: Path(tempdir).exists() and __import__("shutil").rmtree(tempdir, ignore_errors=True))
        repo_root = Path(tempdir) / "repo"
        repo_root.mkdir(parents=True)
        bootstrap = NodeBootstrap(repo_root=repo_root)
        bootstrap.open_or_init()
        adopted = bootstrap.adopt_repo()
        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        store.create_audit("aud_web", adopted.adopted_project["project_id"], "published", "Web Audit", "## Scope\n\nHello **world**.")
        store.create_task(
            "tsk_web",
            adopted.adopted_project["project_id"],
            "aud_web",
            "ready",
            "high",
            "medium",
            "low",
            "feature",
            "Ship the web UI",
        )
        store.db.commit()
        defaults = {
            "repo_root": repo_root,
            "node_home": None,
            "as_of": "2026-06-20T12:00:00Z",
            "refresh_seconds": 0,
            "realtime_enabled": True,
        }
        defaults.update(overrides)
        ctx = WebContext(**defaults)
        client = TestClient(create_app(ctx))
        client.__enter__()
        self.addCleanup(client.__exit__, None, None, None)
        return client, repo_root

    def test_home_page_renders(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("CapiForge", response.text)
        self.assertIn('class="sidebar-brand-version">v0.4.0</span>', response.text)
        self.assertIn("Ship the web UI", response.text)
        self.assertIn("home-dashboard", response.text)
        self.assertIn("Estado del proyecto", response.text)
        self.assertIn("home-queue-chip", response.text)
        self.assertIn("Primeros pasos", response.text)
        self.assertIn("index_local_docs.py", response.text)

    def test_tasks_page_renders(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ship the web UI", response.text)
        self.assertIn("Reclamar", response.text)
        self.assertIn("Nueva tarea", response.text)
        self.assertIn('id="tasks-panel"', response.text)
        self.assertIn("hx-get=", response.text)

    def test_task_create_from_web(self) -> None:
        client, repo_root = self._adopted_client()
        list_response = client.get("/tasks")
        project_id = list_response.text.split('name="project_id" value="')[1].split('"')[0]
        response = client.post(
            "/api/tasks/create",
            data={
                "project_id": project_id,
                "workspace_id": "",
                "filter": "all",
                "description": "Task created from web UI",
                "priority": "high",
                "task_type": "doc",
                "initial_state": "ready",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Task created from web UI", response.text)
        self.assertIn('id="tasks-panel"', response.text)
        bootstrap = NodeBootstrap(repo_root=repo_root)
        adopted = bootstrap.adopt_repo()
        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        matches = [
            row
            for row in store.db.execute(
                "SELECT task_id, description, priority, type, state FROM tasks WHERE description = ?",
                ("Task created from web UI",),
            ).fetchall()
        ]
        self.assertEqual(len(matches), 1)
        task_id, description, priority, task_type, state = matches[0]
        self.assertEqual(description, "Task created from web UI")
        self.assertEqual(priority, "high")
        self.assertEqual(task_type, "doc")
        self.assertEqual(state, "ready")
        self.assertTrue(task_id.startswith("tsk_web_"))

    def test_task_create_requires_description(self) -> None:
        client, _repo = self._adopted_client()
        list_response = client.get("/tasks")
        project_id = list_response.text.split('name="project_id" value="')[1].split('"')[0]
        response = client.post(
            "/api/tasks/create",
            data={
                "project_id": project_id,
                "workspace_id": "",
                "filter": "all",
                "description": "   ",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("Error:", response.text)

    def test_home_sidebar_links_to_root(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('href="/?workspace_id=', response.text)
        self.assertNotIn('href="/home?', response.text)

    def test_tasks_panel_partial(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/api/partials/tasks-panel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Ship the web UI", response.text)
        self.assertIn("filter-pill", response.text)

    def test_tasks_pagination_and_badges(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertIn("pill-tone--", response.text)

    def test_sync_indicator_in_sidebar_brand(self) -> None:
        client, _repo = self._adopted_client()
        for path in ("/", "/tasks", "/docs"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("app-sync-status", response.text)
            self.assertIn("sync-dot", response.text)
            self.assertNotIn("sync-status--header", response.text)
            self.assertNotIn("sidebar-footer", response.text)

    def test_brand_logo_and_splash(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("app-splash-loader", response.text)
        self.assertIn("sidebar-brand-icon", response.text)
        self.assertIn("/brand/capiforge_logo_original_transparente.png", response.text)
        logo = client.get("/brand/capiforge_logo_original_transparente.png")
        self.assertEqual(logo.status_code, 200)
        self.assertIn("image/png", logo.headers.get("content-type", ""))

    def test_tasks_panel_partial_preserves_filter(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/api/partials/tasks-panel?filter=active")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Activas", response.text)
        self.assertIn("filter=active", response.text)

    def test_tasks_panel_has_sortable_headers(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/api/partials/tasks-panel?sort=priority&sort_dir=desc")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sort-header", response.text)
        self.assertIn("sort=priority", response.text)
        self.assertIn("↓", response.text)

    def test_task_update_field_htmx(self) -> None:
        client, _repo = self._adopted_client()
        list_response = client.get("/tasks")
        project_id = list_response.text.split('name="project_id" value="')[1].split('"')[0]
        response = client.post(
            "/api/tasks/update-field",
            data={
                "task_id": "tsk_web",
                "project_id": project_id,
                "workspace_id": "",
                "filter": "all",
                "field": "priority",
                "value": "critical",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("pill-picker", response.text)
        self.assertIn("critical", response.text)

    def test_tasks_panel_has_editable_pills(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/api/partials/tasks-panel")
        self.assertEqual(response.status_code, 200)
        self.assertIn("pill-picker", response.text)

    def test_task_description_links_to_detail(self) -> None:
        client, _repo = self._adopted_client()
        list_response = client.get("/tasks")
        project_id = list_response.text.split('name="project_id" value="')[1].split('"')[0]
        response = client.get(
            f"/api/partials/tasks-panel?project_id={project_id}&filter=all&task_id=tsk_web"
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("task-row-link", response.text)
        self.assertIn("task_id=tsk_web", response.text)
        self.assertIn('id="task-detail"', response.text)
        self.assertIn("detail-dl", response.text)
        self.assertIn("Atributos", response.text)
        self.assertIn("Identificador", response.text)
        self.assertIn("is-selected", response.text)

    def test_add_project_form_partial(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/")
        workspace_id = response.text.split("add-project-form?workspace_id=")[1].split('"')[0]
        form = client.get(f"/api/partials/add-project-form?workspace_id={workspace_id}")
        self.assertEqual(form.status_code, 200)
        self.assertIn("folder_path", form.text)
        self.assertIn("Elegir carpeta", form.text)

    def test_pick_folder_endpoint_without_display(self) -> None:
        client, _repo = self._adopted_client()
        with patch.dict("os.environ", {}, clear=True):
            response = client.get("/api/projects/pick-folder")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["ok"])

    def test_adopt_folder_project(self) -> None:
        client, hub_repo = self._adopted_client()
        new_folder = hub_repo.parent / "other-web-project"
        new_folder.mkdir(exist_ok=True)
        home = client.get("/")
        workspace_id = home.text.split("add-project-form?workspace_id=")[1].split('"')[0]
        response = client.post(
            "/api/projects/adopt-folder",
            data={"workspace_id": workspace_id, "folder_path": str(new_folder)},
            follow_redirects=False,
        )
        self.assertIn(response.status_code, {200, 303})
        self.assertTrue((hub_repo / ".capiforge" / "web" / "project-repos.json").exists())
        self.assertTrue((new_folder / ".capiforge" / "node" / "bootstrap.json").exists())

        client, _repo = self._adopted_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sidebar-node", response.text)
        self.assertIn("expanded_ws=", response.text)
        self.assertIn("sidebar-chevron", response.text)

    def test_project_switcher_preserves_route(self) -> None:
        client, hub_repo = self._adopted_client()
        home = client.get("/")
        workspace_id = home.text.split("add-project-form?workspace_id=")[1].split('"')[0]
        hub_project_id = home.text.split('name="project_id" value="')[1].split('"')[0] if 'name="project_id" value="' in home.text else home.text.split("project_id=")[1].split("&")[0]

        new_folder = hub_repo.parent / "switch-target"
        new_folder.mkdir(exist_ok=True)
        adopt = client.post(
            "/api/projects/adopt-folder",
            data={"workspace_id": workspace_id, "folder_path": str(new_folder)},
            follow_redirects=False,
        )
        self.assertIn(adopt.status_code, {200, 303})

        tasks = client.get("/tasks")
        self.assertIn("project-switcher-select", tasks.text)
        self.assertIn("switch-target", tasks.text)
        self.assertIn("/tasks?project_id=", tasks.text)

        docs = client.get(f"/docs?project_id={hub_project_id}&workspace_id={workspace_id}")
        self.assertEqual(docs.status_code, 200)
        self.assertIn("project-switcher-select", docs.text)

    def test_active_project_repo_in_subtitle(self) -> None:
        client, repo_root = self._adopted_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(str(repo_root.resolve()), response.text)

    def test_task_action_htmx_returns_toast_and_panel(self) -> None:
        client, _repo = self._adopted_client()
        list_response = client.get("/tasks")
        project_id = list_response.text.split('name="project_id" value="')[1].split('"')[0]
        response = client.post(
            "/api/tasks/claim",
            data={
                "task_id": "tsk_web",
                "project_id": project_id,
                "workspace_id": "",
                "filter": "all",
            },
            headers={"HX-Request": "true"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("notice-banner", response.text)
        self.assertIn('id="tasks-panel"', response.text)
        self.assertIn("hx-swap-oob", response.text)

    def test_docs_page_renders_markdown(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/docs?audit_id=aud_web")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Web Audit", response.text)
        self.assertIn("<strong>world</strong>", response.text)

    def test_docs_page_rewrites_relative_markdown_links(self) -> None:
        client, repo_root = self._adopted_client()
        parent = repo_root / "docs" / "audits" / "audit-v04-expanded-hub.md"
        parent.parent.mkdir(parents=True, exist_ok=True)
        parent.write_text("# Parent\n\nExpanded hub.", encoding="utf-8")
        bootstrap = NodeBootstrap(repo_root=repo_root)
        adopted = bootstrap.adopt_repo()
        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        store.create_audit(
            "aud_child",
            adopted.adopted_project["project_id"],
            "published",
            "Child audit",
            "**Parent:** [audit-v04-expanded-hub.md](audit-v04-expanded-hub.md)",
        )
        store.db.commit()
        list_response = client.get("/docs")
        project_id = list_response.text.split("project_id=")[1].split("&")[0]
        workspace_id = list_response.text.split("workspace_id=")[1].split('"')[0]
        response = client.get(f"/docs?project_id={project_id}&workspace_id={workspace_id}&audit_id=aud_child")
        self.assertEqual(response.status_code, 200)
        self.assertIn("doc_path=docs%2Faudits%2Faudit-v04-expanded-hub.md", response.text)
        follow = client.get(
            f"/docs?project_id={project_id}&workspace_id={workspace_id}&doc_path=docs/audits/audit-v04-expanded-hub.md"
        )
        self.assertEqual(follow.status_code, 200)
        self.assertIn("Expanded hub", follow.text)

    def test_local_document_viewer_renders_repo_file(self) -> None:
        client, repo_root = self._adopted_client()
        doc_path = repo_root / "docs" / "sample.md"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text("# Sample\n\nLocal **doc**.", encoding="utf-8")
        bootstrap = NodeBootstrap(repo_root=repo_root)
        adopted = bootstrap.adopt_repo()
        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        store.add_local_document("doc_sample", adopted.adopted_project["project_id"], "docs/sample.md")
        store.db.commit()
        list_response = client.get("/docs")
        project_id = list_response.text.split("project_id=")[1].split("&")[0]
        response = client.get(f"/docs?project_id={project_id}&document_id=doc_sample")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Local <strong>doc</strong>", response.text)
        self.assertIn("docs/sample.md", response.text)

    def test_realtime_assets_on_pages(self) -> None:
        client, _repo = self._adopted_client()
        for path in ("/", "/tasks", "/docs"):
            response = client.get(path)
            self.assertEqual(response.status_code, 200)
            self.assertIn("realtime-config", response.text)
            self.assertIn("/static/realtime.js", response.text)

    def test_no_realtime_disables_sse_assets(self) -> None:
        client, _repo = self._adopted_client_with_ctx(realtime_enabled=False)
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("realtime-config", response.text)
        self.assertNotIn("/static/realtime.js", response.text)
        stream = client.get("/api/events/stream")
        self.assertEqual(stream.status_code, 404)

    def test_sse_stream_available_when_realtime_enabled(self) -> None:
        client, _repo = self._adopted_client()
        self.assertIsNotNone(client.app.state.event_bus)

    def test_refresh_fallback_triggers_remain_when_enabled(self) -> None:
        client, _repo = self._adopted_client_with_ctx(refresh_seconds=15)
        home = client.get("/")
        self.assertIn("every 15s", home.text)
        tasks = client.get("/tasks")
        self.assertIn("every 15s", tasks.text)

    def test_sync_status_partial_updates_coord_meta(self) -> None:
        client, _repo = self._adopted_client()
        list_response = client.get("/tasks")
        project_id = list_response.text.split('name="project_id" value="')[1].split('"')[0]
        response = client.get(f"/api/partials/sync-status?project_id={project_id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("sync-coord-meta", response.text)
        self.assertIn("data-coord-label", response.text)
        self.assertIn("Coordinador:", response.text)

    def test_freshness_indicator_starts_connecting_with_realtime(self) -> None:
        client, _repo = self._adopted_client()
        response = client.get("/tasks")
        self.assertIn("sync-dot--connecting", response.text)
        self.assertIn("Conectando", response.text)
        self.assertIn("data-coord-label", response.text)

    def test_uninitialized_repo_shows_notice(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "empty"
            repo_root.mkdir()
            ctx = WebContext(repo_root=repo_root, node_home=None, as_of=None, refresh_seconds=0, realtime_enabled=False)
            client = TestClient(create_app(ctx))
            client.__enter__()
            self.addCleanup(client.__exit__, None, None, None)
            response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("bootstrap", response.text.lower())


@unittest.skipIf(not _WEB_DEPS_INSTALLED, "Web dependencies are not installed")
class WebMarkdownTest(unittest.TestCase):
    def test_render_markdown_disables_raw_html(self) -> None:
        html = render_markdown("**bold**")
        self.assertIn("<strong>bold</strong>", html)
