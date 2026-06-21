from __future__ import annotations

from dataclasses import dataclass

from runtime.hub.data import AppSnapshot, AuditPreview, NavState, TaskPreview, resolve_nav_selection


@dataclass(frozen=True)
class PageHeader:
    breadcrumb: str
    title: str
    subtitle: str = ""


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
