from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from runtime.hub.data import LocalDocumentPreview, resolve_nav_selection
from runtime.hub.pages import build_page_header, resolve_selected_audit, tasks_for_audit
from runtime.web.context import ViewRoute, build_project_switcher, load_snapshot, nav_from_query, sidebar_nav
from runtime.web.docs_detail import (
    build_audit_detail_sections,
    build_document_detail_sections,
    resolve_docs_detail_title,
)
from runtime.web.home_dashboard import build_home_dashboard
from runtime.web.i18n import PAGE_TYPE_TITLES
from runtime.web.local_docs import resolve_local_document, resolve_repo_markdown_path
from runtime.web.markdown import MarkdownRenderContext, render_markdown
from runtime.web.project_registry import active_project_repo_path, content_repo_for_project
from runtime.web.sync_status import build_coord_meta, build_sync_indicator
from runtime.web.tasks_view import build_tasks_view_context, render_template

router = APIRouter()


def _markdown_context(project) -> MarkdownRenderContext | None:
    if project is None:
        return None
    return MarkdownRenderContext(
        project_id=project.project_id,
        workspace_id=project.workspace_id,
        local_documents=project.local_documents,
    )


def _render_project_markdown(content: str, *, project, base_path: str | None = None) -> str:
    context = _markdown_context(project)
    if context is None:
        return render_markdown(content)
    if base_path:
        context = MarkdownRenderContext(
            project_id=context.project_id,
            workspace_id=context.workspace_id,
            local_documents=context.local_documents,
            base_path=base_path,
        )
    return render_markdown(content, context=context)


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
    active_repo = None
    if project is not None:
        active_repo = str(active_project_repo_path(ctx.repo_root, ctx.node_home, project.project_id))
        if header.subtitle:
            header = replace(header, subtitle=f"{active_repo} · {header.subtitle}")
        else:
            header = replace(header, subtitle=active_repo)
    sync_indicator = None
    sync_coord = None
    if project is not None:
        sync_indicator = build_sync_indicator(
            degraded=project.sync_degraded,
            pending_routes=project.sync_pending_routes,
            refresh_seconds=ctx.refresh_seconds,
        )
        sync_coord = build_coord_meta(
            degraded=project.sync_degraded,
            pending_routes=project.sync_pending_routes,
        )
    return {
        "request": request,
        "snapshot": snapshot,
        "nav": nav,
        "workspace": workspace,
        "project": project,
        "header": header,
        "sidebar_items": sidebar_nav(snapshot, nav, request=request, route=route),
        "project_switcher": build_project_switcher(snapshot, nav, request=request, route=route),
        "active_project_repo": active_repo,
        "refresh_seconds": ctx.refresh_seconds,
        "realtime_enabled": ctx.realtime_enabled,
        "route": route,
        "sync_indicator": sync_indicator,
        "sync_coord": sync_coord,
        **query_overrides,
    }


