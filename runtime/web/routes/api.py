from __future__ import annotations

from urllib.parse import urlencode

from pathlib import Path

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from runtime.tui.actions import WEB_AGENT_ID, WEB_SESSION_ID, claim_task, release_task, transition_task, update_task_attribute, upsert_project_page
from runtime.web.adopt_folder import adopt_folder_as_project
from runtime.web.context import load_snapshot, nav_from_query
from runtime.web.folder_picker import pick_folder_native
from runtime.web.project_registry import content_repo_for_project
from runtime.web.sync_status import build_coord_meta
from runtime.web.tasks_view import build_tasks_view_context, render_template, render_tasks_panel_bundle

router = APIRouter()


def _content_paths(request: Request, project_id: str) -> tuple:
    ctx = request.state.web_ctx
    return content_repo_for_project(ctx.repo_root, ctx.node_home, project_id)


def _redirect_tasks(request: Request, *, task_id: str | None = None, message: str | None = None, **extra: str) -> RedirectResponse:
    params = dict(request.query_params)
    params.update({key: value for key, value in extra.items() if value})
    if task_id:
        params["task_id"] = task_id
    if message:
        params["msg"] = message
    query = urlencode(params)
    url = f"/tasks?{query}" if query else "/tasks"
    return RedirectResponse(url=url, status_code=303)


def _htmx_action_response(
    request: Request,
    *,
    message: str,
    ok: bool,
    workspace_id: str,
    project_id: str,
    task_filter: str,
    task_id: str,
    page: int | None = None,
    sort: str | None = None,
    sort_dir: str | None = None,
) -> HTMLResponse:
    context = build_tasks_view_context(
        request,
        workspace_id=workspace_id or None,
        project_id=project_id,
        task_filter=task_filter,
        selected_task_id=task_id,
        page=page,
        sort_column=sort,
        sort_dir=sort_dir,
    )
    panel_html, refresh_html = render_tasks_panel_bundle(request, context=context)
    toast_html = render_template(request, "partials/toast.html", {"message": message, "ok": ok})
    body = toast_html + f'<div id="tasks-panel" hx-swap-oob="innerHTML">{panel_html}</div>' + refresh_html
    return HTMLResponse(content=body)


@router.get("/partials/tasks-panel", response_class=HTMLResponse)
async def tasks_panel_partial(request: Request) -> HTMLResponse:
    panel_html, refresh_html = render_tasks_panel_bundle(request)
    return HTMLResponse(content=panel_html + refresh_html)


@router.get("/partials/sync-status", response_class=HTMLResponse)
async def sync_status_partial(request: Request) -> HTMLResponse:
    ctx = request.state.web_ctx
    snapshot = load_snapshot(ctx)
    project_id = request.query_params.get("project_id")
    project = None
    if project_id:
        for workspace in snapshot.workspaces:
            for candidate in workspace.projects:
                if candidate.project_id == project_id:
                    project = candidate
                    break
            if project is not None:
                break
    if project is None:
        nav = nav_from_query(
            snapshot,
            workspace_id=request.query_params.get("workspace_id"),
            project_id=project_id,
            route="home",
            has_expanded_ws=False,
            has_expanded_proj=False,
        )
        from runtime.tui.data import resolve_nav_selection

        _, project = resolve_nav_selection(snapshot, nav)

    sync_coord = None
    if project is not None:
        sync_coord = build_coord_meta(
            degraded=project.sync_degraded,
            pending_routes=project.sync_pending_routes,
        )
    html = render_template(
        request,
        "partials/sync_status.html",
        {
            "sync_coord": sync_coord,
            "refresh_seconds": ctx.refresh_seconds,
            "realtime_enabled": ctx.realtime_enabled,
        },
    )
    return HTMLResponse(content=html)


