from __future__ import annotations

import textwrap
from dataclasses import dataclass, replace
from typing import Callable, Literal

from runtime.tui.data import (
    AppSnapshot,
    AuditPreview,
    HomeSnapshot,
    NavState,
    ProjectSnapshot,
    TaskPreview,
    WorkspaceSnapshot,
    default_nav_state,
    count_tasks_by_filter,
    filter_tasks,
    resolve_as_of,
    resolve_nav_selection,
    snapshot_with_notice,
)
from runtime.tui.theme import (
    append_pill,
    labelize,
    render_pill,
    style_for_audit_state,
    style_for_effort,
    style_for_priority,
    style_for_risk,
    style_for_cta,
    style_for_selected_row,
    style_for_task_state,
    style_for_task_type,
)
from rich.console import Group
from rich.markdown import Markdown
from rich.text import Text

FocusPanel = Literal["sidenav", "content"]

TASK_FILTER_OPTIONS = (
    ("all", "Todas", "1"),
    ("active", "Activas", "2"),
    ("blocked", "Bloqueadas", "3"),
    ("done", "Hechas", "4"),
)

TASK_TABLE_COLUMNS = (
    ("description", "Descripción", "Qué hay que hacer"),
    ("state", "Estado", "Fase del ciclo de vida"),
    ("priority", "Prioridad", "Urgencia relativa"),
    ("task_type", "Tipo", "Naturaleza del trabajo"),
    ("effort", "Esfuerzo", "Coste estimado"),
    ("risk", "Riesgo", "Impacto si falla"),
    ("audit", "Auditoría", "Spec de origen"),
)

TASK_SORTABLE_COLUMNS = frozenset(
    {"description", "state", "priority", "task_type", "effort", "risk"}
)

TASK_STATE_ORDER = ("proposed", "ready", "claimed", "in_progress", "blocked", "done", "cancelled")
TASK_PRIORITY_ORDER = ("low", "medium", "high", "critical")
TASK_EFFORT_ORDER = ("low", "medium", "high")
TASK_RISK_ORDER = ("low", "medium", "high")
TASK_TYPE_ORDER = ("fix", "feature", "audit_followup", "doc", "refactor", "ops")

TASK_COLUMN_WIDTHS = {
    "state": 12,
    "priority": 12,
    "task_type": 10,
    "effort": 10,
    "risk": 9,
    "audit": 18,
}
DEFAULT_TASK_TABLE_WIDTH = 120
MIN_TASK_TABLE_WIDTH = 64
TASK_TABLE_GUTTER = 2


@dataclass(frozen=True)
class HomeSection:
    title: str
    lines: tuple[str, ...]
    tone: str = "body"


@dataclass(frozen=True)
class DetailField:
    label: str
    value: str


@dataclass(frozen=True)
class TaskDetailPanel:
    eyebrow: str
    title: str
    summary: tuple[str, ...]
    metadata: tuple[DetailField, ...]
    tone: str = "body"


@dataclass(frozen=True)
class BrowserSelection:
    workspace: WorkspaceSnapshot | None
    project: ProjectSnapshot | None
    task: TaskPreview | None


@dataclass(frozen=True)
class PageHeader:
    breadcrumb: str
    title: str
    subtitle: str = ""


@dataclass(frozen=True)
class ContentViewModel:
    header: PageHeader
    body: Text | str
    footer_hints: str
    task_drawer: Text | str | None = None
    tasks_meta: str = ""
    tasks: tuple[TaskPreview, ...] | None = None


@dataclass(frozen=True)
class HomeViewModel:
    title: str
    subtitle: str
    sections: tuple[HomeSection, ...]
    detail_panel: TaskDetailPanel
    updated_at: str