@router.get("/", response_class=HTMLResponse)
async def home_page(request: Request) -> HTMLResponse:
    context = _common_context(request, "home")
    project = context["project"]
    workspace = context["workspace"]
    if project:
        context["home"] = build_home_dashboard(
            project=project,
            snapshot=context["snapshot"],
            workspace_name=workspace.name if workspace else None,
        )
        context["purpose_page"] = next((p for p in project.project_pages if p.page_type == "purpose"), None)
        context["architecture_page"] = next((p for p in project.project_pages if p.page_type == "architecture"), None)
        context["purpose_html"] = _render_project_markdown(context["purpose_page"].content, project=project) if context["purpose_page"] and context["purpose_page"].content else ""
        context["architecture_html"] = (
            _render_project_markdown(context["architecture_page"].content, project=project)
            if context["architecture_page"] and context["architecture_page"].content
            else ""
        )
    else:
        context["home"] = None
        context["purpose_page"] = None
        context["architecture_page"] = None
        context["purpose_html"] = ""
        context["architecture_html"] = ""
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
    document_id = request.query_params.get("document_id")
    doc_path = request.query_params.get("doc_path")
    if project:
        selected_audit = resolve_selected_audit(project.audits, nav.selected_audit_id)
        if document_id or doc_path:
            selected_audit = None
        linked_tasks = tasks_for_audit(project.all_tasks, selected_audit.audit_id) if selected_audit else ()
        context["audits"] = project.audits
        context["local_documents"] = project.local_documents
        context["selected_audit"] = selected_audit
        context["selected_document_id"] = document_id
        context["selected_doc_path"] = doc_path
        context["selected_document"] = None
        context["local_document_html"] = ""
        context["audit_html"] = (
            _render_project_markdown(selected_audit.content, project=project)
            if selected_audit
            else ""
        )
        context["linked_tasks"] = linked_tasks
        selected_document = None
        ctx = request.state.web_ctx
        repo_root, _node_home = content_repo_for_project(ctx.repo_root, ctx.node_home, project.project_id)
        if document_id:
            try:
                resolved = resolve_local_document(project=project, document_id=document_id, repo_root=repo_root)
                context["selected_document"] = resolved.document
                selected_document = resolved.document
                context["local_document_html"] = _render_project_markdown(
                    resolved.path.read_text(encoding="utf-8"),
                    project=project,
                    base_path=resolved.document.storage_path,
                )
            except (OSError, ValueError) as exc:
                context["document_error"] = str(exc)
            else:
                context["document_error"] = None
        elif doc_path:
            try:
                resolved_path = resolve_repo_markdown_path(repo_root=repo_root, doc_path=doc_path)
                storage_path = resolved_path.relative_to(repo_root.resolve()).as_posix()
                selected_document = LocalDocumentPreview(document_id=doc_path, storage_path=storage_path)
                context["selected_document"] = selected_document
                context["local_document_html"] = _render_project_markdown(
                    resolved_path.read_text(encoding="utf-8"),
                    project=project,
                    base_path=storage_path,
                )
                context["document_error"] = None
            except (OSError, ValueError) as exc:
                context["document_error"] = str(exc)
        else:
            context["document_error"] = None
        context["docs_detail_title"] = resolve_docs_detail_title(selected_audit, selected_document)
        if selected_audit:
            context["docs_detail_sections"] = build_audit_detail_sections(selected_audit, linked_tasks)
        elif selected_document:
            context["docs_detail_sections"] = build_document_detail_sections(
                selected_document,
                context.get("document_error"),
            )
        else:
            context["docs_detail_sections"] = ()
    else:
        context["audits"] = ()
        context["local_documents"] = ()
        context["selected_audit"] = None
        context["selected_document_id"] = None
        context["selected_doc_path"] = None
        context["selected_document"] = None
        context["local_document_html"] = ""
        context["audit_html"] = ""
        context["linked_tasks"] = ()
        context["document_error"] = None
        context["docs_detail_title"] = None
        context["docs_detail_sections"] = ()
    return request.state.templates.TemplateResponse(request, "docs.html", context)


@router.get("/project-page", response_class=HTMLResponse)
async def project_page_editor(request: Request) -> HTMLResponse:
    context = _common_context(request, "project_page")
    project = context["project"]
    page_type = request.query_params.get("page_type", "purpose")
    if page_type not in {"purpose", "architecture", "custom"}:
        page_type = "purpose"
    selected_page = None
    if project:
        selected_page = next((p for p in project.project_pages if p.page_type == page_type), None)
    context["page_type"] = page_type
    context["selected_page"] = selected_page
    context["page_content"] = selected_page.content if selected_page else ""
    context["page_title"] = selected_page.title if selected_page else PAGE_TYPE_TITLES.get(page_type, PAGE_TYPE_TITLES["custom"])
    return request.state.templates.TemplateResponse(request, "project_page_edit.html", context)
