from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity
from runtime.tui.theme import DEFAULT_THEME, normalize_theme_name

LOCAL_AGENT_ID = "capiforge-tui"
LOCAL_SESSION_ID = "capiforge-tui-session"

DEFAULT_AUTO_REFRESH_SECONDS = 15
AUTO_REFRESH_OPTIONS = (0, 15, 30, 60)

ViewName = Literal["workspace_empty", "project_home", "project_tasks", "project_docs"]


@dataclass(frozen=True)
class TaskPreview:
    task_id: str
    description: str
    state: str
    priority: str
    effort: str
    risk: str
    task_type: str
    origin_audit_id: str = ""
    lifecycle_key: str | None = None
    blocked_reason: str | None = None
    blocked_next_step: str | None = None


ReadyTaskPreview = TaskPreview


@dataclass(frozen=True)
class AuditPreview:
    audit_id: str
    title: str
    state: str
    content: str = ""


@dataclass(frozen=True)
class LocalDocumentPreview:
    document_id: str
    storage_path: str


@dataclass(frozen=True)
class ProjectSnapshot:
    project_id: str
    workspace_id: str
    name: str
    canonical_link: str | None = None
    owner_node_id: str | None = None
    queue_counts: dict[str, int] = field(default_factory=dict)
    ready_tasks: tuple[TaskPreview, ...] = ()
    all_tasks: tuple[TaskPreview, ...] = ()
    audits: tuple[AuditPreview, ...] = ()
    local_documents: tuple[LocalDocumentPreview, ...] = ()
    sync_summary: str | None = None
    sync_degraded: bool = False
    sync_pending_routes: int = 0
    notices: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkspaceSnapshot:
    workspace_id: str
    name: str
    canonical_link: str | None = None
    projects: tuple[ProjectSnapshot, ...] = ()


@dataclass
class AppSnapshot:
    title: str = "CapiForge"
    subtitle: str = "Local workspace browser"
    bootstrap_state: str = "unavailable"
    generated_at: str = ""
    local_node_id: str | None = None
    node_db_path: str | None = None
    workspace_name: str | None = None
    workspace_project_count: int | None = None
    project_name: str | None = None
    project_id: str | None = None
    project_link: str | None = None
    owner_node_id: str | None = None
    queue_counts: dict[str, int] = field(default_factory=dict)
    ready_tasks: tuple[TaskPreview, ...] = ()
    sync_summary: str | None = None
    sync_degraded: bool = False
    sync_pending_routes: int = 0
    notices: tuple[str, ...] = ()
    workspaces: tuple[WorkspaceSnapshot, ...] = ()


HomeSnapshot = AppSnapshot


@dataclass(frozen=True)
class NavState:
    workspace_id: str | None = None
    project_id: str | None = None
    view: ViewName = "workspace_empty"
    selected_task_id: str | None = None
    selected_audit_id: str | None = None
    task_filter: str = "all"
    expanded_workspaces: frozenset[str] = field(default_factory=frozenset)
    expanded_projects: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class PersistedTuiSettings:
    nav: NavState | None = None
    theme: str = DEFAULT_THEME
    auto_refresh_seconds: int = DEFAULT_AUTO_REFRESH_SECONDS


def resolve_as_of(raw: str | None = None) -> str:
    if raw:
        return raw
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _task_preview_from_row(row: dict) -> TaskPreview:
    return TaskPreview(
        task_id=row["task_id"],
        description=row["description"],
        state=row["state"],
        priority=row["priority"],
        effort=row["effort"],
        risk=row["risk"],
        task_type=row["type"],
        origin_audit_id=row.get("origin_audit_id") or "",
        lifecycle_key=row.get("lifecycle_key"),
        blocked_reason=row.get("blocked_reason"),
        blocked_next_step=row.get("blocked_next_step"),
    )


def load_app_snapshot(*, repo_root: str | Path, node_home: str | Path | None = None, as_of: str | None = None) -> AppSnapshot:
    return load_home_snapshot(repo_root=repo_root, node_home=node_home, as_of=as_of)