def build_page_header(snapshot: AppSnapshot, nav: NavState) -> PageHeader:
    workspace, project = resolve_nav_selection(snapshot, nav)
    if nav.view == "workspace_empty" and not snapshot.workspaces:
        return PageHeader(breadcrumb="", title="CapiForge", subtitle="Create your first workspace")
    if nav.view == "workspace_empty" and workspace and not project:
        return PageHeader(
            breadcrumb=workspace.name,
            title=workspace.name,
            subtitle="Add a project to this workspace",
        )
    if project and workspace:
        view_label = {
            "project_home": "Inicio",
            "project_tasks": "Tareas",
            "project_docs": "Documentación",
        }.get(nav.view, "Inicio")
        return PageHeader(
            breadcrumb=f"{workspace.name} / {project.name} / {view_label}",
            title=project.name if nav.view == "project_home" else view_label,
            subtitle=project.sync_summary or "",
        )
    return PageHeader(breadcrumb="", title=snapshot.title, subtitle=snapshot.subtitle)


def build_home_content(snapshot: AppSnapshot, nav: NavState) -> ContentViewModel:
    workspace, project = resolve_nav_selection(snapshot, nav)
    header = build_page_header(snapshot, nav)
    if not snapshot.workspaces:
        body = Text("Crea tu primer workspace", style="dim")
        body.append("\n")
        body.append("Presiona n para crear", style=style_for_cta())
        return ContentViewModel(header=header, body=body, footer_hints="n Nuevo workspace  ·  q Salir  ·  r Refrescar")
    if workspace and not project:
        body = Text(f"Workspace · {workspace.name}", style="bright_white")
        body.append("\n")
        body.append("Presiona p para agregar un proyecto", style=style_for_cta())
        return ContentViewModel(header=header, body=body, footer_hints="p Nuevo proyecto  ·  n Workspace  ·  q Salir  ·  r Refrescar")
    if project is None:
        return ContentViewModel(header=header, body="Sin proyecto visible.", footer_hints="q Salir  ·  r Refrescar")

    text = Text()
    text.append("Resumen", style="dim")
    text.append("\n")
    owner = project.owner_node_id or "unknown"
    sync = project.sync_summary or "Local read-only shell"
    text.append(f"{owner} · {sync}", style="")
    if snapshot.local_node_id:
        text.append(f" · nodo {snapshot.local_node_id}", style="dim")
    text.append("\n\n")
    text.append("Siguiente lista", style="dim")
    text.append("\n")
    if project.ready_tasks:
        next_ready = project.ready_tasks[0]
        ready_line = Text(f"  {next_ready.description}  ")
        ready_line.append_text(render_pill(labelize(next_ready.state), style_for_task_state(next_ready.state)))
        text.append_text(ready_line)
        text.append("\n")
        text.append("c para claim  ·  t para ver todas", style=style_for_cta())
    else:
        text.append("Sin tareas ready.", style="dim")
        text.append("\n")
        text.append("a para crear tarea", style=style_for_cta())
    text.append("\n\n")
    text.append("Cola", style="dim")
    text.append("\n")
    queue_line = Text()
    for key in ("ready", "in_progress", "claimed", "blocked", "done"):
        count = _queue_count(project, key)
        if count:
            append_pill(queue_line, f"{labelize(key)} {count}", style_for_task_state(key if key != "in_progress" else "in_progress"))
    text.append_text(queue_line if len(queue_line) > 0 else Text("Sin tareas en cola.", style="dim"))
    text.append("\n\n")
    text.append("Recientes", style="dim")
    text.append("\n")
    recent = project.all_tasks[:3] if project.all_tasks else project.ready_tasks[:3]
    if not recent:
        text.append("Sin tareas recientes.", style="dim")
    else:
        for index, task in enumerate(recent):
            if index:
                text.append("\n")
            line = Text(f"  {task.description}  ")
            line.append_text(render_pill(labelize(task.state), style_for_task_state(task.state)))
            text.append_text(line)
    text.append("\n\n")
    text.append("Documentación", style="dim")
    text.append("\n")
    audit_count = len(project.audits)
    text.append(f"{audit_count} audit{'s' if audit_count != 1 else ''} · o para abrir Documentación", style="")
    return ContentViewModel(
        header=header,
        body=text,
        footer_hints="o Documentación  ·  t Tareas  ·  q Salir  ·  r Refrescar",
    )


def _queue_count(project: ProjectSnapshot, key: str) -> int:
    if key in project.queue_counts:
        return project.queue_counts[key]
    if key == "in_progress":
        return sum(1 for task in project.all_tasks if task.state == "in_progress")
    if key == "claimed":
        return sum(1 for task in project.all_tasks if task.state == "claimed")
    return 0


