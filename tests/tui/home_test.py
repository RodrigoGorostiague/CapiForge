import tempfile
import unittest
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError
from runtime.tui.data import AuditPreview, HomeSnapshot, ProjectSnapshot, ReadyTaskPreview, WorkspaceSnapshot, load_home_snapshot
from runtime.tui.splash import build_splash_content
from runtime.tui.view import (
    build_home_rows,
    build_home_sections,
    build_home_view_model,
    load_home_view_model,
    resolve_browser_selection,
)

try:
    from textual.css.query import NoMatches
    from textual.widgets import DataTable, Static

    from runtime.tui.app import STARTUP_SNAPSHOT_DELAY_SECONDS, HomeApp, StartupSplash, main as tui_main
    from runtime.tui.widgets import AuditTaskRow, DocRow, FilterPill, NavRow
    from textual.containers import Vertical
except ModuleNotFoundError:
    HomeApp = None
    DataTable = None
    NoMatches = None
    STARTUP_SNAPSHOT_DELAY_SECONDS = None
    Static = None
    StartupSplash = None
    tui_main = None

@unittest.skipIf(HomeApp is None, "Textual is not installed")
class TUIEntrypointTest(unittest.TestCase):
    def test_main_builds_app_from_cli_args(self) -> None:
        app_instance = unittest.mock.Mock()

        with (
            patch("runtime.tui.shell.sys.stdin.isatty", return_value=True),
            patch("runtime.tui.shell.sys.stdout.isatty", return_value=True),
            patch("runtime.tui.shell.ShellApp", return_value=app_instance) as home_app,
        ):
            exit_code = tui_main(
                ["--repo-root", "/tmp/repo", "--node-home", "/tmp/node", "--as-of", "2026-06-19T18:00:00Z"]
            )

        self.assertEqual(exit_code, 0)
        home_app.assert_called_once_with(
            repo_root="/tmp/repo",
            node_home="/tmp/node",
            as_of="2026-06-19T18:00:00Z",
            theme=None,
            auto_refresh_seconds=None,
        )
        app_instance.run.assert_called_once_with()

    def test_main_reports_non_tty_contract(self) -> None:
        stderr = StringIO()

        with (
            patch("runtime.tui.shell.sys.stdin.isatty", return_value=False),
            patch("runtime.tui.shell.sys.stdout.isatty", return_value=False),
            patch("runtime.tui.shell.sys.stderr", stderr),
            patch("runtime.tui.shell.ShellApp") as home_app,
        ):
            exit_code = tui_main([])

        self.assertEqual(exit_code, 1)
        self.assertIn("The TUI requires an interactive terminal.", stderr.getvalue())
        home_app.assert_not_called()


