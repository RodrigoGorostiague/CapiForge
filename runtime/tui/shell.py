from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Literal, Sequence

from collections.abc import Iterable

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult, ScreenStackError, SystemCommand
from textual.binding import Binding
from textual.command import CommandPalette
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import DataTable, Footer, Input, Static

from runtime.tui.commands import iter_shell_commands

from runtime.paths import default_repo_root
from runtime.tui.actions import (
    ActionResult,
    claim_task,
    create_project,
    create_task,
    create_workspace,
    release_task,
    transition_task,
)
from runtime.tui.data import (
    AUTO_REFRESH_OPTIONS,
    AppSnapshot,
    AuditPreview,
    DEFAULT_AUTO_REFRESH_SECONDS,
    NavState,
    ProjectSnapshot,
    default_nav_state,
    count_tasks_by_filter,
    filter_tasks,
    load_home_snapshot,
    load_persisted_tui_state,
    persist_tui_state,
    resolve_nav_selection,
)
from runtime.tui.nav import (
    NavNode,
    active_nav_node_id,
    build_nav_tree,
    nav_state_for_node,
    toggle_expand_for_focused_node,
)
from runtime.tui.splash import SPLASH_DURATION_SECONDS, build_splash_content, load_splash_art
from runtime.tui.theme import (
    APP_CSS,
    SIDENAV_WIDTH,
    active_theme,
    css_for_theme,
    labelize,
    next_theme_name,
    normalize_theme_name,
    render_pill,
    set_active_theme,
    style_for_audit_state,
    theme_names,
)
from runtime.tui.view import (
    TASK_FILTER_OPTIONS,
    TASK_SORTABLE_COLUMNS,
    TASK_TABLE_COLUMNS,
    build_audit_task_row_label,
    build_filter_pill_label,
    build_content_view_model,
    build_docs_detail_content,
    build_footer_hints,
    build_sync_status_light,
    build_task_column_label,
    build_task_table_row,
    compute_docs_detail_height,
    compute_task_column_widths,
    estimate_docs_detail_lines,
    resolve_selected_audit,
    sort_tasks_for_view,
    tasks_for_audit,
)
from runtime.tui.widgets import AuditTaskRow, DocRow, FilterPill, NavRow

STARTUP_SNAPSHOT_DELAY_SECONDS = 0.001
THEME_CSS_LOCATION = ("runtime.tui.theme", "active-theme")
FocusPanel = Literal["sidenav", "content"]
TimerScheduler = Callable[[float, Callable[[], None]], object]
TASK_FILTERS = tuple(option[0] for option in TASK_FILTER_OPTIONS)


def build_parser(*, prog: str = "capiforge tui") -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=prog)
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--node-home")
    parser.add_argument("--as-of")
    parser.add_argument("--theme", choices=theme_names(), default=None, help="Color theme: neon, notion, or light")
    parser.add_argument(
        "--auto-refresh",
        type=int,
        default=None,
        choices=AUTO_REFRESH_OPTIONS,
        help="Auto-refresh interval in seconds (0=off, 15, 30, 60)",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, prog: str = "capiforge tui") -> int:
    args = build_parser(prog=prog).parse_args(list(argv) if argv is not None else None)
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("The TUI requires an interactive terminal.", file=sys.stderr)
        return 1
    app = ShellApp(
        repo_root=args.repo_root,
        node_home=args.node_home,
        as_of=args.as_of,
        theme=args.theme,
        auto_refresh_seconds=args.auto_refresh,
    )
    app.run()
    return 0


class NameModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, title: str, placeholder: str, *, initial: str = "") -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Container(classes="modal-panel"):
            yield Static(self._title, classes="modal-title")
            yield Input(placeholder=self._placeholder, value=self._initial, id="modal-input")
            yield Static("Enter confirmar  ·  Esc cancelar", classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#modal-input", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        value = self.query_one("#modal-input", Input).value.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class TaskModal(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", show=False)]

    def __init__(self, title: str, placeholder: str) -> None:
        super().__init__()
        self._title = title
        self._placeholder = placeholder

    def compose(self) -> ComposeResult:
        with Container(classes="modal-panel"):
            yield Static(self._title, classes="modal-title")
            yield Input(placeholder=self._placeholder, id="modal-input")
            yield Static("Enter confirmar  ·  Esc cancelar", classes="modal-hint")

    def on_mount(self) -> None:
        self.query_one("#modal-input", Input).focus()

    def on_input_submitted(self, _event: Input.Submitted) -> None:
        value = self.query_one("#modal-input", Input).value.strip()
        self.dismiss(value or None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ShellApp(App[None]):
    CSS = APP_CSS
    COMMAND_PALETTE_BINDING = "ctrl+p"
    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "refresh", "Refresh", show=True),
        Binding("ctrl+p", "command_palette", "Commands", show=True),
        Binding("a", "new_task", "New task", show=False),
        Binding("g", "toggle_auto_refresh", "Auto", show=False),
        Binding("n", "new_workspace", "Workspace", show=False),
        Binding("p", "new_project", "Project", show=False),
        Binding("o", "open_docs", "Docs", show=False),
        Binding("T", "cycle_theme", "Theme", show=False),
        Binding("t", "open_tasks", "Tasks", show=False),
        Binding("h", "open_home", "Home", show=False),
        Binding("f", "cycle_filter", "Filter", show=False),
        Binding("c", "claim_selected", "Claim", show=False),
        Binding("s", "start_selected", "Start", show=False),
        Binding("b", "block_selected", "Block", show=False),
        Binding("d", "done_selected", "Done", show=False),
        Binding("x", "release_selected", "Release", show=False),
        Binding("left", "collapse_nav", show=False),
        Binding("right", "expand_nav", show=False),
        Binding("[", "docs_prev", show=False),
        Binding("]", "docs_next", show=False),
        Binding("up", "nav_up", show=False),
        Binding("down", "nav_down", show=False),
        Binding("escape", "close_drawer", show=False),
        Binding("enter", "activate", show=False),
    ]

    def __init__(
        self,
        *,
        repo_root: str,
        node_home: str | None = None,
        as_of: str | None = None,
        theme: str | None = None,
        auto_refresh_seconds: int | None = None,
        snapshot_loader=load_home_snapshot,
        splash_art_loader=load_splash_art,
        splash_duration_seconds: float = SPLASH_DURATION_SECONDS,
        show_startup_splash: bool = True,
        startup_snapshot_scheduler: TimerScheduler | None = None,
        splash_dismiss_scheduler: TimerScheduler | None = None,
    ) -> None:
        super().__init__()
        persisted = load_persisted_tui_state()
        self._theme_name = normalize_theme_name(theme or persisted.theme)
        palette = set_active_theme(self._theme_name)
        self.dark = palette.dark
        self._auto_refresh_seconds = (
            auto_refresh_seconds
            if auto_refresh_seconds is not None
            else persisted.auto_refresh_seconds
        )
        self._refreshed_at = time.monotonic()
        self._auto_refresh_timer = None
        self._refresh_status_timer = None
        self._repo_root = repo_root
        self._node_home = node_home
        self._as_of = as_of
        self._snapshot_loader = snapshot_loader
        self._splash_art_loader = splash_art_loader
        self._splash_duration_seconds = splash_duration_seconds
        self._show_startup_splash = show_startup_splash
        self._startup_snapshot_scheduler = startup_snapshot_scheduler
        self._splash_dismiss_scheduler = splash_dismiss_scheduler
        self._current_snapshot: AppSnapshot | None = None
        self._nav = persisted.nav or NavState()
        self._nav_focus_index = 0
        self._focus_panel: FocusPanel = "sidenav"
        self._drawer_open = False
        self._task_sort_column = "description"
        self._task_sort_reverse = False
        self._startup_snapshot_ready = False
        self._startup_splash_dismiss_requested = False
        self._startup_splash: StartupSplash | None = None
        self._sync_refreshing = False

    def compose(self) -> ComposeResult:
        with Horizontal(id="layout"):
            with Vertical(id="sidenav"):
                yield Static("CapiForge", id="sidenav-brand")
                yield Static("+ Nuevo workspace", id="nav-action", classes="sidenav-action clickable")
                yield VerticalScroll(id="nav-tree")
            with Vertical(id="content-panel"):
                with Container(id="content-header"):
                    with Horizontal(id="content-header-top"):
                        with Vertical(id="content-header-left"):
                            yield Static(id="breadcrumb")
                            with Horizontal(id="title-row"):
                                yield Static(id="page-title")
                                yield Static("", id="task-meta")
                        yield Static(id="refresh-status")
                    yield Static("─" * 48, id="header-rule")
                yield Horizontal(id="task-filters", classes="hidden")
                yield DataTable(id="tasks-table", cursor_type="row", zebra_stripes=True)
                yield Static("", id="tasks-empty")
                with Vertical(id="docs-shell", classes="hidden"):
                    yield Static(id="docs-index-label")
                    yield Container(id="docs-list")
                    with Vertical(id="docs-detail"):
                        with Horizontal(id="docs-detail-toolbar"):
                            yield Static(id="docs-detail-title")
                            yield Static("◀ Prev", id="docs-prev", classes="clickable docs-nav-btn")
                            yield Static("Next ▶", id="docs-next", classes="clickable docs-nav-btn")
                        with VerticalScroll(id="docs-detail-scroll"):
                            yield Static(id="docs-detail-content")
                    with Vertical(id="docs-tasks-section"):
                        yield Static(id="docs-tasks-label")
                        yield Container(id="docs-tasks-list")
                with VerticalScroll(id="content-body"):
                    yield Static(id="content-main")
                yield Static(id="task-drawer")
                yield Static("", id="footer-hints")
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._apply_theme(self._theme_name)
        if self._show_startup_splash:
            self._startup_splash = StartupSplash(
                repo_root=self._repo_root,
                splash_art_loader=self._splash_art_loader,
                duration_seconds=self._splash_duration_seconds,
                dismiss_scheduler=self._splash_dismiss_scheduler,
            )
            self.push_screen(self._startup_splash)
            self._schedule_startup_snapshot(STARTUP_SNAPSHOT_DELAY_SECONDS, self._load_initial_snapshot)
            return
        self._load_initial_snapshot()

    def _start_refresh_status_timer(self) -> None:
        if self._refresh_status_timer is not None:
            self._refresh_status_timer.stop()
        try:
            self._refresh_status_timer = self.set_interval(1.0, self._render_refresh_status)
        except RuntimeError:
            self._refresh_status_timer = None

    def _start_auto_refresh(self) -> None:
        if self._auto_refresh_timer is not None:
            self._auto_refresh_timer.stop()
            self._auto_refresh_timer = None
        if self._auto_refresh_seconds <= 0:
            return
        try:
            self._auto_refresh_timer = self.set_interval(float(self._auto_refresh_seconds), self._auto_refresh_tick)
        except RuntimeError:
            self._auto_refresh_timer = None

    def _auto_refresh_tick(self) -> None:
        self._reload_snapshot(quiet=True)

    def on_resize(self, event: events.Resize) -> None:
        if isinstance(self.screen, StartupSplash):
            return
        self._maybe_reflow_tasks_table()
        self._update_docs_detail_layout()

    def action_docs_prev(self) -> None:
        self._navigate_docs(-1)

    def action_docs_next(self) -> None:
        self._navigate_docs(1)

    def _navigate_docs(self, step: int) -> None:
        if self._nav.view != "project_docs":
            return
        snapshot = self._current_snapshot
        if snapshot is None:
            return
        _workspace, project = resolve_nav_selection(snapshot, self._nav)
        if project is None or not project.audits:
            return
        current_index = next(
            (index for index, audit in enumerate(project.audits) if audit.audit_id == self._nav.selected_audit_id),
            0,
        )
        next_index = min(max(current_index + step, 0), len(project.audits) - 1)
        next_audit = project.audits[next_index]
        linked_task_ids = self._linked_task_ids_for_audit(next_audit.audit_id)
        self._nav = NavState(
            workspace_id=self._nav.workspace_id,
            project_id=self._nav.project_id,
            view=self._nav.view,
            selected_task_id=linked_task_ids[0] if linked_task_ids else None,
            selected_audit_id=next_audit.audit_id,
            task_filter=self._nav.task_filter,
            expanded_workspaces=self._nav.expanded_workspaces,
            expanded_projects=self._nav.expanded_projects,
        )
        self._render_content()

    def _current_docs_audit(self) -> AuditPreview | None:
        snapshot = self._current_snapshot
        if snapshot is None or self._nav.view != "project_docs":
            return None
        _workspace, project = resolve_nav_selection(snapshot, self._nav)
        if project is None or not project.audits:
            return None
        return resolve_selected_audit(project.audits, self._nav.selected_audit_id)

    def _update_docs_detail_layout(self, *, audit: AuditPreview | None = None) -> None:
        if self._nav.view != "project_docs":
            return
        try:
            detail = self.query_one("#docs-detail", Vertical)
            scroll = self.query_one("#docs-detail-scroll", VerticalScroll)
        except Exception:
            return

        selected = audit if audit is not None else self._current_docs_audit()
        if selected is None:
            line_count = 4
        else:
            width = scroll.size.width if scroll.size.width > 0 else max(40, self.size.width - SIDENAV_WIDTH - 8)
            line_count = estimate_docs_detail_lines(selected, width=width)

        height = compute_docs_detail_height(line_count, screen_height=self.size.height)
        detail.styles.height = height
        detail.styles.max_height = max(8, self.size.height // 2)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "tasks-table":
            return
        column_key = str(event.column_key)
        if column_key not in TASK_SORTABLE_COLUMNS:
            return
        if self._task_sort_column == column_key:
            self._task_sort_reverse = not self._task_sort_reverse
        else:
            self._task_sort_column = column_key
            self._task_sort_reverse = False
        self._maybe_reflow_tasks_table()

    def _content_panel_width(self) -> int:
        try:
            panel = self.query_one("#content-panel")
            if panel.size.width > 0:
                return panel.size.width
        except Exception:
            pass
        return max(48, self.size.width - SIDENAV_WIDTH)

    def _tasks_table_width(self, table: DataTable | None = None) -> int:
        if table is not None and table.size.width > 0:
            return table.size.width
        return max(48, self._content_panel_width() - 8)

    def _maybe_reflow_tasks_table(self) -> None:
        if self._nav.view != "project_tasks" or self._current_snapshot is None:
            return
        try:
            table = self.query_one("#tasks-table", DataTable)
        except Exception:
            return
        if not table.has_class("visible"):
            return
        view_model = build_content_view_model(
            self._current_snapshot,
            self._nav,
            content_width=self._content_panel_width(),
        )
        if view_model.tasks is None:
            return
        self._populate_tasks_table(table, view_model.tasks)

    def on_click(self, event: events.Click) -> None:
        if isinstance(self.screen, (ModalScreen, CommandPalette)):
            return
        widget = event.widget
        if isinstance(widget, NavRow):
            self._handle_nav_row_click(widget.node_index)
            event.stop()
            return
        if isinstance(widget, FilterPill):
            self.action_set_task_filter(widget.filter_id)
            self._set_focus_panel("content")
            event.stop()
            return
        if isinstance(widget, DocRow):
            self._select_audit(widget.audit_id)
            self._set_focus_panel("content")
            event.stop()
            return
        if isinstance(widget, AuditTaskRow):
            self._open_task_from_audit(widget.task_id)
            event.stop()
            return
        if widget.id == "docs-prev":
            if not widget.has_class("disabled"):
                self.action_docs_prev()
            event.stop()
            return
        if widget.id == "docs-next":
            if not widget.has_class("disabled"):
                self.action_docs_next()
            event.stop()
            return
        if widget.id == "nav-action":
            self._set_focus_panel("sidenav")
            self.action_new_workspace()
            event.stop()
            return
        if widget.id in {"sidenav", "nav-tree", "sidenav-brand"}:
            self._set_focus_panel("sidenav")
            return
        if widget.id in {"content-panel", "content-header", "content-body", "content-main", "task-meta", "footer-hints"}:
            self._set_focus_panel("content")

    def _handle_nav_row_click(self, node_index: int) -> None:
        nodes = self._nav_nodes()
        if node_index < 0 or node_index >= len(nodes):
            return
        self._nav_focus_index = node_index
        self._set_focus_panel("sidenav")
        self._render_nav()
        self.action_activate()

    def _select_audit(self, audit_id: str) -> None:
        if self._nav.selected_audit_id == audit_id:
            return
        linked_task_ids = self._linked_task_ids_for_audit(audit_id)
        selected_task_id = self._nav.selected_task_id
        if selected_task_id not in linked_task_ids:
            selected_task_id = linked_task_ids[0] if linked_task_ids else None
        self._nav = NavState(
            workspace_id=self._nav.workspace_id,
            project_id=self._nav.project_id,
            view=self._nav.view,
            selected_task_id=selected_task_id,
            selected_audit_id=audit_id,
            task_filter=self._nav.task_filter,
            expanded_workspaces=self._nav.expanded_workspaces,
            expanded_projects=self._nav.expanded_projects,
        )
        self._render_content()

    def _linked_task_ids_for_audit(self, audit_id: str) -> tuple[str, ...]:
        snapshot = self._current_snapshot
        if snapshot is None:
            return ()
        _workspace, project = resolve_nav_selection(snapshot, self._nav)
        if project is None:
            return ()
        return tuple(task.task_id for task in tasks_for_audit(project.all_tasks, audit_id))

    def _selected_linked_task_id(self) -> str | None:
        snapshot = self._current_snapshot
        if snapshot is None or not self._nav.selected_audit_id or not self._nav.selected_task_id:
            return None
        linked_ids = self._linked_task_ids_for_audit(self._nav.selected_audit_id)
        if self._nav.selected_task_id in linked_ids:
            return self._nav.selected_task_id
        return linked_ids[0] if linked_ids else None

    def _open_task_from_audit(self, task_id: str) -> None:
        if not self._nav.project_id:
            return
        self._nav = NavState(
            workspace_id=self._nav.workspace_id,
            project_id=self._nav.project_id,
            view="project_tasks",
            selected_task_id=task_id,
            selected_audit_id=self._nav.selected_audit_id,
            task_filter="all",
            expanded_workspaces=self._nav.expanded_workspaces,
            expanded_projects=self._nav.expanded_projects,
        )
        self._focus_panel = "content"
        self._drawer_open = True
        persist_tui_state(
            nav=self._nav,
            theme=self._theme_name,
            auto_refresh_seconds=self._auto_refresh_seconds,
        )
        self._render_all()

    def on_key(self, event: events.Key) -> None:
        if isinstance(self.screen, (ModalScreen, CommandPalette)):
            return
        if isinstance(self.focused, Input):
            return
        if event.key == "question_mark":
            self.action_command_palette()
            event.prevent_default()
            event.stop()
            return
        if self._nav.view == "project_tasks" and event.character and event.character in "1234":
            filter_index = int(event.character) - 1
            if 0 <= filter_index < len(TASK_FILTERS):
                self.action_set_task_filter(TASK_FILTERS[filter_index])
                event.prevent_default()
                event.stop()
            return
        if event.key == "shift+tab":
            self.action_focus_prev_panel()
            event.prevent_default()
            event.stop()
        elif event.key == "tab":
            self.action_focus_next_panel()
            event.prevent_default()
            event.stop()
        elif event.key == "enter" and self._nav.view == "project_tasks" and self._focus_panel == "content":
            self.action_open_linked_audit()
            event.prevent_default()
            event.stop()
        elif event.key == "enter" and self._nav.view == "project_docs" and self._focus_panel == "content":
            linked_task_id = self._selected_linked_task_id()
            if linked_task_id:
                self._open_task_from_audit(linked_task_id)
            event.prevent_default()
            event.stop()

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        yield from super().get_system_commands(screen)
        yield from iter_shell_commands(self, screen)

    def action_set_task_filter(self, filter_name: str) -> None:
        if self._nav.view != "project_tasks" or filter_name not in TASK_FILTERS:
            return
        if filter_name == self._nav.task_filter:
            return
        self._nav = NavState(
            workspace_id=self._nav.workspace_id,
            project_id=self._nav.project_id,
            view=self._nav.view,
            selected_task_id=None,
            selected_audit_id=self._nav.selected_audit_id,
            task_filter=filter_name,
            expanded_workspaces=self._nav.expanded_workspaces,
            expanded_projects=self._nav.expanded_projects,
        )
        self._drawer_open = False
        self._persist_state()
        self._render_all()

    def _schedule_startup_snapshot(self, delay_seconds: float, callback: Callable[[], None]) -> object:
        if self._startup_snapshot_scheduler is not None:
            return self._startup_snapshot_scheduler(delay_seconds, callback)
        return self.set_timer(delay_seconds, callback)

    def _load_initial_snapshot(self) -> None:
        self._reload_snapshot()
        self._start_auto_refresh()
        self._start_refresh_status_timer()
        self._startup_snapshot_ready = True
        self._dismiss_startup_splash_if_ready()

    def request_startup_splash_dismissal(self) -> None:
        self._startup_splash_dismiss_requested = True
        self._dismiss_startup_splash_if_ready()

    def _dismiss_startup_splash_if_ready(self) -> None:
        splash = self._startup_splash
        if not self._startup_splash_dismiss_requested or not self._startup_snapshot_ready or splash is None:
            return
        if self.screen == splash:
            self.pop_screen()
        self._startup_splash = None

    def action_cycle_theme(self) -> None:
        self._theme_name = next_theme_name(self._theme_name)
        self._apply_theme(self._theme_name)
        palette = set_active_theme(self._theme_name)
        self._show_status(f"Tema · {palette.label}", error=False)
        self._persist_state()

    def _apply_theme(self, theme_name: str) -> None:
        palette = set_active_theme(theme_name)
        self.dark = palette.dark
        # Layer theme CSS on top of Textual defaults and widget rules. Replacing the
        # entire stylesheet drops layout rules registered during compose.
        self.stylesheet.add_source(css_for_theme(theme_name), read_from=THEME_CSS_LOCATION)
        self.stylesheet.reparse()
        if self.is_mounted:
            try:
                self.stylesheet.update(self.screen)
                self.refresh_css()
                self._render_all()
            except ScreenStackError:
                return

    def _persist_state(self) -> None:
        persist_tui_state(
            nav=self._nav,
            theme=self._theme_name,
            auto_refresh_seconds=self._auto_refresh_seconds,
        )

    def action_refresh(self) -> None:
        self._reload_snapshot()

    def action_toggle_auto_refresh(self) -> None:
        try:
            current_index = AUTO_REFRESH_OPTIONS.index(self._auto_refresh_seconds)
            next_seconds = AUTO_REFRESH_OPTIONS[(current_index + 1) % len(AUTO_REFRESH_OPTIONS)]
        except ValueError:
            next_seconds = DEFAULT_AUTO_REFRESH_SECONDS
        self._auto_refresh_seconds = next_seconds
        self._persist_state()
        self._start_auto_refresh()
        self._render_refresh_status()
        label = f"{next_seconds}s" if next_seconds else "off"
        self._show_status(f"Auto-refresh · {label}", error=False)

    def action_new_task(self) -> None:
        if not self._nav.project_id:
            self._show_status("Selecciona un proyecto primero.", error=True)
            return
        self.push_screen(TaskModal("Nueva tarea", "Descripción de la tarea"), self._handle_task_created)

    def action_new_workspace(self) -> None:
        self.push_screen(NameModal("Nuevo workspace", "Nombre del workspace"), self._handle_workspace_created)

    def action_new_project(self) -> None:
        workspace_id = self._nav.workspace_id
        if not workspace_id and self._current_snapshot:
            workspace, _project = resolve_nav_selection(self._current_snapshot, self._nav)
            workspace_id = workspace.workspace_id if workspace else None
        if not workspace_id:
            self._show_status("Selecciona un workspace primero.", error=True)
            return
        self.push_screen(NameModal("Nuevo proyecto", "Nombre del proyecto"), self._handle_project_created)

    def action_open_docs(self) -> None:
        audit_id = self._linked_audit_id_for_selected_task()
        if self._nav.project_id:
            self._nav = NavState(
                workspace_id=self._nav.workspace_id,
                project_id=self._nav.project_id,
                view="project_docs",
                selected_task_id=self._nav.selected_task_id,
                selected_audit_id=audit_id or self._nav.selected_audit_id,
                expanded_workspaces=self._nav.expanded_workspaces,
                expanded_projects=self._nav.expanded_projects,
                task_filter=self._nav.task_filter,
            )
            self._drawer_open = False
            self._focus_panel = "content"
            self._render_all()

    def _linked_audit_id_for_selected_task(self) -> str | None:
        snapshot = self._current_snapshot
        if snapshot is None or not self._nav.project_id or not self._nav.selected_task_id:
            return None
        _workspace, project = resolve_nav_selection(snapshot, self._nav)
        if project is None:
            return None
        task = next((item for item in project.all_tasks if item.task_id == self._nav.selected_task_id), None)
        if task is None or not task.origin_audit_id:
            return None
        return task.origin_audit_id

    def action_open_linked_audit(self) -> None:
        if self._linked_audit_id_for_selected_task():
            self.action_open_docs()
            return
        self._show_status("La tarea seleccionada no tiene auditoría vinculada.", error=True)

    def action_open_tasks(self) -> None:
        if self._nav.project_id:
            self._nav = NavState(
                workspace_id=self._nav.workspace_id,
                project_id=self._nav.project_id,
                view="project_tasks",
                expanded_workspaces=self._nav.expanded_workspaces,
                expanded_projects=self._nav.expanded_projects,
                task_filter=self._nav.task_filter,
            )
            self._drawer_open = False
            self._focus_panel = "content"
            self._render_all()

    def action_open_home(self) -> None:
        if self._nav.project_id:
            self._nav = NavState(
                workspace_id=self._nav.workspace_id,
                project_id=self._nav.project_id,
                view="project_home",
                expanded_workspaces=self._nav.expanded_workspaces,
                expanded_projects=self._nav.expanded_projects,
                task_filter=self._nav.task_filter,
            )
            self._drawer_open = False
            self._focus_panel = "sidenav"
            self._render_all()

    def action_cycle_filter(self) -> None:
        if self._nav.view != "project_tasks":
            return
        current_index = TASK_FILTERS.index(self._nav.task_filter) if self._nav.task_filter in TASK_FILTERS else 0
        next_filter = TASK_FILTERS[(current_index + 1) % len(TASK_FILTERS)]
        self.action_set_task_filter(next_filter)

    def action_focus_next_panel(self) -> None:
        self._set_focus_panel("content" if self._focus_panel == "sidenav" else "sidenav")

    def action_focus_prev_panel(self) -> None:
        self._set_focus_panel("sidenav" if self._focus_panel == "content" else "content")

    def action_close_drawer(self) -> None:
        if not self._drawer_open:
            return
        self._drawer_open = False
        self.query_one("#task-drawer", Static).remove_class("visible")

    def action_nav_up(self) -> None:
        if self._focus_panel == "content":
            if self._nav.view == "project_docs":
                self._focus_content_selection(-1)
            return
        nodes = self._nav_nodes()
        if not nodes:
            return
        self._nav_focus_index = max(self._nav_focus_index - 1, 0)
        self._render_nav()

    def action_nav_down(self) -> None:
        if self._focus_panel == "content":
            if self._nav.view == "project_docs":
                self._focus_content_selection(1)
            return
        nodes = self._nav_nodes()
        if not nodes:
            return
        self._nav_focus_index = min(self._nav_focus_index + 1, len(nodes) - 1)
        self._render_nav()

    def action_collapse_nav(self) -> None:
        if self._focus_panel != "sidenav":
            return
        nodes = self._nav_nodes()
        if not nodes:
            return
        self._nav = toggle_expand_for_focused_node(nodes, self._nav_focus_index, self._nav)
        self._render_all()

    def action_expand_nav(self) -> None:
        if self._focus_panel != "sidenav":
            return
        nodes = self._nav_nodes()
        if not nodes:
            return
        node = nodes[self._nav_focus_index]
        if node.expandable:
            self._nav = toggle_expand_for_focused_node(nodes, self._nav_focus_index, self._nav)
            self._render_all()
            return
        self.action_activate()

    def action_activate(self) -> None:
        if self._focus_panel == "content":
            if self._nav.view == "project_tasks":
                self.action_open_linked_audit()
            elif self._nav.view == "project_docs":
                return
        nodes = self._nav_nodes()
        if not nodes:
            return
        node = nodes[self._nav_focus_index]
        if node.kind == "action":
            self.action_new_workspace()
            return
        self._nav = nav_state_for_node(node, self._nav)
        self._sync_nav_focus_to_active()
        if self._nav.view == "project_tasks":
            self._focus_panel = "content"
        elif self._nav.view == "project_docs":
            self._focus_panel = "content"
        elif self._nav.view == "project_home":
            self._focus_panel = "sidenav"
        persist_tui_state(
            nav=self._nav,
            theme=self._theme_name,
            auto_refresh_seconds=self._auto_refresh_seconds,
        )
        self._render_all()

    def action_claim_selected(self) -> None:
        self._run_task_action(lambda project_id, task_id: claim_task(
            repo_root=self._repo_root,
            node_home=self._node_home,
            project_id=project_id,
            task_id=task_id,
        ))

    def action_start_selected(self) -> None:
        self._run_task_action(lambda project_id, task_id: transition_task(
            repo_root=self._repo_root,
            node_home=self._node_home,
            project_id=project_id,
            task_id=task_id,
            requested_state="in_progress",
        ))

    def action_block_selected(self) -> None:
        self._run_task_action(lambda project_id, task_id: transition_task(
            repo_root=self._repo_root,
            node_home=self._node_home,
            project_id=project_id,
            task_id=task_id,
            requested_state="blocked",
        ))

    def action_done_selected(self) -> None:
        self._run_task_action(lambda project_id, task_id: transition_task(
            repo_root=self._repo_root,
            node_home=self._node_home,
            project_id=project_id,
            task_id=task_id,
            requested_state="done",
        ))

    def action_release_selected(self) -> None:
        self._run_task_action(lambda project_id, task_id: release_task(
            repo_root=self._repo_root,
            node_home=self._node_home,
            project_id=project_id,
            task_id=task_id,
        ))

    def _handle_workspace_created(self, name: str | None) -> None:
        if not name:
            return
        result = create_workspace(repo_root=self._repo_root, node_home=self._node_home, name=name)
        self._handle_action_result(result)
        if result.ok:
            self._reload_snapshot(select_latest_workspace=True)

    def _handle_project_created(self, name: str | None) -> None:
        if not name:
            return
        workspace_id = self._nav.workspace_id
        if not workspace_id and self._current_snapshot:
            workspace, _ = resolve_nav_selection(self._current_snapshot, self._nav)
            workspace_id = workspace.workspace_id if workspace else None
        if not workspace_id:
            self._show_status("Workspace no disponible.", error=True)
            return
        result = create_project(
            repo_root=self._repo_root,
            node_home=self._node_home,
            workspace_id=workspace_id,
            name=name,
        )
        self._handle_action_result(result)
        if result.ok:
            self._reload_snapshot()

    def _handle_task_created(self, description: str | None) -> None:
        if not description or not self._nav.project_id:
            return
        result = create_task(
            repo_root=self._repo_root,
            node_home=self._node_home,
            project_id=self._nav.project_id,
            description=description,
        )
        self._handle_action_result(result)
        if result.ok:
            self._reload_snapshot()
            if self._nav.view != "project_tasks":
                self.action_open_tasks()

    def _handle_action_result(self, result: ActionResult) -> None:
        self._show_status(result.message, error=not result.ok)

    def _run_task_action(self, callback: Callable[[str, str], ActionResult]) -> None:
        task_id, project_id = self._selected_task_context()
        if not task_id or not project_id:
            self._show_status("Selecciona una tarea primero.", error=True)
            return
        result = callback(project_id, task_id)
        self._handle_action_result(result)
        if result.ok:
            self._reload_snapshot()

    def _selected_task_context(self) -> tuple[str | None, str | None]:
        snapshot = self._current_snapshot
        if snapshot is None or not self._nav.project_id:
            return None, None
        _workspace, project = resolve_nav_selection(snapshot, self._nav)
        if project is None:
            return None, None
        if self._nav.view == "project_home":
            if project.ready_tasks:
                return project.ready_tasks[0].task_id, self._nav.project_id
            return None, self._nav.project_id
        tasks = filter_tasks(project.all_tasks, self._nav.task_filter)
        if not tasks:
            return None, self._nav.project_id
        if self._nav.selected_task_id:
            if any(task.task_id == self._nav.selected_task_id for task in tasks):
                return self._nav.selected_task_id, self._nav.project_id
        return tasks[0].task_id, self._nav.project_id

    def _focus_content_selection(self, step: int) -> bool:
        snapshot = self._current_snapshot
        if snapshot is None:
            return False
        if self._nav.view == "project_docs":
            _workspace, project = resolve_nav_selection(snapshot, self._nav)
            if project is None or not project.audits:
                return False
            selected_audit = resolve_selected_audit(project.audits, self._nav.selected_audit_id)
            if selected_audit is None:
                return False
            linked_tasks = tasks_for_audit(project.all_tasks, selected_audit.audit_id)
            if linked_tasks:
                current_index = next(
                    (index for index, task in enumerate(linked_tasks) if task.task_id == self._nav.selected_task_id),
                    0,
                )
                next_index = min(max(current_index + step, 0), len(linked_tasks) - 1)
                self._nav = NavState(
                    workspace_id=self._nav.workspace_id,
                    project_id=self._nav.project_id,
                    view=self._nav.view,
                    selected_task_id=linked_tasks[next_index].task_id,
                    selected_audit_id=selected_audit.audit_id,
                    task_filter=self._nav.task_filter,
                    expanded_workspaces=self._nav.expanded_workspaces,
                    expanded_projects=self._nav.expanded_projects,
                )
                self._render_docs_linked_tasks(project, selected_audit)
                return True
            return False
        return False

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id != "tasks-table":
            return
        task_id = str(event.row_key.value)
        if task_id == self._nav.selected_task_id:
            return
        self._nav = NavState(
            workspace_id=self._nav.workspace_id,
            project_id=self._nav.project_id,
            view=self._nav.view,
            selected_task_id=task_id,
            selected_audit_id=self._nav.selected_audit_id,
            task_filter=self._nav.task_filter,
            expanded_workspaces=self._nav.expanded_workspaces,
            expanded_projects=self._nav.expanded_projects,
        )
        self._update_task_drawer()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "tasks-table":
            return
        self._update_task_drawer()

    def _set_focus_panel(self, panel: FocusPanel) -> None:
        self._focus_panel = panel
        self._update_focus_chrome()
        if panel == "content" and self._nav.view == "project_tasks":
            table = self.query_one("#tasks-table", DataTable)
            if table.display:
                table.focus()
            return
        self.screen.focus()

    def _update_focus_chrome(self) -> None:
        sidenav = self.query_one("#sidenav")
        content_panel = self.query_one("#content-panel")
        sidenav.set_class(self._focus_panel == "sidenav", "panel-focused")
        content_panel.set_class(self._focus_panel == "content", "panel-focused")

    def _toggle_task_drawer(self) -> None:
        drawer = self.query_one("#task-drawer", Static)
        self._drawer_open = not self._drawer_open
        drawer.set_class(self._drawer_open, "visible")

    def _toggle_doc_drawer(self) -> None:
        return

    def _update_task_drawer(self) -> None:
        snapshot = self._current_snapshot
        if snapshot is None or self._nav.view != "project_tasks":
            return
        view_model = build_content_view_model(
            snapshot,
            self._nav,
            content_width=self._content_panel_width(),
        )
        drawer = self.query_one("#task-drawer", Static)
        if view_model.task_drawer:
            drawer.update(view_model.task_drawer)
            drawer.add_class("visible")
            self._drawer_open = True
        else:
            drawer.update("")
            self._drawer_open = False
            drawer.remove_class("visible")

    def _nav_nodes(self) -> list[NavNode]:
        if self._current_snapshot is None:
            return []
        return build_nav_tree(self._current_snapshot, self._nav)

    def _reload_snapshot(self, *, select_latest_workspace: bool = False, quiet: bool = False) -> None:
        previous_nav = self._nav
        self._sync_refreshing = True
        self._render_sync_status()
        try:
            snapshot = self._snapshot_loader(repo_root=self._repo_root, node_home=self._node_home, as_of=self._as_of)
        except Exception:
            if self._current_snapshot is not None:
                snapshot = self._current_snapshot
                if not quiet:
                    self._show_status("Refresh failed. Showing cached data.", error=True)
            else:
                snapshot = AppSnapshot(bootstrap_state="unavailable")
                if not quiet:
                    self._show_status("Refresh failed.", error=True)
        finally:
            self._sync_refreshing = False
        self._current_snapshot = snapshot
        self._refreshed_at = time.monotonic()
        self._nav = default_nav_state(snapshot, previous_nav)
        if select_latest_workspace and snapshot.workspaces:
            latest = snapshot.workspaces[-1]
            self._nav = NavState(
                workspace_id=latest.workspace_id,
                view="workspace_empty",
                expanded_workspaces=frozenset({latest.workspace_id}),
            )
        self._sync_nav_focus_to_active()
        self._persist_state()
        self._render_all()

    def _sync_nav_focus_to_active(self) -> None:
        nodes = self._nav_nodes()
        active_id = active_nav_node_id(self._nav)
        if active_id:
            for index, node in enumerate(nodes):
                if node.node_id == active_id:
                    self._nav_focus_index = index
                    return
        self._nav_focus_index = min(self._nav_focus_index, max(len(nodes) - 1, 0))

    def _render_all(self) -> None:
        self._render_nav()
        self._render_content()
        self._update_focus_chrome()

    def _render_nav(self) -> None:
        nodes = self._nav_nodes()
        nav_tree = self.query_one("#nav-tree", VerticalScroll)
        nav_tree.remove_children()
        active_id = active_nav_node_id(self._nav)
        for index, node in enumerate(nodes):
            classes = ["nav-row"]
            if node.kind == "workspace":
                classes.append("nav-row--workspace")
            elif node.kind == "project":
                classes.append("nav-row--project")
            elif node.kind == "page":
                classes.append("nav-row--page")
            if node.node_id == active_id:
                classes.append("nav-row--active")
            if index == self._nav_focus_index and self._focus_panel == "sidenav":
                classes.append("nav-row--focused")
            label = ("  " * node.depth) + node.label
            classes.append("clickable")
            nav_tree.mount(NavRow(label, node_index=index, classes=" ".join(classes)))

    def _render_content(self) -> None:
        snapshot = self._current_snapshot
        if snapshot is None:
            return
        content_width = self._content_panel_width() if self._nav.view == "project_tasks" else None
        view_model = build_content_view_model(snapshot, self._nav, content_width=content_width)
        self.query_one("#breadcrumb", Static).update(view_model.header.breadcrumb)
        self.query_one("#page-title", Static).update(view_model.header.title)
        self._render_sync_status()

        task_meta = self.query_one("#task-meta", Static)
        task_filters = self.query_one("#task-filters", Horizontal)
        tasks_table = self.query_one("#tasks-table", DataTable)
        tasks_empty = self.query_one("#tasks-empty", Static)
        content_main = self.query_one("#content-main", Static)
        content_body = self.query_one("#content-body", VerticalScroll)
        docs_shell = self.query_one("#docs-shell", Vertical)
        docs_list = self.query_one("#docs-list", Container)
        header_rule = self.query_one("#header-rule", Static)

        if view_model.tasks is not None:
            task_meta.update(f"· {view_model.tasks_meta}")
            task_meta.add_class("visible")
            header_rule.add_class("hidden")
            _workspace, project = resolve_nav_selection(snapshot, self._nav)
            all_tasks = project.all_tasks if project is not None else ()
            self._render_task_filters(task_filters, self._nav.task_filter, all_tasks)
            task_filters.remove_class("hidden")
            tasks_table.add_class("visible")
            content_body.add_class("hidden")
            docs_shell.remove_class("visible")
            docs_list.remove_children()
            content_main.update("")
            self._populate_tasks_table(tasks_table, view_model.tasks)
            if view_model.tasks:
                tasks_empty.update("")
                tasks_empty.remove_class("visible")
            else:
                tasks_empty.update("Sin tareas en este filtro. Prueba otro filtro (1–4) o pulsa f para rotar.")
                tasks_empty.add_class("visible")
        elif self._nav.view == "project_docs":
            task_meta.update("")
            task_meta.remove_class("visible")
            header_rule.add_class("hidden")
            task_filters.remove_children()
            task_filters.add_class("hidden")
            tasks_table.remove_class("visible")
            tasks_empty.remove_class("visible")
            content_body.add_class("hidden")
            content_main.update("")
            docs_shell.add_class("visible")
            self._render_docs_view()
        else:
            task_meta.update("")
            task_meta.remove_class("visible")
            header_rule.remove_class("hidden")
            task_filters.remove_children()
            task_filters.add_class("hidden")
            tasks_table.remove_class("visible")
            tasks_empty.remove_class("visible")
            content_body.remove_class("hidden")
            docs_shell.remove_class("visible")
            docs_list.remove_children()
            content_main.update(view_model.body)

        drawer = self.query_one("#task-drawer", Static)
        if self._nav.view == "project_tasks" and view_model.task_drawer:
            drawer.update(view_model.task_drawer)
            drawer.add_class("visible")
            self._drawer_open = True
        elif view_model.task_drawer and self._nav.view != "project_docs":
            drawer.update(view_model.task_drawer)
        else:
            drawer.update("")
            self._drawer_open = False
        if self._nav.view not in {"project_tasks", "project_docs"}:
            drawer.set_class(self._drawer_open, "visible")
        elif self._nav.view == "project_docs":
            drawer.remove_class("visible")
        self._update_footer(view_model.footer_hints)
        if self._focus_panel == "content" and view_model.tasks is not None and tasks_table.has_class("visible"):
            tasks_table.focus()

    def _render_task_filters(
        self,
        container: Horizontal,
        active_filter: str,
        all_tasks: tuple,
    ) -> None:
        counts = count_tasks_by_filter(all_tasks)
        pills = list(container.query(FilterPill))
        if not pills:
            for index, (filter_id, label, shortcut) in enumerate(TASK_FILTER_OPTIONS):
                pill_content = build_filter_pill_label(
                    filter_id,
                    label,
                    shortcut,
                    count=counts.get(filter_id, 0),
                    active=filter_id == active_filter,
                )
                classes = ["filter-pill", "clickable"]
                if filter_id == active_filter:
                    classes.append("filter-pill--active")
                container.mount(
                    FilterPill(
                        pill_content,
                        filter_id=filter_id,
                        classes=" ".join(classes),
                        id=f"filter-{filter_id}",
                    )
                )
                if index < len(TASK_FILTER_OPTIONS) - 1:
                    container.mount(Static("  ", classes="filter-spacer"))
            return
        for pill in pills:
            pill.set_class(pill.filter_id == active_filter, "filter-pill--active")
            option = next((item for item in TASK_FILTER_OPTIONS if item[0] == pill.filter_id), None)
            if option is None:
                continue
            filter_id, label, shortcut = option
            pill.update(
                build_filter_pill_label(
                    filter_id,
                    label,
                    shortcut,
                    count=counts.get(filter_id, 0),
                    active=pill.filter_id == active_filter,
                )
            )

    def _render_docs_view(self) -> None:
        snapshot = self._current_snapshot
        if snapshot is None:
            return
        _workspace, project = resolve_nav_selection(snapshot, self._nav)
        docs_list = self.query_one("#docs-list", Container)
        index_label = self.query_one("#docs-index-label", Static)
        if project is None or not project.audits:
            index_label.update("Sin documentación")
            docs_list.remove_children()
            docs_list.mount(Static("Sin documentación todavía.", classes="empty-docs"))
            self._render_docs_detail(None, index=0, total=0)
            self._render_docs_linked_tasks(project, None)
            return

        selected_audit = resolve_selected_audit(project.audits, self._nav.selected_audit_id)
        if selected_audit is None:
            return
        if self._nav.selected_audit_id != selected_audit.audit_id:
            self._nav = NavState(
                workspace_id=self._nav.workspace_id,
                project_id=self._nav.project_id,
                view=self._nav.view,
                selected_task_id=self._nav.selected_task_id,
                selected_audit_id=selected_audit.audit_id,
                task_filter=self._nav.task_filter,
                expanded_workspaces=self._nav.expanded_workspaces,
                expanded_projects=self._nav.expanded_projects,
            )

        selected_index = next(
            (index for index, audit in enumerate(project.audits) if audit.audit_id == selected_audit.audit_id),
            0,
        )
        index_label.update(f"Índice · {selected_index + 1}/{len(project.audits)}")
        self._render_docs_list(docs_list, project.audits, selected_audit.audit_id)
        self._render_docs_detail(selected_audit, index=selected_index, total=len(project.audits))
        self._render_docs_linked_tasks(project, selected_audit)
        if project.local_documents:
            docs_list.mount(Static("Archivos locales", classes="doc-section-label"))
            for doc in project.local_documents:
                docs_list.mount(Static(f"  {doc.storage_path}", classes="doc-file"))

    def _render_docs_detail(self, audit, *, index: int, total: int) -> None:
        title_widget = self.query_one("#docs-detail-title", Static)
        content_widget = self.query_one("#docs-detail-content", Static)
        prev_button = self.query_one("#docs-prev", Static)
        next_button = self.query_one("#docs-next", Static)
        if audit is None:
            title_widget.update("Sin documentación seleccionada")
            content_widget.update("")
            prev_button.add_class("disabled")
            next_button.add_class("disabled")
            self.call_after_refresh(self._update_docs_detail_layout)
            return

        title_line = Text()
        title_line.append(audit.title or "Untitled", style="bold bright_white")
        title_line.append("  ")
        title_line.append_text(render_pill(labelize(audit.state), style_for_audit_state(audit.state)))
        title_line.append(f"  ·  {index + 1}/{total}", style="dim")
        title_widget.update(title_line)
        content_widget.update(build_docs_detail_content(audit))
        prev_button.set_class(index <= 0, "disabled")
        next_button.set_class(index >= total - 1, "disabled")

        def relayout() -> None:
            self._update_docs_detail_layout(audit=audit)
            try:
                self.query_one("#docs-detail-scroll", VerticalScroll).scroll_home(animate=False)
            except Exception:
                pass

        self.call_after_refresh(relayout)

    def _render_docs_list(self, container: Container, audits: tuple, selected_id: str) -> None:
        container.remove_children()
        for audit in audits:
            title = (audit.title or "Untitled")[:50].ljust(52)
            row_text = Text(title)
            row_text.append_text(render_pill(labelize(audit.state), style_for_audit_state(audit.state)))
            classes = ["doc-row", "clickable"]
            if audit.audit_id == selected_id:
                classes.append("doc-row--selected")
            container.mount(DocRow(row_text, audit_id=audit.audit_id, classes=" ".join(classes)))

    def _render_docs_linked_tasks(self, project: ProjectSnapshot | None, audit: AuditPreview | None) -> None:
        label = self.query_one("#docs-tasks-label", Static)
        container = self.query_one("#docs-tasks-list", Container)
        if project is None or audit is None:
            label.update("Tareas vinculadas")
            container.remove_children()
            return

        linked_tasks = tasks_for_audit(project.all_tasks, audit.audit_id)
        if not linked_tasks:
            label.update("Tareas vinculadas · ninguna")
            container.remove_children()
            return

        label.update(f"Tareas vinculadas · {len(linked_tasks)}")
        container.remove_children()
        selected_id = self._nav.selected_task_id
        linked_ids = {task.task_id for task in linked_tasks}
        if selected_id not in linked_ids:
            selected_id = linked_tasks[0].task_id
            if self._nav.selected_task_id != selected_id:
                self._nav = NavState(
                    workspace_id=self._nav.workspace_id,
                    project_id=self._nav.project_id,
                    view=self._nav.view,
                    selected_task_id=selected_id,
                    selected_audit_id=self._nav.selected_audit_id,
                    task_filter=self._nav.task_filter,
                    expanded_workspaces=self._nav.expanded_workspaces,
                    expanded_projects=self._nav.expanded_projects,
                )

        for task in linked_tasks:
            row_text = build_audit_task_row_label(task)
            classes = ["audit-task-row", "clickable"]
            if task.task_id == selected_id:
                classes.append("audit-task-row--selected")
            container.mount(AuditTaskRow(row_text, task_id=task.task_id, classes=" ".join(classes)))

    def _populate_tasks_table(self, table: DataTable, tasks: tuple) -> None:
        snapshot = self._current_snapshot
        audits: tuple = ()
        if snapshot is not None:
            _workspace, project = resolve_nav_selection(snapshot, self._nav)
            if project is not None:
                audits = project.audits
        sorted_tasks = sort_tasks_for_view(
            tasks,
            sort_column=self._task_sort_column,
            reverse=self._task_sort_reverse,
        )
        available_width = self._tasks_table_width(table)
        column_widths = compute_task_column_widths(available_width)
        selected_task_id = self._nav.selected_task_id
        table.clear(columns=True)
        for column_key, label, _hint in TASK_TABLE_COLUMNS:
            table.add_column(
                build_task_column_label(
                    column_key,
                    label,
                    sort_column=self._task_sort_column,
                    sort_reverse=self._task_sort_reverse,
                ),
                key=column_key,
                width=column_widths[column_key],
            )
        selected_index = 0
        for index, task in enumerate(sorted_tasks):
            row = build_task_table_row(
                task,
                audits=audits,
                column_widths=column_widths,
            )
            table.add_row(*row, key=task.task_id)
            if task.task_id == selected_task_id:
                selected_index = index
        if sorted_tasks:
            table.move_cursor(row=selected_index)
            if selected_task_id is None:
                self._nav = NavState(
                    workspace_id=self._nav.workspace_id,
                    project_id=self._nav.project_id,
                    view=self._nav.view,
                    selected_task_id=sorted_tasks[selected_index].task_id,
                    selected_audit_id=self._nav.selected_audit_id,
                    task_filter=self._nav.task_filter,
                    expanded_workspaces=self._nav.expanded_workspaces,
                    expanded_projects=self._nav.expanded_projects,
                )
            self._update_task_drawer()
        else:
            self._drawer_open = False
            drawer = self.query_one("#task-drawer", Static)
            drawer.update("")
            drawer.remove_class("visible")

    def _render_sync_status(self) -> None:
        if not self.is_mounted:
            return
        try:
            status_widget = self.query_one("#refresh-status", Static)
        except Exception:
            return
        degraded = False
        pending_routes = 0
        snapshot = self._current_snapshot
        if snapshot is not None:
            _workspace, project = resolve_nav_selection(snapshot, self._nav)
            if project is not None:
                degraded = project.sync_degraded
                pending_routes = project.sync_pending_routes
            else:
                degraded = snapshot.sync_degraded
                pending_routes = snapshot.sync_pending_routes
        seconds_since_refresh = max(0, int(time.monotonic() - self._refreshed_at))
        status = build_sync_status_light(
            degraded=degraded,
            pending_routes=pending_routes,
            seconds_since_refresh=seconds_since_refresh,
            auto_refresh_seconds=self._auto_refresh_seconds,
            refreshing=self._sync_refreshing,
        )
        status_widget.update(status)

    def _render_refresh_status(self) -> None:
        self._render_sync_status()

    def _update_footer(self, _hints: str) -> None:
        palette = active_theme()
        hints = build_footer_hints(
            self._nav,
            focus_panel=self._focus_panel,
            drawer_open=self._drawer_open,
            theme_label=palette.label,
        )
        self.query_one("#footer-hints", Static).update(hints)

    def _show_status(self, message: str, *, error: bool = False) -> None:
        bar = self.query_one("#status-bar", Static)
        bar.update(message)
        bar.remove_class("success")
        bar.remove_class("error")
        bar.add_class("error" if error else "success")

        def _clear() -> None:
            bar.update("")
            bar.remove_class("success")
            bar.remove_class("error")

        self.set_timer(2.0, _clear)


class StartupSplash(Screen[None]):
    BINDINGS = [
        Binding("q", "dismiss", show=False),
        Binding("r", "dismiss", show=False),
    ]

    def __init__(
        self,
        *,
        repo_root: str,
        splash_art_loader=load_splash_art,
        duration_seconds: float = SPLASH_DURATION_SECONDS,
        dismiss_scheduler: TimerScheduler | None = None,
    ) -> None:
        super().__init__(id="startup-splash")
        self._repo_root = repo_root
        self._splash_art_loader = splash_art_loader
        self._duration_seconds = duration_seconds
        self._dismiss_scheduler = dismiss_scheduler
        self._dismissed = False

    def compose(self) -> ComposeResult:
        yield Container(
            Static(id="splash-content"),
            Static("Press any key to continue", id="splash-hint"),
            id="splash-shell",
        )

    def on_mount(self) -> None:
        self._render_content()
        self._schedule_dismissal(self._duration_seconds, self._dismiss)

    def _schedule_dismissal(self, delay_seconds: float, callback: Callable[[], None]) -> object:
        if self._dismiss_scheduler is not None:
            return self._dismiss_scheduler(delay_seconds, callback)
        return self.set_timer(delay_seconds, callback)

    def on_resize(self, _event) -> None:
        self._render_content()

    def on_key(self, event) -> None:
        event.stop()
        self._dismiss()

    def action_dismiss(self) -> None:
        self._dismiss()

    def _render_content(self) -> None:
        splash = build_splash_content(
            available_width=self.size.width,
            available_height=self.size.height,
            ascii_art=self._splash_art_loader(repo_root=self._repo_root),
        )
        content = self.query_one("#splash-content", Static)
        content.set_classes(splash.mode)
        content.update("\n".join(splash.lines))

    def _dismiss(self) -> None:
        if self._dismissed or self.app.screen != self:
            return
        self._dismissed = True
        request_dismissal = getattr(self.app, "request_startup_splash_dismissal", None)
        if request_dismissal is None:
            self.app.pop_screen()
            return
        request_dismissal()


HomeApp = ShellApp