def _resolve_selected_task(tasks: tuple[TaskPreview, ...], selected_task_id: str | None) -> TaskPreview | None:
    if not tasks:
        return None
    if selected_task_id:
        for task in tasks:
            if task.task_id == selected_task_id:
                return task
    return tasks[0]


def build_filter_pill_label(filter_id: str, label: str, shortcut: str, *, count: int, active: bool) -> Text:
    pill_label = f"[{shortcut}] {label} ({count})"
    style = style_for_selected_row() if active else "dim"
    return render_pill(pill_label, style)


def build_task_filters_bar(task_filter: str, *, tasks: tuple[TaskPreview, ...] = ()) -> Text:
    counts = count_tasks_by_filter(tasks)
    text = Text()
    for index, (filter_id, label, shortcut) in enumerate(TASK_FILTER_OPTIONS):
        if index:
            text.append("  ")
        text.append_text(
            build_filter_pill_label(
                filter_id,
                label,
                shortcut,
                count=counts.get(filter_id, 0),
                active=filter_id == task_filter,
            )
        )
    return text


SyncLightState = Literal["ok", "degraded", "pending", "stale", "refreshing"]

SYNC_LIGHT_STYLES: dict[SyncLightState, tuple[str, str]] = {
    "ok": ("●", "bright_green"),
    "degraded": ("●", "bright_yellow"),
    "pending": ("●", "bright_yellow"),
    "stale": ("●", "bright_red"),
    "refreshing": ("◐", "bright_cyan"),
}

SYNC_LIGHT_LABELS: dict[SyncLightState, str] = {
    "ok": "Sync OK",
    "degraded": "Local-only",
    "pending": "Rutas pendientes",
    "stale": "Datos desactualizados",
    "refreshing": "Actualizando",
}


def resolve_sync_light_state(
    *,
    degraded: bool,
    pending_routes: int,
    seconds_since_refresh: int,
    auto_refresh_seconds: int,
    refreshing: bool,
) -> SyncLightState:
    if refreshing:
        return "refreshing"
    if pending_routes > 0:
        return "pending"
    if degraded:
        return "degraded"
    if auto_refresh_seconds > 0 and seconds_since_refresh > auto_refresh_seconds:
        return "stale"
    return "ok"


def build_sync_status_light(
    *,
    degraded: bool = False,
    pending_routes: int = 0,
    seconds_since_refresh: int = 0,
    auto_refresh_seconds: int = 0,
    refreshing: bool = False,
) -> Text:
    state = resolve_sync_light_state(
        degraded=degraded,
        pending_routes=pending_routes,
        seconds_since_refresh=seconds_since_refresh,
        auto_refresh_seconds=auto_refresh_seconds,
        refreshing=refreshing,
    )
    glyph, color = SYNC_LIGHT_STYLES[state]
    text = Text()
    text.append(glyph, style=color)
    text.append(f" {SYNC_LIGHT_LABELS[state]}", style="dim")
    if auto_refresh_seconds:
        text.append(f" · auto {auto_refresh_seconds}s", style="dim")
    elif state != "refreshing":
        text.append(" · auto off", style="dim")
    return text


def build_refresh_status(*, seconds_since_refresh: int, auto_refresh_seconds: int) -> str:
    auto_label = f"auto {auto_refresh_seconds}s" if auto_refresh_seconds else "auto off"
    return f"actualizado hace {seconds_since_refresh}s · {auto_label}"


def build_footer_hints(
    nav: NavState,
    *,
    focus_panel: FocusPanel,
    drawer_open: bool,
    theme_label: str,
) -> str:
    parts: list[str] = ["Ctrl+P Comandos", "Tab Panel", "Click Seleccionar"]

    if focus_panel == "sidenav":
        parts.extend(["↑↓ Navegar", "Enter Abrir", "←→ Expandir"])
    elif nav.view == "project_tasks":
        parts.extend(["Click header ordenar", "a Nueva", "↑↓ Filas", "Enter/o Auditoría", "1-4 Filtro", "c Claim", "s Start", "b Block", "d Done", "x Release"])
    elif nav.view == "project_docs":
        parts.extend(["↑↓ Cambiar", "[ ] Prev/Next", "Click tarea → Tareas", "Enter Abrir tarea"])
    elif nav.view == "project_home" and nav.project_id:
        parts.extend(["a Nueva tarea", "c Claim ready", "t Tareas", "o Docs"])
    else:
        parts.extend(["n Workspace", "p Proyecto"])

    if drawer_open:
        parts.append("Esc Cerrar")

    parts.extend(["g Auto-refresh", "r Refresh", "q Quit", f"Tema {theme_label} (T)"])
    return "  ·  ".join(parts)