class HomeSnapshotTest(unittest.TestCase):
    def test_snapshot_degrades_gracefully_before_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot = load_home_snapshot(repo_root=tempdir, as_of="2026-06-19T18:00:00Z")

        self.assertEqual(snapshot.bootstrap_state, "uninitialized")
        self.assertFalse(snapshot.queue_counts)
        self.assertIn("No local bootstrap yet.", snapshot.notices[0])

    def test_snapshot_reads_adopted_project_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            self.assertEqual(adopted_state.state, "initialized")
            adopted_state = bootstrap.adopt_repo()

            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_audit("aud_1", adopted_state.adopted_project["project_id"], "published", "Audit", "body")
            store.create_task("tsk_ready", adopted_state.adopted_project["project_id"], "aud_1", "ready", "high", "low", "low", "fix", "Tune the home screen spacing")
            store.create_task(
                "tsk_blocked",
                adopted_state.adopted_project["project_id"],
                "aud_1",
                "blocked",
                "medium",
                "low",
                "low",
                "fix",
                "Blocked task",
                blocked_reason="waiting",
                blocked_evidence="artifact://1",
                blocked_next_step="unblock",
            )
            store.db.commit()

            snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        self.assertEqual(snapshot.bootstrap_state, "adopted")
        self.assertEqual(snapshot.project_name, "repo")
        self.assertEqual(snapshot.workspace_name, repo_root.parent.name)
        self.assertEqual(snapshot.queue_counts["ready"], 1)
        self.assertEqual(snapshot.queue_counts["blocked"], 1)
        self.assertEqual(snapshot.ready_tasks[0].description, "Tune the home screen spacing")
        self.assertEqual(snapshot.ready_tasks[0].state, "ready")
        self.assertEqual(snapshot.ready_tasks[0].task_type, "fix")
        self.assertEqual(len(snapshot.workspaces), 1)
        self.assertEqual(snapshot.workspaces[0].name, repo_root.parent.name)
        self.assertEqual(snapshot.workspaces[0].projects[0].name, "repo")
        self.assertIn("Local-only visibility", snapshot.sync_summary)

    def test_snapshot_enumerates_visible_workspaces_and_projects(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()

            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_workspace("ws_extra", "workspace://extra", "Extra workspace")
            store.upsert_project("prj_extra", "ws_extra", adopted_state.local_node_id, "project://extra", "Extra project")
            store.create_audit("aud_extra", "prj_extra", "published", "Audit", "body")
            store.create_task("tsk_extra", "prj_extra", "aud_extra", "ready", "medium", "low", "low", "fix", "Extra task")
            store.db.commit()

            snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        self.assertCountEqual([workspace.name for workspace in snapshot.workspaces], ["Extra workspace", repo_root.parent.name])
        extra_workspace = next(workspace for workspace in snapshot.workspaces if workspace.name == "Extra workspace")
        self.assertEqual(extra_workspace.projects[0].name, "Extra project")
        self.assertEqual(extra_workspace.projects[0].ready_tasks[0].description, "Extra task")

    def test_snapshot_excludes_inaccessible_projects_from_workspace_browser_data(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()

            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_workspace("ws_hidden", "workspace://hidden", "Hidden workspace")
            store.upsert_project("prj_hidden", "ws_hidden", "remote-node", "project://hidden", "Hidden project")
            store.db.commit()

            snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        hidden_workspace = next(workspace for workspace in snapshot.workspaces if workspace.workspace_id == "ws_hidden")
        self.assertEqual(hidden_workspace.projects, ())
        self.assertNotIn("Hidden project", [project.name for workspace in snapshot.workspaces for project in workspace.projects])

    def test_snapshot_keeps_local_browser_data_without_adopted_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            initialized_state = bootstrap.open_or_init()

            store = NodeStore.from_file(initialized_state.node_db_path)
            self.addCleanup(store.close)
            store.create_workspace("ws_extra", "workspace://extra", "Extra workspace")
            store.upsert_project("prj_extra", "ws_extra", initialized_state.local_node_id, "project://extra", "Extra project")
            store.create_audit("aud_extra", "prj_extra", "published", "Audit", "body")
            store.create_task("tsk_extra", "prj_extra", "aud_extra", "ready", "medium", "low", "low", "fix", "Extra task")
            store.db.commit()

            snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        self.assertEqual(snapshot.bootstrap_state, "initialized")
        self.assertIsNone(snapshot.project_name)
        self.assertEqual(len(snapshot.workspaces), 1)
        self.assertEqual(snapshot.workspaces[0].name, "Extra workspace")
        self.assertEqual(snapshot.workspaces[0].projects[0].name, "Extra project")
        self.assertEqual(snapshot.workspaces[0].projects[0].ready_tasks[0].description, "Extra task")
        self.assertIn("Bootstrap is ready, but no repository is adopted yet.", snapshot.notices)

    def test_snapshot_keeps_partial_data_when_workspace_lookup_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()

            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_audit("aud_1", adopted_state.adopted_project["project_id"], "published", "Audit", "body")
            store.create_task("tsk_ready", adopted_state.adopted_project["project_id"], "aud_1", "ready", "high", "low", "low", "fix", "Ready task")
            store.db.commit()

            with patch(
                "runtime.tui.data.NodeMCPSurface.workspace_get",
                side_effect=SurfaceError("WORKSPACE_UNAVAILABLE", "workspace failed"),
            ):
                snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        self.assertEqual(snapshot.bootstrap_state, "adopted")
        self.assertIsNone(snapshot.workspace_name)
        self.assertEqual(snapshot.project_name, "repo")
        self.assertEqual(snapshot.queue_counts["ready"], 1)
        self.assertEqual(snapshot.ready_tasks[0].description, "Ready task")
        self.assertIn("Workspace details are unavailable.", snapshot.notices)
        self.assertIn("Local-only visibility", snapshot.sync_summary)

    def test_snapshot_degrades_gracefully_when_store_open_fails(self) -> None:
        from runtime.node.store import NodeStore

        real_from_file = NodeStore.from_file
        call_count = 0

        def guarded_from_file(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return real_from_file(*args, **kwargs)
            raise PermissionError("denied")

        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()

            with patch("runtime.tui.data.NodeStore.from_file", side_effect=guarded_from_file):
                snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        self.assertEqual(snapshot.bootstrap_state, "adopted")
        self.assertEqual(snapshot.project_name, adopted_state.adopted_project["project_name"])
        self.assertTrue(any("Local runtime data could not be read right now." in notice for notice in snapshot.notices))

    def test_snapshot_keeps_partial_data_when_store_read_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()

            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_audit("aud_1", adopted_state.adopted_project["project_id"], "published", "Audit", "body")
            store.create_task("tsk_ready", adopted_state.adopted_project["project_id"], "aud_1", "ready", "high", "low", "low", "fix", "Ready task")
            store.db.commit()

            with patch("runtime.tui.data.NodeStore.get_task", side_effect=OSError("corrupt")):
                snapshot = load_home_snapshot(repo_root=repo_root, as_of="2026-06-19T18:00:00Z")

        self.assertEqual(snapshot.bootstrap_state, "adopted")
        self.assertEqual(snapshot.queue_counts["ready"], 1)
        self.assertFalse(snapshot.ready_tasks)
        self.assertTrue(any("Local runtime data could not be read right now." in notice for notice in snapshot.notices))

    def test_home_rows_include_footer_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            snapshot = load_home_snapshot(repo_root=tempdir, as_of="2026-06-19T18:00:00Z")

        texts = [text for _kind, text in build_home_rows(snapshot)]
        self.assertIn("CapiForge", texts)
        self.assertIn("q Quit  ·  r Refresh", texts)

    def test_home_sections_keep_empty_states_readable(self) -> None:
        snapshot = HomeSnapshot(generated_at="2026-06-19T18:00:00Z")

        sections = {section.title: section.lines for section in build_home_sections(snapshot)}

        self.assertEqual(sections["Current context"][0], "Project · No adopted project")
        self.assertEqual(sections["Ready now"][0], "No ready tasks yet.")


class HomeViewModelTest(unittest.TestCase):
    def test_build_home_view_model_formats_updated_at(self) -> None:
        view_model = build_home_view_model(HomeSnapshot(generated_at="2026-06-19T18:00:00Z"))

        self.assertEqual(view_model.title, "CapiForge")
        self.assertEqual(view_model.updated_at, "Updated 2026-06-19T18:00:00Z")
        self.assertEqual(view_model.detail_panel.title, "No ready task selected")

    def test_build_home_view_model_uses_primary_ready_task_for_detail_panel(self) -> None:
        view_model = build_home_view_model(
            HomeSnapshot(
                generated_at="2026-06-19T18:00:00Z",
                ready_tasks=(
                    ReadyTaskPreview(
                        task_id="tsk_1",
                        description="Tune the home screen spacing",
                        state="ready",
                        priority="high",
                        effort="low",
                        risk="low",
                        task_type="fix",
                    ),
                ),
            )
        )

        self.assertEqual(view_model.detail_panel.title, "Tune the home screen spacing")
        self.assertEqual(view_model.detail_panel.metadata[0].value, "Ready")

    def test_build_home_view_model_uses_selected_ready_task_for_detail_panel(self) -> None:
        view_model = build_home_view_model(
            HomeSnapshot(
                generated_at="2026-06-19T18:00:00Z",
                workspaces=(
                    WorkspaceSnapshot(
                        workspace_id="ws_1",
                        name="Workspace 1",
                        projects=(
                            ProjectSnapshot(
                                project_id="prj_1",
                                workspace_id="ws_1",
                                name="Project 1",
                                ready_tasks=(
                                    ReadyTaskPreview(
                                        task_id="tsk_1",
                                        description="First task",
                                        state="ready",
                                        priority="high",
                                        effort="low",
                                        risk="low",
                                        task_type="fix",
                                    ),
                                    ReadyTaskPreview(
                                        task_id="tsk_2",
                                        description="Second task",
                                        state="ready",
                                        priority="medium",
                                        effort="medium",
                                        risk="low",
                                        task_type="feature",
                                    ),
                                ),
                            ),
                        ),
                    ),
                ),
            ),
            selected_workspace_id="ws_1",
            selected_project_id="prj_1",
            selected_task_id="tsk_2",
        )

        self.assertEqual(view_model.detail_panel.title, "Second task")
        self.assertEqual(view_model.detail_panel.metadata[-1].value, "tsk_2")

    def test_build_home_view_model_uses_selected_project_context(self) -> None:
        snapshot = HomeSnapshot(
            generated_at="2026-06-19T18:00:00Z",
            workspaces=(
                WorkspaceSnapshot(
                    workspace_id="ws_1",
                    name="Workspace 1",
                    projects=(
                        ProjectSnapshot(
                            project_id="prj_1",
                            workspace_id="ws_1",
                            name="Project 1",
                            queue_counts={"ready": 1},
                            ready_tasks=(
                                ReadyTaskPreview(
                                    task_id="tsk_1",
                                    description="Task 1",
                                    state="ready",
                                    priority="high",
                                    effort="low",
                                    risk="low",
                                    task_type="fix",
                                ),
                            ),
                        ),
                        ProjectSnapshot(
                            project_id="prj_2",
                            workspace_id="ws_1",
                            name="Project 2",
                            queue_counts={"ready": 0, "blocked": 2},
                        ),
                    ),
                ),
            ),
        )

        view_model = build_home_view_model(snapshot, selected_workspace_id="ws_1", selected_project_id="prj_2")
        sections = {section.title: section.lines for section in view_model.sections}

        self.assertEqual(sections["Current context"][0], "Project · Project 2")
        self.assertEqual(sections["Queue"][0], "Ready 0 · Blocked 2")
        self.assertEqual(view_model.detail_panel.title, "Project 2")

    def test_build_home_view_model_keeps_empty_workspace_context_without_global_fallback(self) -> None:
        view_model = build_home_view_model(
            HomeSnapshot(
                generated_at="2026-06-19T18:00:00Z",
                project_name="Adopted project",
                queue_counts={"ready": 3},
                ready_tasks=(
                    ReadyTaskPreview(
                        task_id="tsk_global",
                        description="Global task",
                        state="ready",
                        priority="high",
                        effort="low",
                        risk="low",
                        task_type="fix",
                    ),
                ),
                sync_summary="Local-only visibility · 1 pending routes · authority local-node",
                workspaces=(
                    WorkspaceSnapshot(workspace_id="ws_empty", name="Empty workspace"),
                ),
            ),
            selected_workspace_id="ws_empty",
        )

        sections = {section.title: section.lines for section in view_model.sections}

        self.assertEqual(sections["Current context"][0], "Project · No visible project selected")
        self.assertEqual(sections["Current context"][1], "Workspace · Empty workspace (0 projects)")
        self.assertEqual(sections["Queue"][0], "Queue counts will appear when a visible project is selected.")
        self.assertEqual(sections["Ready now"][0], "No visible projects in this workspace.")
        self.assertEqual(sections["Status"][0], "Workspace selected · no visible project details available.")
        self.assertEqual(view_model.detail_panel.title, "Empty workspace")
        self.assertEqual(view_model.detail_panel.metadata[0].value, "Waiting for visible projects")

    def test_build_home_view_model_uses_fallbacks_for_partial_ready_task_detail(self) -> None:
        view_model = build_home_view_model(
            HomeSnapshot(
                generated_at="2026-06-19T18:00:00Z",
                ready_tasks=(
                    ReadyTaskPreview(
                        task_id="",
                        description="",
                        state="",
                        priority="",
                        effort="low",
                        risk="",
                        task_type="",
                    ),
                ),
            )
        )

        metadata = {field.label: field.value for field in view_model.detail_panel.metadata}

        self.assertEqual(view_model.detail_panel.title, "Untitled task")
        self.assertEqual(view_model.detail_panel.eyebrow, "Selected context")
        self.assertEqual(metadata["Status"], "Unknown")
        self.assertEqual(metadata["Priority"], "Unknown")
        self.assertEqual(metadata["Effort"], "Low")
        self.assertEqual(metadata["Risk"], "Unknown")
        self.assertEqual(metadata["Type"], "Unknown")
        self.assertEqual(metadata["Task ID"], "Unknown")

    def test_load_home_view_model_falls_back_without_previous_snapshot(self) -> None:
        snapshot, view_model = load_home_view_model(
            snapshot_loader=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            repo_root="/tmp/demo",
            as_of="2026-06-19T18:00:00Z",
        )

        notes = {section.title: section.lines for section in view_model.sections}

        self.assertEqual(snapshot.bootstrap_state, "unavailable")
        self.assertEqual(view_model.updated_at, "Updated 2026-06-19T18:00:00Z")
        self.assertIn("Refresh failed unexpectedly.", notes["Notes"][0])

    def test_load_home_view_model_preserves_previous_snapshot_on_refresh_failure(self) -> None:
        previous_snapshot = HomeSnapshot(
            generated_at="2026-06-19T18:00:00Z",
            project_name="demo-repo",
            sync_summary="Local-only visibility · 0 pending routes · authority local-node",
        )

        snapshot, view_model = load_home_view_model(
            snapshot_loader=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
            repo_root="/tmp/demo",
            as_of="2026-06-19T18:05:00Z",
            previous_snapshot=previous_snapshot,
        )

        sections = {section.title: section.lines for section in view_model.sections}

        self.assertEqual(snapshot.project_name, "demo-repo")
        self.assertEqual(snapshot.generated_at, "2026-06-19T18:05:00Z")
        self.assertIn("demo-repo", sections["Current context"][0])
        self.assertIn("Refresh failed unexpectedly.", sections["Notes"][0])

    def test_resolve_browser_selection_falls_back_to_workspace_for_selected_project(self) -> None:
        snapshot = HomeSnapshot(
            workspaces=(
                WorkspaceSnapshot(
                    workspace_id="ws_1",
                    name="Workspace 1",
                    projects=(ProjectSnapshot(project_id="prj_1", workspace_id="ws_1", name="Project 1"),),
                ),
                WorkspaceSnapshot(
                    workspace_id="ws_2",
                    name="Workspace 2",
                    projects=(ProjectSnapshot(project_id="prj_2", workspace_id="ws_2", name="Project 2"),),
                ),
            )
        )

        selection = resolve_browser_selection(
            snapshot,
            selected_workspace_id="missing-workspace",
            selected_project_id="prj_2",
        )

        self.assertEqual(selection.workspace.workspace_id, "ws_2")
        self.assertEqual(selection.project.project_id, "prj_2")

    def test_resolve_browser_selection_falls_back_to_first_project_when_selected_project_is_missing(self) -> None:
        snapshot = HomeSnapshot(
            workspaces=(
                WorkspaceSnapshot(
                    workspace_id="ws_1",
                    name="Workspace 1",
                    projects=(
                        ProjectSnapshot(project_id="prj_1", workspace_id="ws_1", name="Project 1"),
                        ProjectSnapshot(project_id="prj_2", workspace_id="ws_1", name="Project 2"),
                    ),
                ),
            )
        )

        selection = resolve_browser_selection(
            snapshot,
            selected_workspace_id="ws_1",
            selected_project_id="missing-project",
        )

        self.assertEqual(selection.workspace.workspace_id, "ws_1")
        self.assertEqual(selection.project.project_id, "prj_1")

    def test_resolve_browser_selection_falls_back_to_first_ready_task_when_selected_task_is_missing(self) -> None:
        snapshot = HomeSnapshot(
            workspaces=(
                WorkspaceSnapshot(
                    workspace_id="ws_1",
                    name="Workspace 1",
                    projects=(
                        ProjectSnapshot(
                            project_id="prj_1",
                            workspace_id="ws_1",
                            name="Project 1",
                            ready_tasks=(
                                ReadyTaskPreview(
                                    task_id="tsk_1",
                                    description="First task",
                                    state="ready",
                                    priority="high",
                                    effort="low",
                                    risk="low",
                                    task_type="fix",
                                ),
                                ReadyTaskPreview(
                                    task_id="tsk_2",
                                    description="Second task",
                                    state="ready",
                                    priority="medium",
                                    effort="medium",
                                    risk="low",
                                    task_type="feature",
                                ),
                            ),
                        ),
                    ),
                ),
            )
        )

        selection = resolve_browser_selection(
            snapshot,
            selected_workspace_id="ws_1",
            selected_project_id="prj_1",
            selected_task_id="missing-task",
        )

        self.assertEqual(selection.task.task_id, "tsk_1")


class SplashContentTest(unittest.TestCase):
    def test_build_splash_content_uses_ascii_when_terminal_fits(self) -> None:
        splash = build_splash_content(
            available_width=20,
            available_height=10,
            ascii_art="####\n####",
        )

        self.assertEqual(splash.mode, "ascii")
        self.assertEqual(splash.lines, ("####", "####"))

    def test_build_splash_content_falls_back_when_terminal_is_too_small(self) -> None:
        splash = build_splash_content(
            available_width=8,
            available_height=4,
            ascii_art="########\n########",
        )

        self.assertEqual(splash.mode, "text")
        self.assertEqual(splash.lines, ("CapiForg",))

    def test_build_splash_content_truncates_fallback_brand_for_narrow_terminals(self) -> None:
        splash = build_splash_content(
            available_width=4,
            available_height=4,
            ascii_art="########\n########",
        )

        self.assertEqual(splash.mode, "text")
        self.assertEqual(splash.lines, ("Capi",))

    def test_build_splash_content_handles_zero_width_terminal_safely(self) -> None:
        splash = build_splash_content(
            available_width=0,
            available_height=4,
            ascii_art="########\n########",
        )

        self.assertEqual(splash.mode, "text")
        self.assertEqual(splash.lines, ("",))

    def test_build_splash_content_falls_back_when_art_is_missing(self) -> None:
        splash = build_splash_content(
            available_width=120,
            available_height=40,
            ascii_art="",
        )

        self.assertEqual(splash.mode, "text")
        self.assertEqual(splash.lines, ("CapiForge",))


@unittest.skipIf(HomeApp is None, "Textual is not installed")
class TextualHomeAppTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        from runtime.tui.data import PersistedTuiSettings

        self._persist_patcher = patch(
            "runtime.tui.shell.load_persisted_tui_state",
            return_value=PersistedTuiSettings(theme="neon"),
        )
        self._persist_patcher.start()

    def tearDown(self) -> None:
        self._persist_patcher.stop()

    def _capture_scheduled_callback(self):
        scheduled = {}

        def scheduler(delay_seconds: float, callback) -> None:
            scheduled["delay_seconds"] = delay_seconds
            scheduled["callback"] = callback

        return scheduled, scheduler

    def _assert_home_snapshot_is_visible(self, app: HomeApp) -> None:
        with self.assertRaises(NoMatches):
            app.query_one("#splash-content", Static)
        self.assertEqual(app.query_one("#sidenav-brand", Static).content, "CapiForge")

    def _sample_snapshot(self, **overrides) -> HomeSnapshot:
        base = HomeSnapshot(
            generated_at="2026-06-19T18:00:00Z",
            workspaces=(
                WorkspaceSnapshot(
                    workspace_id="ws_1",
                    name="Workspace 1",
                    projects=(
                        ProjectSnapshot(
                            project_id="prj_1",
                            workspace_id="ws_1",
                            name="Project 1",
                            all_tasks=(
                                ReadyTaskPreview(
                                    task_id="tsk_1",
                                    description="First task",
                                    state="in_progress",
                                    priority="high",
                                    effort="low",
                                    risk="low",
                                    task_type="fix",
                                    origin_audit_id="aud_1",
                                ),
                                ReadyTaskPreview(
                                    task_id="tsk_2",
                                    description="Second task",
                                    state="ready",
                                    priority="medium",
                                    effort="medium",
                                    risk="low",
                                    task_type="feature",
                                    origin_audit_id="aud_1",
                                ),
                            ),
                            ready_tasks=(
                                ReadyTaskPreview(
                                    task_id="tsk_2",
                                    description="Second task",
                                    state="ready",
                                    priority="medium",
                                    effort="medium",
                                    risk="low",
                                    task_type="feature",
                                    origin_audit_id="aud_1",
                                ),
                            ),
                            audits=(
                                AuditPreview(
                                    audit_id="aud_1",
                                    title="Design doc",
                                    state="published",
                                    content="Body",
                                ),
                            ),
                        ),
                    ),
                ),
            ),
        )
        for key, value in overrides.items():
            setattr(base, key, value)
        return base

    def test_on_mount_pushes_splash_before_loading_snapshot(self) -> None:
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: HomeSnapshot())

        with (
            patch.object(app, "push_screen") as push_screen,
            patch.object(app, "set_timer") as set_timer,
            patch.object(app, "_reload_snapshot") as reload_snapshot,
        ):
            app.on_mount()

        push_screen.assert_called_once()
        splash = push_screen.call_args.args[0]
        self.assertIsInstance(splash, StartupSplash)
        reload_snapshot.assert_not_called()
        set_timer.assert_called_once()
        self.assertEqual(set_timer.call_args.args[0], STARTUP_SNAPSHOT_DELAY_SECONDS)

    def test_on_mount_loads_snapshot_immediately_without_splash(self) -> None:
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: HomeSnapshot(),
            show_startup_splash=False,
        )

        with patch.object(app, "_reload_snapshot") as reload_snapshot:
            app.on_mount()

        reload_snapshot.assert_called_once_with()

    async def test_app_renders_shell_layout(self) -> None:
        snapshot = self._sample_snapshot(project_name="demo-repo", workspace_name="demo-workspace")
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as _pilot:
            self.assertEqual(app.query_one("#sidenav-brand", Static).content, "CapiForge")
            self.assertEqual(app.query_one("#page-title", Static).content, "Project 1")
            self.assertIn("Workspace 1", app.query_one("#breadcrumb", Static).content)

    async def test_empty_workspace_state_renders_cta(self) -> None:
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: HomeSnapshot(generated_at="2026-06-19T18:00:00Z"),
            show_startup_splash=False,
        )

        async with app.run_test() as _pilot:
            self.assertIn("primer workspace", str(app.query_one("#content-main", Static).content))

    async def test_tasks_view_renders_neon_pills(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("t")
            await pilot.pause()
            table = app.query_one("#tasks-table", DataTable)
            first_row = table.get_row("tsk_1")
            self.assertIn("First task", str(first_row[0]))
            self.assertIn("In Progress", str(first_row[1]))
            second_row = table.get_row("tsk_2")
            self.assertIn("Ready", str(second_row[1]))

    async def test_tasks_view_uses_datatable_with_row_cursor(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()
            table = app.query_one("#tasks-table", DataTable)
            self.assertTrue(table.has_class("visible"))
            self.assertEqual(table.cursor_type, "row")
            self.assertEqual(app._focus_panel, "content")
            self.assertTrue(app.query_one("#content-panel").has_class("panel-focused"))

    async def test_docs_view_renders_audit_list(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("o")
            await pilot.pause()
            doc_row = app.query_one(".doc-row", DocRow)
            self.assertIn("Design doc", str(doc_row.render()))
            detail = app.query_one("#docs-detail-content", Static)
            from io import StringIO

            from rich.console import Console

            buffer = StringIO()
            Console(file=buffer, width=120, force_terminal=True).print(detail.content)
            self.assertIn("Body", buffer.getvalue())
            self.assertTrue(app.query_one("#docs-shell", Vertical).has_class("visible"))
            label = app.query_one("#docs-tasks-label", Static)
            self.assertIn("Tareas vinculadas · 2", str(label.content))
            task_rows = app.query(AuditTaskRow)
            self.assertEqual(len(task_rows), 2)

    async def test_click_audit_task_row_opens_tasks_with_detail(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("o")
            await pilot.pause()
            task_row = app.query_one(AuditTaskRow)
            await pilot.click(task_row)
            await pilot.pause()
            self.assertEqual(app._nav.view, "project_tasks")
            self.assertEqual(app._nav.selected_task_id, "tsk_1")
            self.assertEqual(app._nav.task_filter, "all")
            drawer = app.query_one("#task-drawer", Static)
            self.assertTrue(drawer.has_class("visible"))
            self.assertIn("tsk_1", str(drawer.content))
            self.assertIn("Design doc", str(drawer.content))

    async def test_refresh_binding_reloads_snapshot(self) -> None:
        snapshots = iter(
            [
                self._sample_snapshot(),
                self._sample_snapshot(
                    workspaces=(
                        WorkspaceSnapshot(
                            workspace_id="ws_1",
                            name="Workspace refreshed",
                            projects=(
                                ProjectSnapshot(project_id="prj_1", workspace_id="ws_1", name="Project refreshed"),
                            ),
                        ),
                    )
                ),
            ]
        )
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: next(snapshots), show_startup_splash=False)

        async with app.run_test() as pilot:
            self.assertIn("Project 1", app.query_one("#breadcrumb", Static).content)
            await pilot.press("r")
            await pilot.pause()
            self.assertIn("Project refreshed", app.query_one("#breadcrumb", Static).content)

    async def test_filter_cycles_in_tasks_view(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t", "f")
            await pilot.pause()
            self.assertEqual(app._nav.task_filter, "active")
            active_pill = app.query_one(".filter-pill--active", FilterPill)
            self.assertIn("[2] Activas", str(active_pill.content))

    async def test_number_key_sets_task_filter(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t", "4")
            await pilot.pause()
            self.assertEqual(app._nav.task_filter, "done")

    async def test_command_palette_opens_with_question_mark(self) -> None:
        from textual.command import CommandPalette

        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("?")
            await pilot.pause()
            self.assertIsInstance(app.screen, CommandPalette)

    async def test_footer_shows_contextual_task_hints(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()
            footer = app.query_one("#footer-hints", Static).content
            self.assertIn("Ctrl+P Comandos", footer)
            self.assertIn("1-4 Filtro", footer)
            self.assertIn("Click header ordenar", footer)
            self.assertIn("Enter/o Auditoría", footer)
            self.assertIn("a Nueva", footer)
            self.assertIn("g Auto-refresh", footer)

    async def test_home_shows_next_ready_task(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as _pilot:
            content = str(app.query_one("#content-main", Static).content)
            self.assertIn("Siguiente lista", content)
            self.assertIn("Second task", content)
            self.assertIn("c para claim", content)

    async def test_refresh_status_shows_auto_refresh_label(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: snapshot,
            show_startup_splash=False,
            auto_refresh_seconds=15,
        )

        async with app.run_test() as _pilot:
            status = app.query_one("#refresh-status", Static).content
            self.assertIn("actualizado hace", status)
            self.assertIn("auto 15s", status)

    async def test_toggle_auto_refresh_cycles_interval(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: snapshot,
            show_startup_splash=False,
            auto_refresh_seconds=15,
        )

        async with app.run_test() as pilot:
            await pilot.press("g")
            await pilot.pause()
            self.assertEqual(app._auto_refresh_seconds, 30)
            status = app.query_one("#refresh-status", Static).content
            self.assertIn("auto 30s", status)

    async def test_nav_down_selects_tasks_in_tasks_view(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t", "down")
            await pilot.pause()
            self.assertEqual(app._nav.selected_task_id, "tsk_2")
            drawer = str(app.query_one("#task-drawer", Static).content)
            self.assertIn("tsk_2", drawer)
            self.assertIn("Design doc", drawer)

    async def test_tab_switches_focus_between_sidenav_and_content(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()
            self.assertEqual(app._focus_panel, "content")
            await pilot.press("tab")
            await pilot.pause()
            self.assertEqual(app._focus_panel, "sidenav")
            self.assertTrue(app.query_one("#sidenav").has_class("panel-focused"))
            await pilot.press("shift+tab")
            await pilot.pause()
            self.assertEqual(app._focus_panel, "content")

    async def test_task_table_header_click_sorts_by_state(self) -> None:
        from rich.text import Text

        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("t")
            await pilot.pause()
            table = app.query_one("#tasks-table", DataTable)
            app.on_data_table_header_selected(DataTable.HeaderSelected(table, "state", 1, label=Text("Estado")))
            await pilot.pause()
            self.assertEqual(app._task_sort_column, "state")
            self.assertFalse(app._task_sort_reverse)
            first_row = table.get_row_at(0)
            self.assertIn("Ready", str(first_row[1]))

    async def test_task_detail_panel_opens_linked_audit_with_o(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()
            drawer = app.query_one("#task-drawer", Static)
            self.assertTrue(drawer.has_class("visible"))
            self.assertIn("tsk_1", str(drawer.content))
            self.assertIn("Design doc", str(drawer.content))
            await pilot.press("o")
            await pilot.pause()
            self.assertEqual(app._nav.view, "project_docs")
            self.assertEqual(app._nav.selected_audit_id, "aud_1")

    async def test_mouse_click_nav_row_opens_tasks_view(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            tasks_row = next(row for row in app.query(NavRow) if "Tareas" in str(row.render()))
            await pilot.click(tasks_row)
            await pilot.pause()
            self.assertEqual(app._nav.view, "project_tasks")
            self.assertEqual(app._focus_panel, "content")

    async def test_mouse_click_filter_pill_sets_filter(self) -> None:
        from textual.events import Click

        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("t")
            await pilot.pause()
            done_pill = app.query_one("#filter-done", FilterPill)
            app.on_click(Click(done_pill, 0, 0, 0, 0, 1, False, False, False, chain=1))
            await pilot.pause()
            self.assertEqual(app._nav.task_filter, "done")

    async def test_mouse_click_doc_row_selects_audit(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            await pilot.press("o")
            await pilot.pause()
            doc_row = app.query_one(".doc-row", DocRow)
            await pilot.click(doc_row)
            await pilot.pause()
            self.assertEqual(app._nav.selected_audit_id, "aud_1")
            self.assertTrue(doc_row.has_class("doc-row--selected"))

    async def test_docs_prev_next_buttons_navigate_audits(self) -> None:
        snapshot = self._sample_snapshot(
            workspaces=(
                WorkspaceSnapshot(
                    workspace_id="ws_1",
                    name="Workspace 1",
                    projects=(
                        ProjectSnapshot(
                            project_id="prj_1",
                            workspace_id="ws_1",
                            name="Project 1",
                            audits=(
                                AuditPreview(audit_id="aud_1", title="Design doc", state="published", content="Body 1"),
                                AuditPreview(audit_id="aud_2", title="Second doc", state="published", content="Body 2"),
                            ),
                        ),
                    ),
                ),
            )
        )
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.press("o")
            await pilot.pause()
            self.assertEqual(app._nav.selected_audit_id, "aud_1")
            await pilot.click("#docs-next")
            await pilot.pause()
            self.assertEqual(app._nav.selected_audit_id, "aud_2")
            detail = app.query_one("#docs-detail-content", Static)
            from io import StringIO

            from rich.console import Console

            buffer = StringIO()
            Console(file=buffer, width=120, force_terminal=True).print(detail.content)
            self.assertIn("Body 2", buffer.getvalue())
            await pilot.click("#docs-prev")
            await pilot.pause()
            self.assertEqual(app._nav.selected_audit_id, "aud_1")

    async def test_refresh_binding_shows_notice_when_loader_raises(self) -> None:
        snapshots = iter([self._sample_snapshot(), RuntimeError("boom")])

        def loader(**_kwargs):
            value = next(snapshots)
            if isinstance(value, Exception):
                raise value
            return value

        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=loader, show_startup_splash=False)

        async with app.run_test() as pilot:
            await pilot.press("r")
            await pilot.pause()
            self.assertIn("Refresh failed", app.query_one("#status-bar", Static).content)

    async def test_startup_splash_auto_dismisses_after_duration(self) -> None:
        snapshot = self._sample_snapshot(project_name="demo-repo")
        startup_schedule, startup_scheduler = self._capture_scheduled_callback()
        dismiss_schedule, dismiss_scheduler = self._capture_scheduled_callback()
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: snapshot,
            splash_duration_seconds=0.25,
            startup_snapshot_scheduler=startup_scheduler,
            splash_dismiss_scheduler=dismiss_scheduler,
        )

        async with app.run_test() as pilot:
            self.assertEqual(app.screen.id, "startup-splash")
            startup_schedule["callback"]()
            dismiss_schedule["callback"]()
            await pilot.pause()
            self.assertNotEqual(app.screen.id, "startup-splash")
            self._assert_home_snapshot_is_visible(app)

    async def test_startup_splash_q_dismisses_without_quitting_app(self) -> None:
        snapshot = self._sample_snapshot(project_name="demo-repo")
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: snapshot,
            splash_duration_seconds=60,
        )

        async with app.run_test() as pilot:
            self.assertEqual(app.screen.id, "startup-splash")
            await pilot.press("q")
            await pilot.pause()
            self.assertNotEqual(app.screen.id, "startup-splash")
            self._assert_home_snapshot_is_visible(app)

    async def test_cycle_theme_binding_switches_palette(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(repo_root="/tmp/demo", snapshot_loader=lambda **_kwargs: snapshot, show_startup_splash=False, theme="neon")

        async with app.run_test() as pilot:
            self.assertEqual(app._theme_name, "neon")
            await pilot.press("T")
            await pilot.pause()
            self.assertEqual(app._theme_name, "notion")
            footer = app.query_one("#footer-hints", Static).content
            self.assertIn("Notion", footer)

    async def test_cli_theme_argument_selects_initial_theme(self) -> None:
        snapshot = self._sample_snapshot()
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: snapshot,
            show_startup_splash=False,
            theme="light",
        )

        async with app.run_test() as _pilot:
            self.assertEqual(app._theme_name, "light")
            footer = app.query_one("#footer-hints", Static).content
            self.assertIn("Light", footer)

    async def test_startup_splash_resize_switches_between_ascii_and_text(self) -> None:
        snapshot = self._sample_snapshot(project_name="demo-repo")
        app = HomeApp(
            repo_root="/tmp/demo",
            snapshot_loader=lambda **_kwargs: snapshot,
            splash_art_loader=lambda **_kwargs: "####\n####",
            splash_duration_seconds=60,
        )

        async with app.run_test(size=(20, 10)) as pilot:
            splash_content = app.screen.query_one("#splash-content", Static)
            self.assertTrue(splash_content.has_class("ascii"))
            self.assertEqual(splash_content.content, "####\n####")

            await pilot.resize_terminal(8, 4)
            splash_content = app.screen.query_one("#splash-content", Static)
            self.assertTrue(splash_content.has_class("text"))
            self.assertEqual(splash_content.content, "CapiForg")


class DocsRenderingTest(unittest.TestCase):
    def test_build_docs_detail_content_renders_markdown_heading(self) -> None:
        from io import StringIO

        from rich.console import Console

        from runtime.tui.data import AuditPreview
        from runtime.tui.view import build_docs_detail_content

        audit = AuditPreview(
            audit_id="aud_demo",
            title="Demo",
            state="published",
            content="## Fases entregadas\n\n- Shell + navegación",
        )
        buffer = StringIO()
        console = Console(file=buffer, force_terminal=True, width=80)
        console.print(build_docs_detail_content(audit))
        output = buffer.getvalue()
        self.assertIn("Fases entregadas", output)
        self.assertIn("Shell", output)

    def test_docs_list_row_preserves_state_styles(self) -> None:
        from rich.text import Text

        from runtime.tui.theme import labelize, render_pill, style_for_audit_state

        row = Text("Demo audit")
        row.append_text(render_pill(labelize("published"), style_for_audit_state("published")))
        self.assertTrue(any(span.style for span in row.spans))

    def test_estimate_docs_detail_lines_scales_with_content(self) -> None:
        from runtime.tui.view import estimate_docs_detail_lines

        short = AuditPreview(audit_id="aud_1", title="Short", state="published", content="Brief")
        long = AuditPreview(
            audit_id="aud_2",
            title="Long",
            state="published",
            content="## Alcance\n\n" + "\n".join(f"- item {index}" for index in range(12)),
        )
        self.assertLess(estimate_docs_detail_lines(short, width=80), estimate_docs_detail_lines(long, width=80))


class ThemeTest(unittest.TestCase):
    def test_render_pill_uses_neon_style(self) -> None:
        from runtime.tui.theme import render_pill, set_active_theme, style_for_task_state

        set_active_theme("neon")
        pill = render_pill("In Progress", style_for_task_state("in_progress"))
        self.assertIn("In Progress", str(pill))
        self.assertIn("bright_blue", style_for_task_state("in_progress"))

    def test_notion_theme_uses_muted_styles(self) -> None:
        from runtime.tui.theme import set_active_theme, style_for_task_state

        set_active_theme("notion")
        self.assertEqual(style_for_task_state("in_progress"), "bold blue")

    def test_build_task_filters_bar_marks_active_filter(self) -> None:
        from runtime.tui.view import build_task_filters_bar

        bar = build_task_filters_bar("blocked")
        rendered = str(bar)
        self.assertIn("[3] Bloqueadas", rendered)
        self.assertIn("[1] Todas", rendered)

    def test_sort_tasks_for_view_orders_by_priority(self) -> None:
        from runtime.tui.data import TaskPreview
        from runtime.tui.view import sort_tasks_for_view

        tasks = (
            TaskPreview("tsk_1", "Alpha", "ready", "low", "low", "low", "fix"),
            TaskPreview("tsk_2", "Beta", "ready", "critical", "low", "low", "fix"),
        )
        ordered = sort_tasks_for_view(tasks, sort_column="priority", reverse=True)
        self.assertEqual(ordered[0].task_id, "tsk_2")

    def test_build_task_table_row_renders_neon_state_pill(self) -> None:
        from runtime.tui.data import TaskPreview
        from runtime.tui.theme import set_active_theme, style_for_task_state
        from runtime.tui.view import TASK_TABLE_COLUMNS, build_task_table_row, compute_task_column_widths

        set_active_theme("neon")
        task = TaskPreview(
            task_id="tsk_1",
            description="First task",
            state="in_progress",
            priority="high",
            effort="low",
            risk="low",
            task_type="fix",
            origin_audit_id="aud_1",
        )
        widths = {**compute_task_column_widths(120), "state": 14}
        row = build_task_table_row(
            task,
            audits=(AuditPreview(audit_id="aud_1", title="Design doc", state="published"),),
            column_widths=widths,
        )
        self.assertEqual(len(row), len(TASK_TABLE_COLUMNS))
        self.assertEqual(row[0], "First task")
        self.assertIn("In Progress", str(row[1]))
        self.assertIn("bright_blue", style_for_task_state("in_progress"))
        self.assertIn("Design doc", str(row[-1]))

    def test_tasks_for_audit_filters_by_origin(self) -> None:
        from runtime.tui.data import TaskPreview
        from runtime.tui.view import tasks_for_audit

        tasks = (
            TaskPreview("tsk_1", "One", "done", "high", "low", "low", "fix", origin_audit_id="aud_1"),
            TaskPreview("tsk_2", "Two", "done", "medium", "low", "low", "feature", origin_audit_id="aud_2"),
        )
        linked = tasks_for_audit(tasks, "aud_1")
        self.assertEqual([task.task_id for task in linked], ["tsk_1"])

    def test_build_task_drawer_includes_audit_navigation(self) -> None:
        from runtime.tui.data import TaskPreview
        from runtime.tui.view import build_task_drawer

        task = TaskPreview(
            task_id="tsk_1",
            description="Ship the task table",
            state="ready",
            priority="high",
            effort="low",
            risk="low",
            task_type="feature",
            origin_audit_id="aud_1",
            lifecycle_key="lifecycle://demo",
        )
        drawer = build_task_drawer(
            task,
            audits=(AuditPreview(audit_id="aud_1", title="Design doc", state="published"),),
        )
        rendered = str(drawer)
        self.assertIn("tsk_1", rendered)
        self.assertIn("Design doc", rendered)
        self.assertIn("aud_1", rendered)
        self.assertIn("Documentación", rendered)
        self.assertIn("lifecycle://demo", rendered)
        self.assertIn("Ship the task table", rendered)

    def test_compute_task_column_widths_fits_available_width(self) -> None:
        from runtime.tui.view import compute_task_column_widths

        for available in (72, 90, 120, 160):
            widths = compute_task_column_widths(available)
            self.assertLessEqual(sum(widths.values()), available)
            self.assertGreaterEqual(widths["description"], 12)

    def test_next_theme_cycles_in_order(self) -> None:
        from runtime.tui.theme import next_theme_name, set_active_theme

        set_active_theme("neon")
        self.assertEqual(next_theme_name(), "notion")
        set_active_theme("light")
        self.assertEqual(next_theme_name(), "neon")

    def test_persisted_theme_round_trip(self) -> None:
        from runtime.tui.data import NavState, PersistedTuiSettings, persist_tui_state, load_persisted_tui_state

        with tempfile.TemporaryDirectory() as tempdir:
            with patch.object(Path, "home", return_value=Path(tempdir)):
                persist_tui_state(nav=NavState(view="project_home"), theme="light", auto_refresh_seconds=30)
                settings = load_persisted_tui_state()
                self.assertEqual(settings.theme, "light")
                self.assertEqual(settings.auto_refresh_seconds, 30)
                self.assertIsNotNone(settings.nav)


class ActionsTest(unittest.TestCase):
    def test_create_workspace_persists_to_store(self) -> None:
        from runtime.tui.actions import create_workspace

        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            result = create_workspace(repo_root=repo_root, node_home=None, name="My Workspace")
            self.assertTrue(result.ok, result.message)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            state = bootstrap.status(interactive=False)
            store = NodeStore.from_file(state.node_db_path)
            self.addCleanup(store.close)
            workspaces = store.list_workspaces()
            self.assertEqual(len(workspaces), 1)
            self.assertEqual(workspaces[0]["name"], "My Workspace")

    def test_create_task_persists_to_store(self) -> None:
        from runtime.tui.actions import create_task

        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()
            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_audit(
                "aud_tui",
                adopted_state.adopted_project["project_id"],
                "published",
                "TUI audit",
                "body",
            )
            store.db.commit()

            result = create_task(
                repo_root=repo_root,
                node_home=None,
                project_id=adopted_state.adopted_project["project_id"],
                description="Task from TUI",
            )
            self.assertTrue(result.ok, result.message)
            tasks = store.list_project_tasks(adopted_state.adopted_project["project_id"])
            descriptions = {task["description"] for task in tasks}
            self.assertIn("Task from TUI", descriptions)

    def test_create_task_requires_published_audit(self) -> None:
        from runtime.tui.actions import create_task

        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()

            result = create_task(
                repo_root=repo_root,
                node_home=None,
                project_id=adopted_state.adopted_project["project_id"],
                description="Should fail",
            )
            self.assertFalse(result.ok)
            self.assertIn("audit", result.message.lower())


class StoreProjectTasksTest(unittest.TestCase):
    def test_list_project_tasks_returns_all_states(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            repo_root = Path(tempdir) / "repo"
            repo_root.mkdir(parents=True, exist_ok=True)
            bootstrap = NodeBootstrap(repo_root=repo_root)
            adopted_state = bootstrap.open_or_init()
            adopted_state = bootstrap.adopt_repo()
            store = NodeStore.from_file(adopted_state.node_db_path)
            self.addCleanup(store.close)
            store.create_audit("aud_1", adopted_state.adopted_project["project_id"], "published", "Audit", "body")
            store.create_task("tsk_ready", adopted_state.adopted_project["project_id"], "aud_1", "ready", "high", "low", "low", "fix", "Ready task")
            store.create_task("tsk_progress", adopted_state.adopted_project["project_id"], "aud_1", "in_progress", "medium", "low", "low", "fix", "Active task", active_claim_session_id="sess_1")
            store.db.commit()

            tasks = store.list_project_tasks(adopted_state.adopted_project["project_id"])
            states = {task["state"] for task in tasks}
            self.assertEqual(states, {"ready", "in_progress"})
            for task in tasks:
                self.assertEqual(task["origin_audit_id"], "aud_1")
                self.assertIn("lifecycle_key", task)
                self.assertIn("blocked_reason", task)
                self.assertIn("blocked_next_step", task)


if __name__ == "__main__":
    unittest.main()
