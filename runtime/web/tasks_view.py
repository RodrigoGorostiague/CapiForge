from __future__ import annotations

from urllib.parse import urlencode

from fastapi import Request

from runtime.tui.data import NavState, count_tasks_by_filter, filter_tasks, resolve_nav_selection
from runtime.tui.task_fields import TASK_FIELD_OPTIONS
from runtime.tui.view import TASK_FILTER_OPTIONS, TASK_SORTABLE_COLUMNS, sort_tasks_for_view
from runtime.web.context import load_snapshot, nav_expansion_params, nav_from_query
from runtime.web.helpers import find_audit, paginate_tasks

SORTABLE_COLUMNS = (
    ("description", "Descripción"),
    ("state", "Estado"),
    ("priority", "Prioridad"),
    ("task_type", "Tipo"),
    ("effort", "Esfuerzo"),
    ("risk", "Riesgo"),
)


def render_template(request: Request, name: str, context: dict) -> str:
    return request.state.templates.get_template(name).render({**context, "request": request})


def _normalize_sort(sort_column: str | None) -> str:
    if sort_column in TASK_SORTABLE_COLUMNS:
        return sort_column
    return "description"


def _normalize_sort_dir(sort_dir: str | None) -> str:
    return "desc" if sort_dir == "desc" else "asc"


def _tasks_params(
    *,
    project_id: str,
    workspace_id: str,
    task_filter: str,
    page: int,
    sort_column: str,
    sort_dir: str,
    task_id: str | None = None,
    extra: dict[str, str] | None = None,
) -> dict[str, str]:
    params = {
        "project_id": project_id,
        "workspace_id": workspace_id,
        "filter": task_filter,
        "page": str(page),
        "sort": sort_column,
        "sort_dir": sort_dir,
    }
    if task_id:
        params["task_id"] = task_id
    if extra:
        params.update(extra)
    return params


def partial_panel_url(**params: str | int | None) -> str:
    clean = {key: str(value) for key, value in params.items() if value not in (None, "")}
    return f"/api/partials/tasks-panel?{urlencode(clean)}"


def tasks_page_url(**params: str | int | None) -> str:
    clean = {key: str(value) for key, value in params.items() if value not in (None, "")}
    return f"/tasks?{urlencode(clean)}"


def _next_sort(sort_column: str, sort_dir: str, target_column: str) -> tuple[str, str]:
    if target_column == sort_column:
        return target_column, "desc" if sort_dir == "asc" else "asc"
    return target_column, "asc"