def _truncate_label(value: str, *, max_len: int) -> str:
    if len(value) <= max_len:
        return value
    return f"{value[: max_len - 1]}…"


def _ordered_index(values: tuple[str, ...], key: str) -> int:
    try:
        return values.index(key)
    except ValueError:
        return len(values)


def compute_task_column_widths(available_width: int) -> dict[str, int]:
    width = max(available_width - TASK_TABLE_GUTTER, MIN_TASK_TABLE_WIDTH)
    fixed_sum = sum(TASK_COLUMN_WIDTHS.values())
    min_description = 12
    if width >= fixed_sum + min_description:
        return {"description": width - fixed_sum, **TASK_COLUMN_WIDTHS}

    remaining = width - min_description
    scale = remaining / fixed_sum
    shrunk = {
        key: max(6, int(column_width * scale))
        for key, column_width in TASK_COLUMN_WIDTHS.items()
    }
    fixed_total = sum(shrunk.values())
    if fixed_total > remaining:
        shrunk["audit"] = max(6, shrunk["audit"] - (fixed_total - remaining))
    return {"description": width - sum(shrunk.values()), **shrunk}


def _wrap_text_lines(text: str, *, width: int) -> tuple[str, ...]:
    wrap_width = max(16, width)
    wrapped = textwrap.wrap(
        text or "",
        width=wrap_width,
        break_long_words=True,
        break_on_hyphens=False,
    )
    return tuple(wrapped) if wrapped else ("",)


def build_task_column_label(
    column_key: str,
    label: str,
    *,
    sort_column: str | None,
    sort_reverse: bool,
) -> str:
    if column_key != sort_column:
        return label
    return f"{label} {'↓' if sort_reverse else '↑'}"


def sort_tasks_for_view(
    tasks: tuple[TaskPreview, ...],
    *,
    sort_column: str,
    reverse: bool = False,
) -> tuple[TaskPreview, ...]:
    if sort_column not in TASK_SORTABLE_COLUMNS:
        return tasks

    def sort_key(task: TaskPreview):
        if sort_column == "description":
            return (task.description or "").casefold()
        if sort_column == "state":
            return _ordered_index(TASK_STATE_ORDER, task.state)
        if sort_column == "priority":
            return _ordered_index(TASK_PRIORITY_ORDER, task.priority)
        if sort_column == "task_type":
            return _ordered_index(TASK_TYPE_ORDER, task.task_type)
        if sort_column == "effort":
            return _ordered_index(TASK_EFFORT_ORDER, task.effort)
        if sort_column == "risk":
            return _ordered_index(TASK_RISK_ORDER, task.risk)
        return ""

    return tuple(sorted(tasks, key=sort_key, reverse=reverse))


def _audit_lookup(audits: tuple[AuditPreview, ...], audit_id: str) -> AuditPreview | None:
    if not audit_id:
        return None
    for audit in audits:
        if audit.audit_id == audit_id:
            return audit
    return AuditPreview(audit_id=audit_id, title=audit_id, state="unknown")


def _pill_cell(label: str, style: str, *, column_width: int) -> Text:
    return render_pill(_truncate_label(label, max_len=max(1, column_width - 2)), style)


