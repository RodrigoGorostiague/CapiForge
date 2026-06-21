from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from runtime.hub.data import AppSnapshot, NavState, ViewName

NavNodeKind = Literal["action", "workspace", "project", "page"]


@dataclass(frozen=True)
class NavNode:
    node_id: str
    kind: NavNodeKind
    label: str
    depth: int
    workspace_id: str | None = None
    project_id: str | None = None
    view: ViewName | None = None
    expandable: bool = False
    expanded: bool = False


def build_nav_tree(snapshot: AppSnapshot, nav: NavState) -> list[NavNode]:
    nodes: list[NavNode] = [
        NavNode(node_id="action:new-workspace", kind="action", label="+ Nuevo workspace", depth=0),
    ]
    for workspace in snapshot.workspaces:
        workspace_expanded = workspace.workspace_id in nav.expanded_workspaces
        prefix = "▾ " if workspace_expanded else "▸ "
        nodes.append(
            NavNode(
                node_id=f"workspace:{workspace.workspace_id}",
                kind="workspace",
                label=f"{prefix}{workspace.name}",
                depth=0,
                workspace_id=workspace.workspace_id,
                expandable=True,
                expanded=workspace_expanded,
            )
        )
        if not workspace_expanded:
            continue
        for project in workspace.projects:
            project_expanded = project.project_id in nav.expanded_projects
            project_prefix = "▾ " if project_expanded else "▸ "
            nodes.append(
                NavNode(
                    node_id=f"project:{project.project_id}",
                    kind="project",
                    label=f"{project_prefix}{project.name}",
                    depth=1,
                    workspace_id=workspace.workspace_id,
                    project_id=project.project_id,
                    expandable=True,
                    expanded=project_expanded,
                )
            )
            if not project_expanded:
                continue
            for page_label, page_view in (
                ("Inicio", "project_home"),
                ("Tareas", "project_tasks"),
                ("Documentación", "project_docs"),
            ):
                nodes.append(
                    NavNode(
                        node_id=f"page:{project.project_id}:{page_view}",
                        kind="page",
                        label=page_label,
                        depth=2,
                        workspace_id=workspace.workspace_id,
                        project_id=project.project_id,
                        view=page_view,
                    )
                )
    return nodes


def active_nav_node_id(nav: NavState) -> str | None:
    if nav.view == "workspace_empty":
        if nav.project_id:
            return f"project:{nav.project_id}"
        if nav.workspace_id:
            return f"workspace:{nav.workspace_id}"
        return None
    if nav.project_id and nav.view:
        return f"page:{nav.project_id}:{nav.view}"
    return None


def nav_state_for_node(node: NavNode, nav: NavState) -> NavState:
    if node.kind == "action":
        return NavState(view="workspace_empty")
    if node.kind == "workspace":
        expanded = set(nav.expanded_workspaces)
        if node.workspace_id:
            if node.workspace_id in expanded:
                expanded.remove(node.workspace_id)
            else:
                expanded.add(node.workspace_id)
        return NavState(
            workspace_id=node.workspace_id,
            project_id=None,
            view="workspace_empty",
            expanded_workspaces=frozenset(expanded),
            expanded_projects=nav.expanded_projects,
            task_filter=nav.task_filter,
        )
    if node.kind == "project":
        expanded = set(nav.expanded_projects)
        if node.project_id:
            if node.project_id in expanded:
                expanded.remove(node.project_id)
            else:
                expanded.add(node.project_id)
        return NavState(
            workspace_id=node.workspace_id,
            project_id=node.project_id,
            view="project_home",
            expanded_workspaces=nav.expanded_workspaces,
            expanded_projects=frozenset(expanded),
            task_filter=nav.task_filter,
        )
    return NavState(
        workspace_id=node.workspace_id,
        project_id=node.project_id,
        view=node.view or "project_home",
        expanded_workspaces=nav.expanded_workspaces | ({node.workspace_id} if node.workspace_id else set()),
        expanded_projects=nav.expanded_projects | ({node.project_id} if node.project_id else set()),
        task_filter=nav.task_filter,
    )


def toggle_expand_for_focused_node(nodes: list[NavNode], focused_index: int, nav: NavState) -> NavState:
    if focused_index < 0 or focused_index >= len(nodes):
        return nav
    node = nodes[focused_index]
    if not node.expandable:
        return nav_state_for_node(node, nav)
    if node.kind == "workspace" and node.workspace_id:
        expanded = set(nav.expanded_workspaces)
        if node.workspace_id in expanded:
            expanded.remove(node.workspace_id)
        else:
            expanded.add(node.workspace_id)
        return NavState(
            workspace_id=node.workspace_id,
            project_id=nav.project_id,
            view=nav.view,
            selected_task_id=nav.selected_task_id,
            selected_audit_id=nav.selected_audit_id,
            task_filter=nav.task_filter,
            expanded_workspaces=frozenset(expanded),
            expanded_projects=nav.expanded_projects,
        )
    if node.kind == "project" and node.project_id:
        expanded = set(nav.expanded_projects)
        if node.project_id in expanded:
            expanded.remove(node.project_id)
        else:
            expanded.add(node.project_id)
        return NavState(
            workspace_id=node.workspace_id or nav.workspace_id,
            project_id=node.project_id,
            view=nav.view,
            selected_task_id=nav.selected_task_id,
            selected_audit_id=nav.selected_audit_id,
            task_filter=nav.task_filter,
            expanded_workspaces=nav.expanded_workspaces,
            expanded_projects=frozenset(expanded),
        )
    return nav
