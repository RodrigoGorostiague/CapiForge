from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import urlencode

from fastapi import Request

from runtime.tui.data import AppSnapshot, NavState, ViewName, default_nav_state, load_home_snapshot
from runtime.tui.nav import build_nav_tree

ViewRoute = Literal["home", "tasks", "docs", "project_page"]

PRESERVED_QUERY_KEYS = (
    "expanded_ws",
    "expanded_proj",
    "filter",
    "page",
    "sort",
    "sort_dir",
    "task_id",
    "audit_id",
)


@dataclass(frozen=True)
class WebContext:
    repo_root: Path
    node_home: Path | None
    as_of: str | None
    refresh_seconds: int
    realtime_enabled: bool = True


def load_snapshot(ctx: WebContext) -> AppSnapshot:
    from runtime.web.adopt_folder import load_web_snapshot

    return load_web_snapshot(
        hub_repo_root=ctx.repo_root,
        hub_node_home=ctx.node_home,
        as_of=ctx.as_of,
    )


def view_route_to_name(route: ViewRoute) -> ViewName:
    return {
        "home": "project_home",
        "tasks": "project_tasks",
        "docs": "project_docs",
    }[route]


def _parse_expanded_set(raw: str | None) -> frozenset[str]:
    if raw is None:
        return frozenset()
    return frozenset(part.strip() for part in raw.split(",") if part.strip())


def toggle_workspace_expansion(nav: NavState, workspace_id: str) -> NavState:
    expanded = set(nav.expanded_workspaces)
    if workspace_id in expanded:
        expanded.discard(workspace_id)
    else:
        expanded.add(workspace_id)
    return replace(nav, expanded_workspaces=frozenset(expanded))


def toggle_project_expansion(nav: NavState, project_id: str) -> NavState:
    expanded = set(nav.expanded_projects)
    if project_id in expanded:
        expanded.discard(project_id)
    else:
        expanded.add(project_id)
    return replace(nav, expanded_projects=frozenset(expanded))


def nav_expansion_params(nav: NavState) -> dict[str, str]:
    return {
        "expanded_ws": ",".join(sorted(nav.expanded_workspaces)),
        "expanded_proj": ",".join(sorted(nav.expanded_projects)),
    }


def preserved_query_params(request: Request | None) -> dict[str, str]:
    if request is None:
        return {}
    params: dict[str, str] = {}
    for key in PRESERVED_QUERY_KEYS:
        if key in request.query_params:
            params[key] = request.query_params.get(key, "")
    return params


def build_nav_url(path: str, nav: NavState, request: Request | None = None, **overrides: str | None) -> str:
    params: dict[str, str] = {}
    if request is not None:
        params.update(preserved_query_params(request))
    if nav.workspace_id:
        params["workspace_id"] = nav.workspace_id
    if nav.project_id:
        params["project_id"] = nav.project_id
    params.update(nav_expansion_params(nav))
    for key, value in overrides.items():
        if value is None:
            params.pop(key, None)
        else:
            params[key] = value
    query = urlencode(params)
    return f"{path}?{query}" if query else path


def nav_from_query(
    snapshot: AppSnapshot,
    *,
    workspace_id: str | None,
    project_id: str | None,
    route: ViewRoute,
    task_filter: str = "all",
    selected_task_id: str | None = None,
    selected_audit_id: str | None = None,
    expanded_ws: str | None = None,
    expanded_proj: str | None = None,
    has_expanded_ws: bool = False,
    has_expanded_proj: bool = False,
) -> NavState:
    base = default_nav_state(snapshot)
    expanded_workspaces = _parse_expanded_set(expanded_ws) if has_expanded_ws else base.expanded_workspaces
    expanded_projects = _parse_expanded_set(expanded_proj) if has_expanded_proj else base.expanded_projects
    return NavState(
        workspace_id=workspace_id or base.workspace_id,
        project_id=project_id or base.project_id,
        view=view_route_to_name(route),
        selected_task_id=selected_task_id,
        selected_audit_id=selected_audit_id,
        task_filter=task_filter,
        expanded_workspaces=expanded_workspaces,
        expanded_projects=expanded_projects,
    )


ROUTE_PATHS: dict[str, str] = {
    "home": "/",
    "tasks": "/tasks",
    "docs": "/docs",
}


def page_path(route: str) -> str:
    return ROUTE_PATHS.get(route, f"/{route}")


def _clean_nav_label(label: str) -> str:
    if label.startswith("▾ ") or label.startswith("▸ "):
        return label[2:]
    return label


def sidebar_nav(snapshot: AppSnapshot, nav: NavState, *, request: Request, route: ViewRoute) -> list[dict]:
    current_path = page_path(route)
    nodes = build_nav_tree(snapshot, nav)
    items: list[dict] = []
    for node in nodes:
        if node.kind == "action":
            continue
        if node.kind == "page" and node.view:
            page_route = {
                "project_home": "home",
                "project_tasks": "tasks",
                "project_docs": "docs",
            }.get(node.view)
            if page_route:
                items.append(
                    {
                        "label": node.label,
                        "page_path": page_path(page_route),
                        "url": build_nav_url(
                            page_path(page_route),
                            nav,
                            request,
                            workspace_id=node.workspace_id or "",
                            project_id=node.project_id or "",
                        ),
                        "depth": node.depth,
                        "workspace_id": node.workspace_id,
                        "project_id": node.project_id,
                        "active": nav.view == node.view and nav.project_id == node.project_id,
                        "kind": "page",
                    }
                )
        elif node.kind == "workspace" and node.workspace_id:
            toggled = toggle_workspace_expansion(nav, node.workspace_id)
            items.append(
                {
                    "label": _clean_nav_label(node.label),
                    "url": build_nav_url(current_path, toggled, request),
                    "depth": node.depth,
                    "workspace_id": node.workspace_id,
                    "project_id": None,
                    "active": False,
                    "expanded": node.expanded,
                    "kind": "workspace",
                }
            )
        elif node.kind == "project" and node.project_id:
            toggled = toggle_project_expansion(nav, node.project_id)
            items.append(
                {
                    "label": _clean_nav_label(node.label),
                    "url": build_nav_url(current_path, toggled, request),
                    "depth": node.depth,
                    "workspace_id": node.workspace_id,
                    "project_id": node.project_id,
                    "active": False,
                    "expanded": node.expanded,
                    "kind": "project",
                }
            )
    workspace_id = nav.workspace_id
    if not workspace_id and snapshot.workspaces:
        workspace_id = snapshot.workspaces[0].workspace_id
    if workspace_id:
        items.append(
            {
                "kind": "add_project",
                "label": "+ Añadir proyecto",
                "depth": 1,
                "workspace_id": workspace_id,
            }
        )
    return items