def build_task_table_row(
    task: TaskPreview,
    *,
    audits: tuple[AuditPreview, ...] = (),
    column_widths: dict[str, int] | None = None,
    description_width: int | None = None,
) -> tuple[str | Text, ...]:
    widths = column_widths or compute_task_column_widths(DEFAULT_TASK_TABLE_WIDTH)
    if description_width is not None:
        widths = {**widths, "description": description_width}
    max_description = widths["description"]
    description = _truncate_label(task.description or "Untitled", max_len=max(8, max_description - 1))
    state_cell = _pill_cell(labelize(task.state), style_for_task_state(task.state), column_width=widths["state"])
    priority_cell = _pill_cell(labelize(task.priority), style_for_priority(task.priority), column_width=widths["priority"])
    type_cell = _pill_cell(labelize(task.task_type), style_for_task_type(task.task_type), column_width=widths["task_type"])
    effort_cell = _pill_cell(labelize(task.effort), style_for_effort(task.effort), column_width=widths["effort"])
    risk_cell = _pill_cell(labelize(task.risk), style_for_risk(task.risk), column_width=widths["risk"])
    audit = _audit_lookup(audits, task.origin_audit_id)
    audit_label = _truncate_label(
        (audit.title if audit else task.origin_audit_id) or "—",
        max_len=max(1, widths["audit"] - 2),
    )
    audit_cell = Text(audit_label, style=style_for_cta() if audit else "dim")
    return description, state_cell, priority_cell, type_cell, effort_cell, risk_cell, audit_cell


def build_task_drawer(
    task: TaskPreview | None,
    *,
    audits: tuple[AuditPreview, ...] = (),
    content_width: int | None = None,
) -> Text | None:
    if task is None:
        return None
    text = Text()
    wrap_width = max(32, (content_width or DEFAULT_TASK_TABLE_WIDTH) - 4)
    for line in _wrap_text_lines(task.description or "Untitled", width=wrap_width):
        text.append(line)
        text.append("\n")
    text.append("\n")
    text.append(task.task_id, style="dim")
    if task.lifecycle_key:
        text.append(f"  ·  {task.lifecycle_key}", style="dim")
    if task.state == "blocked":
        text.append("\n")
        if task.blocked_reason:
            text.append(f"Bloqueo · {task.blocked_reason}", style="bright_red")
        if task.blocked_next_step:
            text.append(f"  →  {task.blocked_next_step}", style=style_for_cta())

    audit = _audit_lookup(audits, task.origin_audit_id)
    text.append("\n")
    text.append("Auditoría · ", style="dim")
    if audit:
        text.append(audit.title or audit.audit_id, style="bold")
        text.append("  ")
        text.append_text(render_pill(labelize(audit.state), style_for_audit_state(audit.state)))
        text.append(f"\n{audit.audit_id}", style="dim")
    elif task.origin_audit_id:
        text.append(task.origin_audit_id, style="dim")
    else:
        text.append("sin vincular", style="dim")
    text.append("\n")
    text.append("Enter / o → Documentación", style=style_for_cta())
    return text


def build_tasks_content(
    snapshot: AppSnapshot,
    nav: NavState,
    *,
    content_width: int | None = None,
) -> ContentViewModel:
    workspace, project = resolve_nav_selection(snapshot, nav)
    header = build_page_header(snapshot, nav)
    if project is None:
        return ContentViewModel(header=header, body="Selecciona un proyecto.", footer_hints="q Salir  ·  r Refrescar")

    tasks = tuple(filter_tasks(project.all_tasks, nav.task_filter))
    counts = count_tasks_by_filter(project.all_tasks)
    if tasks:
        tasks_meta = f"{len(tasks)} tareas"
    else:
        filter_label = next((label for fid, label, _ in TASK_FILTER_OPTIONS if fid == nav.task_filter), nav.task_filter)
        tasks_meta = f"0 tareas · sin resultados en «{filter_label}» ({counts.get(nav.task_filter, 0)})"
    selected_task = _resolve_selected_task(tasks, nav.selected_task_id)
    drawer = (
        build_task_drawer(selected_task, audits=project.audits, content_width=content_width)
        if selected_task
        else None
    )
    body = "Sin tareas en este filtro." if not tasks else ""
    return ContentViewModel(
        header=header,
        body=body,
        footer_hints="",
        task_drawer=drawer,
        tasks_meta=tasks_meta,
        tasks=tasks,
    )


def resolve_selected_audit(
    audits: tuple[AuditPreview, ...],
    selected_audit_id: str | None,
) -> AuditPreview | None:
    if not audits:
        return None
    if selected_audit_id:
        for audit in audits:
            if audit.audit_id == selected_audit_id:
                return audit
    return audits[0]