@router.post("/tasks/update-field", response_class=HTMLResponse, response_model=None)
async def task_update_field(
    request: Request,
    task_id: str = Form(...),
    project_id: str = Form(...),
    workspace_id: str = Form(""),
    filter: str = Form("all"),
    page: str = Form("1"),
    sort: str = Form("description"),
    sort_dir: str = Form("asc"),
    field: str = Form(...),
    value: str = Form(...),
) -> HTMLResponse:
    page_num = int(page) if page.isdigit() else 1
    ctx = request.state.web_ctx
    snapshot = load_snapshot(ctx)
    if snapshot.bootstrap_state != "adopted":
        message = "Error: Bootstrap not adopted."
        if request.headers.get("hx-request"):
            return _htmx_action_response(
                request,
                message=message,
                ok=False,
                workspace_id=workspace_id,
                project_id=project_id,
                task_filter=filter,
                task_id=task_id,
                page=page_num,
                sort=sort,
                sort_dir=sort_dir,
            )
        return _redirect_tasks(request, task_id=task_id, message=message, project_id=project_id, workspace_id=workspace_id, filter=filter)

    result = update_task_attribute(
        repo_root=_content_paths(request, project_id)[0],
        node_home=_content_paths(request, project_id)[1],
        project_id=project_id,
        task_id=task_id,
        field=field,
        value=value,
        agent_id=WEB_AGENT_ID,
        session_id=WEB_SESSION_ID,
    )
    message = result.message if result.ok else f"Error: {result.message}"
    if request.headers.get("hx-request"):
        return _htmx_action_response(
            request,
            message=message,
            ok=result.ok,
            workspace_id=workspace_id,
            project_id=project_id,
            task_filter=filter,
            task_id=task_id,
            page=page_num,
            sort=sort,
            sort_dir=sort_dir,
        )
    return _redirect_tasks(
        request,
        task_id=task_id,
        message=message,
        project_id=project_id,
        workspace_id=workspace_id,
        filter=filter,
        page=str(page_num),
        sort=sort,
        sort_dir=sort_dir,
    )


@router.post("/tasks/{action}", response_class=HTMLResponse, response_model=None)
async def task_action(
    request: Request,
    action: str,
    task_id: str = Form(...),
    project_id: str = Form(...),
    workspace_id: str = Form(""),
    filter: str = Form("all"),
    page: str = Form("1"),
    sort: str = Form("description"),
    sort_dir: str = Form("asc"),
) -> HTMLResponse:
    page_num = int(page) if page.isdigit() else 1
    ctx = request.state.web_ctx
    snapshot = load_snapshot(ctx)
    if snapshot.bootstrap_state != "adopted":
        message = "Error: Bootstrap not adopted."
        if request.headers.get("hx-request"):
            return _htmx_action_response(
                request,
                message=message,
                ok=False,
                workspace_id=workspace_id,
                project_id=project_id,
                task_filter=filter,
                task_id=task_id,
                page=page_num,
                sort=sort,
                sort_dir=sort_dir,
            )
        return _redirect_tasks(
            request,
            task_id=task_id,
            message=message,
            project_id=project_id,
            workspace_id=workspace_id,
            filter=filter,
        )

    kwargs = {
        "repo_root": _content_paths(request, project_id)[0],
        "node_home": _content_paths(request, project_id)[1],
        "project_id": project_id,
        "task_id": task_id,
        "agent_id": WEB_AGENT_ID,
        "session_id": WEB_SESSION_ID,
    }
    if action == "claim":
        result = claim_task(**kwargs, plan="Claimed from web UI")
    elif action == "release":
        result = release_task(**kwargs)
    elif action == "start":
        result = transition_task(**kwargs, requested_state="in_progress")
    elif action == "block":
        result = transition_task(**kwargs, requested_state="blocked")
    elif action == "done":
        result = transition_task(**kwargs, requested_state="done")
    else:
        message = "Error: Unknown action."
        if request.headers.get("hx-request"):
            return _htmx_action_response(
                request,
                message=message,
                ok=False,
                workspace_id=workspace_id,
                project_id=project_id,
                task_filter=filter,
                task_id=task_id,
                page=page_num,
                sort=sort,
                sort_dir=sort_dir,
            )
        return _redirect_tasks(
            request,
            task_id=task_id,
            message=message,
            project_id=project_id,
            workspace_id=workspace_id,
            filter=filter,
        )

    message = result.message if result.ok else f"Error: {result.message}"
    if request.headers.get("hx-request"):
        return _htmx_action_response(
            request,
            message=message,
            ok=result.ok,
            workspace_id=workspace_id,
            project_id=project_id,
            task_filter=filter,
            task_id=task_id,
            page=page_num,
            sort=sort,
            sort_dir=sort_dir,
        )

    return _redirect_tasks(
        request,
        task_id=task_id,
        message=message,
        project_id=project_id,
        workspace_id=workspace_id,
        filter=filter,
        page=str(page_num),
        sort=sort,
        sort_dir=sort_dir,
    )