def build_tasks_view_context(
    request: Request,
    *,
    workspace_id: str | None = None,
    project_id: str | None = None,
    task_filter: str | None = None,
    selected_task_id: str | None = None,
    page: int | None = None,
    sort_column: str | None = None,
    sort_dir: str | None = None,
) -> dict:
    ctx = request.state.web_ctx
    snapshot = load_snapshot(ctx)
    query = request.query_params

    resolved_filter = task_filter or query.get("filter", "all")
    resolved_sort = _normalize_sort(sort_column or query.get("sort"))
    resolved_sort_dir = _normalize_sort_dir(sort_dir or query.get("sort_dir"))
    resolved_page = page if page is not None else (int(query.get("page", "1")) if query.get("page", "1").isdigit() else 1)
    resolved_task_id = selected_task_id if selected_task_id is not None else query.get("task_id")

    nav = nav_from_query(
        snapshot,
        workspace_id=workspace_id or query.get("workspace_id"),
        project_id=project_id or query.get("project_id"),
        route="tasks",
        task_filter=resolved_filter,
        selected_task_id=resolved_task_id,
        expanded_ws=query.get("expanded_ws"),
        expanded_proj=query.get("expanded_proj"),
        has_expanded_ws="expanded_ws" in query,
        has_expanded_proj="expanded_proj" in query,
    )
    _workspace, project = resolve_nav_selection(snapshot, nav)
    nav_params = nav_expansion_params(nav)

    base = {
        "nav": nav,
        "project": project,
        "sort_column": resolved_sort,
        "sort_dir": resolved_sort_dir,
        "refresh_seconds": ctx.refresh_seconds,
        "realtime_enabled": ctx.realtime_enabled,
        "filter_options": [],
        "sort_columns": [],
        "tasks": (),
        "selected_task": None,
        "selected_audit": None,
        "tasks_page": {
            "page": 1,
            "page_size": 12,
            "total": 0,
            "total_pages": 1,
            "has_prev": False,
            "has_next": False,
            "prev_url": "",
            "next_url": "",
            "prev_page_url": "",
            "next_page_url": "",
        },
        "panel_url": partial_panel_url(filter=resolved_filter, page=1, sort=resolved_sort, sort_dir=resolved_sort_dir),
    }

    if project is None:
        return base

    counts = count_tasks_by_filter(project.all_tasks)
    filter_options = []
    for filter_id, label, _shortcut in TASK_FILTER_OPTIONS:
        filter_options.append(
            {
                "label": label,
                "count": counts.get(filter_id, 0),
                "active": nav.task_filter == filter_id,
                "partial_url": partial_panel_url(
                    **_tasks_params(
                        project_id=project.project_id,
                        workspace_id=project.workspace_id,
                        task_filter=filter_id,
                        page=1,
                        sort_column=resolved_sort,
                        sort_dir=resolved_sort_dir,
                        task_id=resolved_task_id,
                        extra=nav_params,
                    )
                ),
                "url": tasks_page_url(
                    **_tasks_params(
                        project_id=project.project_id,
                        workspace_id=project.workspace_id,
                        task_filter=filter_id,
                        page=1,
                        sort_column=resolved_sort,
                        sort_dir=resolved_sort_dir,
                        task_id=resolved_task_id,
                        extra=nav_params,
                    )
                ),
            }
        )

    filtered_tasks = filter_tasks(project.all_tasks, nav.task_filter)
    sorted_tasks = sort_tasks_for_view(
        filtered_tasks,
        sort_column=resolved_sort,
        reverse=resolved_sort_dir == "desc",
    )
    pagination = paginate_tasks(sorted_tasks, page=resolved_page)
    page_tasks = pagination["items"]

    selected = None
    if resolved_task_id:
        for task in sorted_tasks:
            if task.task_id == resolved_task_id:
                selected = task
                break
    if selected is None and page_tasks and not resolved_task_id:
        selected = page_tasks[0]

    sort_columns = []
    for column_key, column_label in SORTABLE_COLUMNS:
        next_sort, next_dir = _next_sort(resolved_sort, resolved_sort_dir, column_key)
        params = _tasks_params(
            project_id=project.project_id,
            workspace_id=project.workspace_id,
            task_filter=nav.task_filter,
            page=pagination["page"],
            sort_column=next_sort,
            sort_dir=next_dir,
            task_id=selected.task_id if selected else resolved_task_id,
            extra=nav_params,
        )
        sort_columns.append(
            {
                "label": column_label,
                "active": column_key == resolved_sort,
                "indicator": "↓" if column_key == resolved_sort and resolved_sort_dir == "desc" else ("↑" if column_key == resolved_sort else ""),
                "partial_url": partial_panel_url(**params),
                "page_url": tasks_page_url(**params),
            }
        )

    page_params = _tasks_params(
        project_id=project.project_id,
        workspace_id=project.workspace_id,
        task_filter=nav.task_filter,
        page=pagination["page"],
        sort_column=resolved_sort,
        sort_dir=resolved_sort_dir,
        task_id=selected.task_id if selected else resolved_task_id,
    )
    prev_params = {**page_params, "page": str(max(1, pagination["page"] - 1))}
    next_params = {**page_params, "page": str(min(pagination["total_pages"], pagination["page"] + 1))}

    tasks_page = {
        "page": pagination["page"],
        "page_size": pagination["page_size"],
        "total": pagination["total"],
        "total_pages": pagination["total_pages"],
        "has_prev": pagination["has_prev"],
        "has_next": pagination["has_next"],
        "prev_url": partial_panel_url(**prev_params),
        "next_url": partial_panel_url(**next_params),
        "prev_page_url": tasks_page_url(**prev_params),
        "next_page_url": tasks_page_url(**next_params),
    }

    panel_params = _tasks_params(
        project_id=project.project_id,
        workspace_id=project.workspace_id,
        task_filter=nav.task_filter,
        page=pagination["page"],
        sort_column=resolved_sort,
        sort_dir=resolved_sort_dir,
        task_id=selected.task_id if selected else resolved_task_id,
    )

    return {
        **base,
        "filter_options": filter_options,
        "sort_columns": sort_columns,
        "tasks": page_tasks,
        "selected_task": selected,
        "selected_audit": find_audit(project.audits, selected.origin_audit_id) if selected else None,
        "tasks_page": tasks_page,
        "panel_url": partial_panel_url(**panel_params),
        "priority_options": TASK_FIELD_OPTIONS["priority"],
        "task_type_options": TASK_FIELD_OPTIONS["task_type"],
        "initial_state_options": ("proposed", "ready"),
        "selected_priority": "medium",
        "selected_task_type": "feature",
        "selected_initial_state": "ready",
    }


def render_tasks_panel_bundle(request: Request, context: dict | None = None, **kwargs: object) -> tuple[str, str]:
    ctx = context or build_tasks_view_context(request, **kwargs)  # type: ignore[arg-type]
    panel_html = render_template(request, "partials/tasks_panel.html", ctx)
    refresh_html = ""
    if ctx.get("refresh_seconds"):
        refresh_html = render_template(request, "partials/tasks_refresh_trigger.html", ctx)
    return panel_html, refresh_html