def load_home_snapshot(*, repo_root: str | Path, node_home: str | Path | None = None, as_of: str | None = None) -> AppSnapshot:
    resolved_as_of = resolve_as_of(as_of)
    bootstrap = NodeBootstrap(repo_root=repo_root, node_home=node_home)
    try:
        state = bootstrap.status(interactive=False)
    except SurfaceError as exc:
        return AppSnapshot(
            bootstrap_state="unavailable",
            generated_at=resolved_as_of,
            notices=(f"Runtime data is unavailable right now ({exc.code}).",),
        )

    snapshot = AppSnapshot(
        bootstrap_state=state.state,
        generated_at=resolved_as_of,
        local_node_id=state.local_node_id,
        node_db_path=state.node_db_path,
    )
    adopted_project = state.adopted_project if state.state == "adopted" else None
    if adopted_project:
        snapshot.project_name = adopted_project.get("project_name")
        snapshot.project_id = adopted_project.get("project_id")

    store: NodeStore | None = None
    try:
        store = NodeStore.from_file(state.node_db_path)
        surface = NodeMCPSurface(store=store, router=NodeRouter(store), local_node_id=state.local_node_id)
        actor = ActorIdentity(node_id=state.local_node_id, agent_id=LOCAL_AGENT_ID, session_id=LOCAL_SESSION_ID)

        if adopted_project:
            workspace_response = _safe_surface_call(
                lambda: surface.workspace_get(workspace_id=adopted_project["workspace_id"], actor=actor),
                "Workspace details are unavailable.",
                snapshot,
            )
            if workspace_response:
                workspace = workspace_response["data"]
                snapshot.workspace_name = workspace.get("name")
                snapshot.workspace_project_count = len(workspace.get("projects", ()))

            entrypoint_response = _safe_surface_call(
                lambda: surface.project_entrypoint_get_local(project_id=adopted_project["project_id"], as_of=resolved_as_of),
                "Project summary is unavailable.",
                snapshot,
            )
            if entrypoint_response:
                entrypoint = entrypoint_response["data"]
                snapshot.project_name = entrypoint.get("project_name", snapshot.project_name)
                snapshot.project_link = entrypoint.get("project_link")
                snapshot.owner_node_id = entrypoint.get("owner_node_id")
                snapshot.queue_counts = dict(entrypoint.get("queue_counts", {}))

            ready_response = _safe_surface_call(
                lambda: surface.tasks_list_by_index(
                    project_id=adopted_project["project_id"],
                    index_name="ready",
                    as_of=resolved_as_of,
                    limit=5,
                    actor=actor,
                ),
                "Ready task previews are unavailable.",
                snapshot,
            )
            if ready_response:
                ready_tasks: list[TaskPreview] = []
                for task in ready_response["data"].get("tasks", ()):
                    stored_task = store.get_task(task["task_id"])
                    if not stored_task:
                        continue
                    ready_tasks.append(_task_preview_from_row(stored_task))
                snapshot.ready_tasks = tuple(ready_tasks)

            sync_response = _safe_surface_call(
                lambda: surface.sync_status(project_id=adopted_project["project_id"], actor=actor),
                "Sync visibility is unavailable.",
                snapshot,
            )
            if sync_response:
                sync_data = sync_response["data"]
                authority = sync_data.get("canonical_write_path", "unknown")
                pending_routes = sync_data.get("pending_routes", 0)
                snapshot.sync_degraded = bool(sync_data.get("degraded"))
                snapshot.sync_pending_routes = int(pending_routes)
                if sync_data.get("degraded"):
                    snapshot.sync_summary = f"Local-only visibility · {pending_routes} pending routes · authority {authority}"
                else:
                    snapshot.sync_summary = f"Connected visibility · {pending_routes} pending routes · authority {authority}"

        snapshot.workspaces = load_workspace_snapshots(
            store=store,
            surface=surface,
            actor=actor,
            local_node_id=state.local_node_id,
            as_of=resolved_as_of,
        )
    except Exception:
        return snapshot_with_notice(snapshot, _local_store_notice())
    finally:
        if store is not None:
            try:
                store.close()
            except Exception:
                snapshot = snapshot_with_notice(snapshot, "Local runtime data stayed readable, but cleanup did not finish cleanly.")

    return snapshot_with_notice(snapshot, _bootstrap_notice(state.state))


def snapshot_with_notice(snapshot: AppSnapshot, notice: str | None) -> AppSnapshot:
    if not notice:
        return snapshot
    if notice in snapshot.notices:
        return snapshot
    snapshot.notices = (*snapshot.notices, notice)
    return snapshot


def _safe_surface_call(callback, notice: str, snapshot: AppSnapshot) -> dict | None:
    try:
        return callback()
    except SurfaceError:
        snapshot.notices = (*snapshot.notices, notice)
        return None


def _bootstrap_notice(state: str) -> str | None:
    if state == "uninitialized":
        return "No local bootstrap yet. Run init, then adopt, to populate the home view."
    if state == "initialized":
        return "Bootstrap is ready, but no repository is adopted yet."
    return None


def _local_store_notice() -> str:
    return "Local runtime data could not be read right now. Showing any details loaded before the failure."