def tasks_for_audit(tasks: tuple[TaskPreview, ...], audit_id: str) -> tuple[TaskPreview, ...]:
    if not audit_id:
        return ()
    return tuple(task for task in tasks if task.origin_audit_id == audit_id)


def build_audit_task_row_label(task: TaskPreview, *, max_description: int = 56) -> Text:
    description = _truncate_label(task.description or "Untitled", max_len=max_description)
    row = Text(description)
    row.append("  ")
    row.append_text(render_pill(labelize(task.state), style_for_task_state(task.state)))
    row.append("  ")
    row.append_text(render_pill(labelize(task.priority), style_for_priority(task.priority)))
    return row


def build_docs_detail_content(audit: AuditPreview) -> Group:
    parts: list[Text | Markdown] = [Text(audit.audit_id, style="dim"), Text("")]
    content = (audit.content or "").strip()
    if content:
        parts.append(Markdown(content))
    else:
        parts.append(Text("(sin contenido)", style="dim"))
    return Group(*parts)


def estimate_docs_detail_lines(audit: AuditPreview, *, width: int) -> int:
    from io import StringIO

    from rich.console import Console

    buffer = StringIO()
    console = Console(file=buffer, width=max(20, width), force_terminal=True)
    console.print(build_docs_detail_content(audit))
    return max(4, len(buffer.getvalue().splitlines()))


