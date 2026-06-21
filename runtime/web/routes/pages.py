from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from runtime.tui.data import resolve_nav_selection
from runtime.tui.view import build_page_header, resolve_selected_audit, tasks_for_audit
from runtime.web.context import ViewRoute, load_snapshot, nav_from_query, sidebar_nav
from runtime.web.markdown import render_markdown
from runtime.web.sync_status import build_sync_indicator
from runtime.web.tasks_view import build_tasks_view_context

router = APIRouter()


def _common_context(request: Request, route: ViewRoute, **query_overrides) -> dict:
    ctx = request.state.web_ctx
    snapshot = load_snapshot(ctx)
    nav = nav_from_query(
        snapshot,
        workspace_id=query_overrides.pop("workspace_id", request.query_params.get("workspace_id")),
        project_id=query_overrides.pop("project_id", request.query_params.get("project_id")),
        route=route,
        task_filter=query_overrides.pop("task_filter", request.query_params.get("filter", "all")),
        selected_task_id=query_overrides.pop("selected_task_id", request.query_params.get("task_id")),
        selected_audit_id=query_overrides.pop("selected_audit_id", request.query_params.get("audit_id")),
        expanded_ws=request.query_params.get("expanded_ws"),
        expanded_proj=request.query_params.get("expanded_proj"),
        has_expanded_ws="expanded_ws" in request.query_params,
        has_expanded_proj="expanded_proj" in request.query_params,
    )
    workspace, project = resolve_nav_selection(snapshot, nav)
    header = build_page_header(snapshot, nav)
    sync_indicator = None
    if project is not None:
        sync_indicator = build_sync_indicator(
            degraded=project.sync_degraded,
            pending_routes=project.sync_pending_routes,
            refresh_seconds=ctx.refresh_seconds,
        )
    return {
        "request": request,
        "snapshot": snapshot,
        "nav": nav,
        "workspace": workspace,
        "project": project,
        "header": header,
        "sidebar_items": sidebar_nav(snapshot, nav, request=request, route=route),
        "refresh_seconds": ctx.refresh_seconds,
        "route": route,
        "sync_indicator": sync_indicator,
        **query_overrides,
    }


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request) -> HTMLResponse:
    context = _common_context(request, "home")
    project = context["project"]
    queue_items = []
    if project:
        for key in ("ready", "in_progress", "claimed", "blocked", "done"):
            count = project.queue_counts.get(key)
            if not count and key in {"in_progress", "claimed"}:
                count = sum(1 for t in project.all_tasks if t.state == key)
            if count:
                queue_items.append((key, count))
    context["queue_items"] = queue_items
    context["recent_tasks"] = (project.all_tasks[:3] if project else ())
    return request.state.templates.TemplateResponse(request, "home.html", context)


@router.get("/tasks", response_class=HTMLResponse)
async def tasks_page(request: Request) -> HTMLResponse:
    context = _common_context(request, "tasks")
    context.update(build_tasks_view_context(request))
    return request.state.templates.TemplateResponse(request, "tasks.html", context)


@router.get("/docs", response_class=HTMLResponse)
async def docs_page(request: Request) -> HTMLResponse:
    context = _common_context(request, "docs")
    project = context["project"]
    nav = context["nav"]
    if project:
        selected_audit = resolve_selected_audit(project.audits, nav.selected_audit_id)
        linked_tasks = tasks_for_audit(project.all_tasks, selected_audit.audit_id) if selected_audit else ()
        context["audits"] = project.audits
        context["local_documents"] = project.local_documents
        context["selected_audit"] = selected_audit
        context["audit_html"] = render_markdown(selected_audit.content) if selected_audit else ""
        context["linked_tasks"] = linked_tasks
    else:
        context["audits"] = ()
        context["local_documents"] = ()
        context["selected_audit"] = None
        context["audit_html"] = ""
        context["linked_tasks"] = ()
    return request.state.templates.TemplateResponse(request, "docs.html", context)