def load_workspace_snapshots(
    *,
    store: NodeStore,
    surface: NodeMCPSurface,
    actor: ActorIdentity,
    local_node_id: str,
    as_of: str,
) -> tuple[WorkspaceSnapshot, ...]:
    workspaces: list[WorkspaceSnapshot] = []
    for workspace in store.list_workspaces():
        projects: list[ProjectSnapshot] = []
        for project in store.list_workspace_projects(workspace["workspace_id"]):
            project_id = project["project_id"]
            if not store.has_project_access(local_node_id, project_id):
                continue
            projects.append(
                load_project_snapshot(
                    store=store,
                    surface=surface,
                    actor=actor,
                    as_of=as_of,
                    workspace_id=workspace["workspace_id"],
                    project=project,
                )
            )
        workspaces.append(
            WorkspaceSnapshot(
                workspace_id=workspace["workspace_id"],
                name=workspace.get("name") or "Unnamed workspace",
                canonical_link=workspace.get("canonical_link"),
                projects=tuple(projects),
            )
        )
    return tuple(workspaces)


def load_project_snapshot(
    *,
    store: NodeStore,
    surface: NodeMCPSurface,
    actor: ActorIdentity,
    as_of: str,
    workspace_id: str,
    project: dict,
) -> ProjectSnapshot:
    notices: list[str] = []
    queue_counts: dict[str, int] = {}
    project_name = project.get("name") or "Unnamed project"
    project_link = project.get("canonical_link")
    owner_node_id = project.get("owner_node_id")

    try:
        entrypoint = surface.project_entrypoint_get(project_id=project["project_id"], as_of=as_of, actor=actor)["data"]
        project_name = entrypoint.get("project_name", project_name)
        project_link = entrypoint.get("project_link", project_link)
        owner_node_id = entrypoint.get("owner_node_id", owner_node_id)
        queue_counts = dict(entrypoint.get("queue_counts", {}))
    except SurfaceError:
        notices.append("Project summary is unavailable.")

    ready_tasks: list[TaskPreview] = []
    try:
        ready_response = surface.tasks_list_by_index(
            project_id=project["project_id"],
            index_name="ready",
            as_of=as_of,
            limit=5,
            actor=actor,
        )
        for task in ready_response["data"].get("tasks", ()):
            stored_task = store.get_task(task["task_id"])
            if not stored_task:
                continue
            ready_tasks.append(_task_preview_from_row(stored_task))
    except SurfaceError:
        notices.append("Ready task previews are unavailable.")

    all_tasks = tuple(_task_preview_from_row(row) for row in store.list_project_tasks(project["project_id"]))
    audits = tuple(
        AuditPreview(
            audit_id=row["audit_id"],
            title=row["title"],
            state=row["state"],
            content=row.get("content") or "",
        )
        for row in store.list_project_audits(project["project_id"])
    )
    local_documents = tuple(
        LocalDocumentPreview(document_id=row["document_id"], storage_path=row["storage_path"])
        for row in store.list_local_documents(project["project_id"])
    )

    sync_summary: str | None = None
    sync_degraded = False
    sync_pending_routes = 0
    try:
        sync_data = surface.sync_status(project_id=project["project_id"], actor=actor)["data"]
        authority = sync_data.get("canonical_write_path", "unknown")
        pending_routes = sync_data.get("pending_routes", 0)
        sync_degraded = bool(sync_data.get("degraded"))
        sync_pending_routes = int(pending_routes)
        if sync_data.get("degraded"):
            sync_summary = f"Local-only visibility · {pending_routes} pending routes · authority {authority}"
        else:
            sync_summary = f"Connected visibility · {pending_routes} pending routes · authority {authority}"
    except SurfaceError:
        notices.append("Sync visibility is unavailable.")

    return ProjectSnapshot(
        project_id=project["project_id"],
        workspace_id=workspace_id,
        name=project_name,
        canonical_link=project_link,
        owner_node_id=owner_node_id,
        queue_counts=queue_counts,
        ready_tasks=tuple(ready_tasks),
        all_tasks=all_tasks,
        audits=audits,
        local_documents=local_documents,
        sync_summary=sync_summary,
        sync_degraded=sync_degraded,
        sync_pending_routes=sync_pending_routes,
        notices=tuple(notices),
    )


def slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower()).strip("-")
    return slug or "workspace"