@router.get("/projects/pick-folder")
async def pick_folder(request: Request) -> JSONResponse:
    initial = request.query_params.get("initial_dir")
    initial_dir = Path(initial).expanduser() if initial else request.state.web_ctx.repo_root.parent
    result = pick_folder_native(initial_dir=initial_dir)
    return JSONResponse({"ok": result.ok, "path": result.path, "message": result.message})


@router.get("/partials/add-project-form", response_class=HTMLResponse)
async def add_project_form(request: Request) -> HTMLResponse:
    workspace_id = request.query_params.get("workspace_id", "")
    html = render_template(
        request,
        "partials/add_project_form.html",
        {"workspace_id": workspace_id},
    )
    return HTMLResponse(content=html)


@router.post("/projects/adopt-folder", response_class=HTMLResponse, response_model=None)
async def adopt_folder_project(
    request: Request,
    workspace_id: str = Form(...),
    folder_path: str = Form(...),
) -> HTMLResponse | RedirectResponse:
    ctx = request.state.web_ctx
    result, project_id = adopt_folder_as_project(
        hub_repo_root=ctx.repo_root,
        hub_node_home=ctx.node_home,
        folder_path=folder_path,
        workspace_id=workspace_id,
    )
    if result.ok and project_id:
        params = {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "expanded_ws": workspace_id,
            "expanded_proj": project_id,
            "msg": result.message,
        }
        redirect_url = f"/?{urlencode(params)}"
        if request.headers.get("hx-request"):
            return HTMLResponse(content="", headers={"HX-Redirect": redirect_url})
        return RedirectResponse(url=redirect_url, status_code=303)

    message = result.message if result.ok else f"Error: {result.message}"
    if request.headers.get("hx-request"):
        toast_html = render_template(request, "partials/toast.html", {"message": message, "ok": result.ok})
        form_html = render_template(
            request,
            "partials/add_project_form.html",
            {"workspace_id": workspace_id, "error": message, "folder_path": folder_path},
        )
        return HTMLResponse(content=toast_html + f'<div id="add-project-panel" hx-swap-oob="innerHTML">{form_html}</div>')
    return RedirectResponse(url=f"/?msg={message}", status_code=303)


@router.post("/project-page/save", response_class=HTMLResponse, response_model=None)
async def save_project_page(
    request: Request,
    project_id: str = Form(...),
    workspace_id: str = Form(""),
    page_type: str = Form("purpose"),
    title: str = Form(""),
    content: str = Form(""),
) -> RedirectResponse:
    ctx = request.state.web_ctx
    repo_root, node_home = _content_paths(request, project_id)
    result = upsert_project_page(
        repo_root=repo_root,
        node_home=node_home,
        project_id=project_id,
        page_type=page_type,
        title=title,
        content=content,
    )
    params = {
        "workspace_id": workspace_id,
        "project_id": project_id,
        "msg": result.message if result.ok else f"Error: {result.message}",
    }
    redirect_url = f"/?{urlencode(params)}" if result.ok else f"/project-page?{urlencode({**params, 'page_type': page_type})}"
    return RedirectResponse(url=redirect_url, status_code=303)