def compute_docs_detail_height(content_lines: int, *, screen_height: int) -> int:
    max_height = max(8, screen_height // 2)
    desired = max(8, content_lines + 4)
    return min(desired, max_height)


def build_docs_content(snapshot: AppSnapshot, nav: NavState) -> ContentViewModel:
    workspace, project = resolve_nav_selection(snapshot, nav)
    header = build_page_header(snapshot, nav)
    if project is None:
        return ContentViewModel(header=header, body="Selecciona un proyecto.", footer_hints="q Salir  ·  r Refrescar")

    return ContentViewModel(
        header=header,
        body="",
        footer_hints="",
    )


def build_content_view_model(snapshot: AppSnapshot, nav: NavState, *, content_width: int | None = None) -> ContentViewModel:
    if nav.view == "workspace_empty":
        return build_home_content(snapshot, nav)
    if nav.view == "project_home":
        return build_home_content(snapshot, nav)
    if nav.view == "project_tasks":
        return build_tasks_content(snapshot, nav, content_width=content_width)
    if nav.view == "project_docs":
        return build_docs_content(snapshot, nav)
    return build_home_content(snapshot, nav)


def resolve_browser_selection(
    snapshot: AppSnapshot,
    *,
    selected_workspace_id: str | None = None,
    selected_project_id: str | None = None,
    selected_task_id: str | None = None,
) -> BrowserSelection:
    nav = NavState(
        workspace_id=selected_workspace_id,
        project_id=selected_project_id,
        selected_task_id=selected_task_id,
    )
    workspace, project = resolve_nav_selection(snapshot, nav)
    task = None
    if project is not None:
        if selected_task_id:
            task = next((item for item in project.ready_tasks if item.task_id == selected_task_id), None)
            if task is None:
                task = next((item for item in project.all_tasks if item.task_id == selected_task_id), None)
        if task is None and project.ready_tasks:
            task = project.ready_tasks[0]
        elif task is None and project.all_tasks:
            task = project.all_tasks[0]
    elif snapshot.ready_tasks:
        if selected_task_id:
            task = next((item for item in snapshot.ready_tasks if item.task_id == selected_task_id), None)
        if task is None:
            task = snapshot.ready_tasks[0]
    return BrowserSelection(workspace=workspace, project=project, task=task)


def build_home_sections(snapshot: AppSnapshot, selection: BrowserSelection | None = None) -> tuple[HomeSection, ...]:
    project = selection.project if selection else None
    sections = [
        HomeSection("Current context", current_context_lines(snapshot, selection)),
        HomeSection("Bootstrap", (bootstrap_summary(snapshot),)),
        HomeSection("Queue", (queue_summary(snapshot, selection),)),
        HomeSection("Ready now", ready_task_lines(snapshot, selection)),
        HomeSection("Status", (status_summary(snapshot, selection),)),
    ]
    notes = snapshot.notices
    if project and project.notices:
        notes = (*notes, *project.notices)
    if notes:
        sections.append(HomeSection("Notes", notes, tone="warning"))
    return tuple(sections)


def build_home_rows(snapshot: AppSnapshot) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [
        ("title", snapshot.title),
        ("focus", "Home"),
        ("muted", snapshot.subtitle),
        ("blank", ""),
    ]
    for section in build_home_sections(snapshot):
        rows.append(("label", section.title))
        for line in section.lines:
            rows.append((section.tone, line))
        rows.append(("blank", ""))
    rows.extend(
        [
            ("muted", f"Updated {snapshot.generated_at}" if snapshot.generated_at else "Updated just now"),
            ("footer", "q Quit  ·  r Refresh"),
        ]
    )
    return rows


def build_home_view_model(
    snapshot: AppSnapshot,
    *,
    selected_workspace_id: str | None = None,
    selected_project_id: str | None = None,
    selected_task_id: str | None = None,
) -> HomeViewModel:
    selection = resolve_browser_selection(
        snapshot,
        selected_workspace_id=selected_workspace_id,
        selected_project_id=selected_project_id,
        selected_task_id=selected_task_id,
    )
    return HomeViewModel(
        title=snapshot.title,
        subtitle=snapshot.subtitle,
        sections=build_home_sections(snapshot, selection),
        detail_panel=build_task_detail_panel(snapshot, selection),
        updated_at=f"Updated {snapshot.generated_at}" if snapshot.generated_at else "Updated just now",
    )


def build_task_detail_panel(snapshot: AppSnapshot, selection: BrowserSelection | None = None) -> TaskDetailPanel:
    project = selection.project if selection else None
    workspace = selection.workspace if selection else None
    ready_tasks = project.ready_tasks if project else (() if workspace else snapshot.ready_tasks)
    if not ready_tasks:
        if project:
            summary = (
                f"Project · {project.name}",
                "No ready tasks are visible for this project yet.",
            )
            title = project.name
        elif workspace:
            summary = (
                f"Workspace · {workspace.name}",
                "No visible projects are available in this workspace.",
            )
            title = workspace.name
        else:
            summary = (
                "When a ready task appears, this calm side panel will hold its context.",
                "For now, the home view stays read-only and lightly structured.",
            )
            title = "No ready task selected"
        return TaskDetailPanel(
            eyebrow="Project detail" if project else "Workspace detail" if workspace else "Task detail",
            title=title,
            summary=summary,
            metadata=(
                DetailField("Status", "Waiting for ready work" if project or not workspace else "Waiting for visible projects"),
                DetailField("Priority", "—"),
                DetailField("Effort", "—"),
                DetailField("Risk", "—"),
                DetailField("Type", "Project" if project else "Workspace" if workspace else "—"),
                DetailField("Task ID", project.project_id if project else workspace.workspace_id if workspace else "—"),
            ),
        )

    task = selection.task if selection and selection.task is not None else ready_tasks[0]
    metadata = tuple(
        field
        for field in (
            DetailField("Status", labelize(task.state) if task.state else "Unknown"),
            DetailField("Priority", labelize(task.priority) if task.priority else "Unknown"),
            DetailField("Effort", labelize(task.effort) if task.effort else "Unknown"),
            DetailField("Risk", labelize(task.risk) if task.risk else "Unknown"),
            DetailField("Type", labelize(task.task_type) if task.task_type else "Unknown"),
            DetailField("Task ID", task.task_id or "Unknown"),
        )
        if field.value
    )
    return TaskDetailPanel(
        eyebrow="Selected context",
        title=task.description or "Untitled task",
        summary=(
            f"Project · {(project.name if project else snapshot.project_name) or 'Unknown project'}",
            "This panel follows the current ready queue and leaves room for future drill-down.",
        ),
        metadata=metadata,
    )


def load_home_view_model(
    *,
    snapshot_loader: Callable[..., AppSnapshot],
    repo_root: str,
    node_home: str | None = None,
    as_of: str | None = None,
    previous_snapshot: AppSnapshot | None = None,
    selected_workspace_id: str | None = None,
    selected_project_id: str | None = None,
    selected_task_id: str | None = None,
) -> tuple[AppSnapshot, HomeViewModel]:
    try:
        snapshot = snapshot_loader(repo_root=repo_root, node_home=node_home, as_of=as_of)
    except Exception:
        snapshot = _snapshot_after_refresh_failure(as_of=as_of, previous_snapshot=previous_snapshot)
    return snapshot, build_home_view_model(
        snapshot,
        selected_workspace_id=selected_workspace_id,
        selected_project_id=selected_project_id,
        selected_task_id=selected_task_id,
    )


def current_context_lines(snapshot: AppSnapshot, selection: BrowserSelection | None = None) -> tuple[str, ...]:
    project = selection.project if selection else None
    workspace = selection.workspace if selection else None
    lines: list[str] = []
    if project:
        lines.append(f"Project · {project.name}")
    elif workspace:
        lines.append("Project · No visible project selected")
    elif snapshot.project_name:
        lines.append(f"Project · {snapshot.project_name}")
    else:
        lines.append("Project · No adopted project")

    if workspace:
        count = len(workspace.projects)
        noun = "project" if count == 1 else "projects"
        lines.append(f"Workspace · {workspace.name} ({count} {noun})")
    elif snapshot.workspace_name:
        count = snapshot.workspace_project_count or 0
        noun = "project" if count == 1 else "projects"
        lines.append(f"Workspace · {snapshot.workspace_name} ({count} {noun})")
    else:
        lines.append("Workspace · No workspace summary yet")
    return tuple(lines)


def ready_task_lines(snapshot: AppSnapshot, selection: BrowserSelection | None = None) -> tuple[str, ...]:
    project = selection.project if selection else None
    workspace = selection.workspace if selection else None
    if workspace and project is None:
        return ("No visible projects in this workspace.",)
    ready_tasks = project.ready_tasks if project else snapshot.ready_tasks
    if not ready_tasks:
        return ("No ready tasks yet.",)
    return tuple(
        f"• {task.description} · {task.priority} priority · {task.effort} effort"
        for task in ready_tasks
    )


def bootstrap_summary(snapshot: AppSnapshot) -> str:
    if snapshot.bootstrap_state == "adopted":
        project = snapshot.project_name or "current project"
        return f"Adopted · local reads available for {project}"
    if snapshot.bootstrap_state == "initialized":
        return "Initialized · waiting for repository adoption"
    if snapshot.bootstrap_state == "uninitialized":
        return "Uninitialized · no local runtime data yet"
    return "Unavailable · local runtime data could not be read"


def queue_summary(snapshot: AppSnapshot, selection: BrowserSelection | None = None) -> str:
    project = selection.project if selection else None
    workspace = selection.workspace if selection else None
    if workspace and project is None:
        return "Queue counts will appear when a visible project is selected."
    queue_counts = project.queue_counts if project else snapshot.queue_counts
    if not queue_counts:
        return "Queue counts will appear when project reads are available."
    ordered_keys = ("ready", "blocked", "critical", "done", "expired_claim")
    parts = [f"{labelize(key)} {queue_counts.get(key, 0)}" for key in ordered_keys if key in queue_counts]
    return " · ".join(parts)


def status_summary(snapshot: AppSnapshot, selection: BrowserSelection | None = None) -> str:
    project = selection.project if selection else None
    workspace = selection.workspace if selection else None
    if project:
        return project.sync_summary or "Local read-only shell."
    if workspace:
        return "Workspace selected · no visible project details available."
    return snapshot.sync_summary or "Local read-only shell."


def _snapshot_after_refresh_failure(*, as_of: str | None, previous_snapshot: AppSnapshot | None) -> AppSnapshot:
    notice = "Refresh failed unexpectedly. Existing data is still shown when available; press r to try again."
    if previous_snapshot is None:
        return snapshot_with_notice(
            AppSnapshot(generated_at=resolve_as_of(as_of), bootstrap_state="unavailable"),
            notice,
        )
    snapshot = replace(previous_snapshot, generated_at=resolve_as_of(as_of))
    return snapshot_with_notice(snapshot, notice)