def resolve_nav_selection(snapshot: AppSnapshot, nav: NavState) -> tuple[WorkspaceSnapshot | None, ProjectSnapshot | None]:
    workspace = next((item for item in snapshot.workspaces if item.workspace_id == nav.workspace_id), None)
    if workspace is None and nav.project_id:
        workspace = next(
            (item for item in snapshot.workspaces if any(project.project_id == nav.project_id for project in item.projects)),
            None,
        )
    if workspace is None and snapshot.project_id:
        workspace = next(
            (item for item in snapshot.workspaces if any(project.project_id == snapshot.project_id for project in item.projects)),
            None,
        )
    if workspace is None and snapshot.workspaces:
        workspace = snapshot.workspaces[0]

    project = None
    if workspace is not None:
        preferred_project_id = nav.project_id or snapshot.project_id
        if preferred_project_id:
            project = next((item for item in workspace.projects if item.project_id == preferred_project_id), None)
        if project is None and workspace.projects:
            project = workspace.projects[0]
    return workspace, project


def filter_tasks(tasks: tuple[TaskPreview, ...], task_filter: str) -> tuple[TaskPreview, ...]:
    if task_filter == "all":
        return tasks
    if task_filter == "active":
        return tuple(task for task in tasks if task.state in {"ready", "claimed", "in_progress"})
    if task_filter == "blocked":
        return tuple(task for task in tasks if task.state == "blocked")
    if task_filter == "done":
        return tuple(task for task in tasks if task.state == "done")
    return tasks


def count_tasks_by_filter(tasks: tuple[TaskPreview, ...]) -> dict[str, int]:
    return {
        "all": len(tasks),
        "active": len(filter_tasks(tasks, "active")),
        "blocked": len(filter_tasks(tasks, "blocked")),
        "done": len(filter_tasks(tasks, "done")),
    }


def default_nav_state(snapshot: AppSnapshot, previous: NavState | None = None) -> NavState:
    if not snapshot.workspaces:
        return NavState(view="workspace_empty")

    workspace = None
    project = None
    if previous:
        workspace, project = resolve_nav_selection(snapshot, previous)
    else:
        workspace, project = resolve_nav_selection(snapshot, NavState())

    expanded_workspaces = previous.expanded_workspaces if previous else frozenset()
    expanded_projects = previous.expanded_projects if previous else frozenset()
    if workspace:
        expanded_workspaces = frozenset(set(expanded_workspaces) | {workspace.workspace_id})
    if project:
        expanded_projects = frozenset(set(expanded_projects) | {project.project_id})

    view: ViewName = previous.view if previous and previous.view != "workspace_empty" else "project_home"
    if workspace and not project:
        view = "workspace_empty"

    return NavState(
        workspace_id=workspace.workspace_id if workspace else None,
        project_id=project.project_id if project else None,
        view=view if snapshot.workspaces else "workspace_empty",
        selected_task_id=previous.selected_task_id if previous else None,
        selected_audit_id=previous.selected_audit_id if previous else None,
        task_filter=previous.task_filter if previous else "all",
        expanded_workspaces=expanded_workspaces,
        expanded_projects=expanded_projects,
    )


def load_persisted_tui_state() -> PersistedTuiSettings:
    path = Path.home() / ".capiforge" / "tui-state.json"
    if not path.exists():
        return PersistedTuiSettings()
    try:
        import json

        raw = json.loads(path.read_text())
        nav = NavState(
            workspace_id=raw.get("workspace_id"),
            project_id=raw.get("project_id"),
            view=raw.get("view", "project_home"),
            task_filter=raw.get("task_filter", "all"),
            expanded_workspaces=frozenset(raw.get("expanded_workspaces", [])),
            expanded_projects=frozenset(raw.get("expanded_projects", [])),
        )
        return PersistedTuiSettings(
            nav=nav,
            theme=normalize_theme_name(raw.get("theme")),
            auto_refresh_seconds=int(raw.get("auto_refresh_seconds", DEFAULT_AUTO_REFRESH_SECONDS)),
        )
    except Exception:
        return PersistedTuiSettings()


def load_persisted_nav_state() -> NavState | None:
    return load_persisted_tui_state().nav


def persist_tui_state(*, nav: NavState, theme: str, auto_refresh_seconds: int = DEFAULT_AUTO_REFRESH_SECONDS) -> None:
    path = Path.home() / ".capiforge" / "tui-state.json"
    try:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "workspace_id": nav.workspace_id,
                    "project_id": nav.project_id,
                    "view": nav.view,
                    "task_filter": nav.task_filter,
                    "theme": normalize_theme_name(theme),
                    "auto_refresh_seconds": auto_refresh_seconds,
                    "expanded_workspaces": sorted(nav.expanded_workspaces),
                    "expanded_projects": sorted(nav.expanded_projects),
                },
                indent=2,
            )
        )
    except Exception:
        return


def persist_nav_state(nav: NavState, *, theme: str = DEFAULT_THEME) -> None:
    persist_tui_state(nav=nav, theme=theme)
