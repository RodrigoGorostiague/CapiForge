from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlencode

from runtime.hub.data import AppSnapshot, ProjectSnapshot, TaskPreview
from runtime.web.i18n import audit_count_label, pill_label

QUEUE_STATES = ("ready", "in_progress", "claimed", "blocked", "done")

STATE_TASK_FILTER = {
    "ready": "active",
    "in_progress": "active",
    "claimed": "active",
    "blocked": "blocked",
    "done": "done",
}


@dataclass(frozen=True)
class HomeSummaryItem:
    label: str
    value: str
    hint: str | None = None


@dataclass(frozen=True)
class HomeQueueChip:
    state: str
    count: int
    label: str
    url: str


@dataclass(frozen=True)
class HomeTaskLink:
    task: TaskPreview
    url: str


@dataclass(frozen=True)
class HomeDashboard:
    summary_items: tuple[HomeSummaryItem, ...]
    queue_chips: tuple[HomeQueueChip, ...]
    next_task: HomeTaskLink | None
    recent_tasks: tuple[HomeTaskLink, ...]
    docs_label: str
    local_docs_count: int
    tasks_url: str
    docs_url: str


def _short_id(value: str | None, *, head: int = 10, tail: int = 4) -> str:
    if not value:
        return "desconocido"
    if len(value) <= head + tail + 1:
        return value
    return f"{value[:head]}…{value[-tail:]}"


def _queue_count(project: ProjectSnapshot, key: str) -> int:
    count = project.queue_counts.get(key, 0)
    if count:
        return int(count)
    if key in {"in_progress", "claimed"}:
        return sum(1 for task in project.all_tasks if task.state == key)
    return 0


def _tasks_url(*, project_id: str, workspace_id: str, task_filter: str, task_id: str | None = None) -> str:
    params = {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "filter": task_filter,
    }
    if task_id:
        params["task_id"] = task_id
    return f"/tasks?{urlencode(params)}"


def _sync_summary_label(project: ProjectSnapshot) -> str:
    if project.sync_degraded:
        pending = project.sync_pending_routes
        if pending:
            return f"Solo local · {pending} rutas pendientes"
        return "Solo local"
    pending = project.sync_pending_routes
    if pending:
        return f"Conectado · {pending} rutas pendientes"
    return "Conectado"


def _owner_summary(project: ProjectSnapshot, snapshot: AppSnapshot) -> HomeSummaryItem:
    owner = project.owner_node_id
    local = snapshot.local_node_id
    if owner and local and owner == local:
        return HomeSummaryItem("Propietario", "Este nodo", hint=_short_id(owner))
    if owner:
        return HomeSummaryItem("Propietario", "Otro nodo", hint=_short_id(owner))
    return HomeSummaryItem("Propietario", "Desconocido")


def build_home_dashboard(
    *,
    project: ProjectSnapshot,
    snapshot: AppSnapshot,
    workspace_name: str | None,
) -> HomeDashboard:
    summary_items = (
        HomeSummaryItem("Workspace", workspace_name or "—"),
        HomeSummaryItem("Proyecto", project.name),
        _owner_summary(project, snapshot),
        HomeSummaryItem("Sincronización", _sync_summary_label(project)),
        HomeSummaryItem("Tareas", str(len(project.all_tasks))),
    )

    queue_chips = tuple(
        HomeQueueChip(
            state=state,
            count=count,
            label=f"{pill_label(state)} {count}",
            url=_tasks_url(
                project_id=project.project_id,
                workspace_id=project.workspace_id,
                task_filter=STATE_TASK_FILTER[state],
            ),
        )
        for state in QUEUE_STATES
        if (count := _queue_count(project, state))
    )

    next_task = None
    if project.ready_tasks:
        task = project.ready_tasks[0]
        next_task = HomeTaskLink(
            task=task,
            url=_tasks_url(
                project_id=project.project_id,
                workspace_id=project.workspace_id,
                task_filter="active",
                task_id=task.task_id,
            ),
        )

    recent_tasks = tuple(
        HomeTaskLink(
            task=task,
            url=_tasks_url(
                project_id=project.project_id,
                workspace_id=project.workspace_id,
                task_filter="all",
                task_id=task.task_id,
            ),
        )
        for task in project.all_tasks[:5]
    )

    docs_url = f"/docs?{urlencode({'project_id': project.project_id, 'workspace_id': project.workspace_id})}"
    tasks_url = _tasks_url(
        project_id=project.project_id,
        workspace_id=project.workspace_id,
        task_filter="all",
    )

    return HomeDashboard(
        summary_items=summary_items,
        queue_chips=queue_chips,
        next_task=next_task,
        recent_tasks=recent_tasks,
        docs_label=audit_count_label(len(project.audits)),
        local_docs_count=len(project.local_documents),
        tasks_url=tasks_url,
        docs_url=docs_url,
    )


def task_detail_url(project: ProjectSnapshot, task: TaskPreview, *, task_filter: str = "all") -> str:
    return _tasks_url(
        project_id=project.project_id,
        workspace_id=project.workspace_id,
        task_filter=task_filter,
        task_id=task.task_id,
    )
