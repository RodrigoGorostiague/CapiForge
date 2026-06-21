from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.ids import ActorIdentity
from runtime.tui.actions import ActionResult, WEB_AGENT_ID, WEB_SESSION_ID, _with_surface
from runtime.tui.data import LOCAL_AGENT_ID, LOCAL_SESSION_ID, load_home_snapshot, load_project_snapshot, resolve_as_of
from runtime.web.project_registry import save_registry_entry


def bootstrap_folder_repo(folder_path: Path) -> tuple[ActionResult, dict | None]:
    target = folder_path.resolve()
    if not target.exists():
        return ActionResult(ok=False, message="La carpeta no existe."), None
    if not target.is_dir():
        return ActionResult(ok=False, message="La ruta no es una carpeta."), None

    bootstrap = NodeBootstrap(repo_root=target)
    try:
        state = bootstrap.open_or_init(interactive=False)
        if state.state == "uninitialized":
            return ActionResult(ok=False, message="No se pudo inicializar CapiForge en la carpeta."), None
        if state.state == "initialized":
            state = bootstrap.adopt_repo(interactive=False)
        if state.state != "adopted" or not state.adopted_project:
            return ActionResult(ok=False, message="No se pudo adoptar la carpeta."), None
        return ActionResult(ok=True, message="Carpeta adoptada."), state.adopted_project
    except Exception as exc:
        return ActionResult(ok=False, message=str(exc)), None


def adopt_folder_as_project(
    *,
    hub_repo_root: str | Path,
    hub_node_home: str | Path | None,
    folder_path: str,
    workspace_id: str,
) -> tuple[ActionResult, str | None]:
    folder = Path(folder_path.strip()).expanduser()
    hub_root = Path(hub_repo_root).resolve()
    if folder.resolve() == hub_root:
        return ActionResult(ok=False, message="Este repositorio ya es el proyecto principal."), None

    bootstrap_result, metadata = bootstrap_folder_repo(folder)
    if not bootstrap_result.ok or metadata is None:
        return bootstrap_result, None

    project_id = metadata["project_id"]
    project_name = metadata.get("project_name") or folder.name
    target_bootstrap = NodeBootstrap(repo_root=folder)

    def _callback(_bootstrap, store, _surface, actor, _as_of) -> ActionResult:
        if not store.get_workspace(workspace_id):
            return ActionResult(ok=False, message="Workspace no encontrado.")
        existing = store.get_project(project_id)
        if existing and existing["workspace_id"] != workspace_id:
            return ActionResult(ok=False, message="El proyecto ya existe en otro workspace.")
        store.upsert_project(
            project_id,
            workspace_id,
            actor.node_id,
            metadata.get("project_canonical_link") or f"file://{folder.as_posix()}",
            project_name,
        )
        save_registry_entry(
            Path(hub_repo_root),
            project_id=project_id,
            repo_root=folder,
            node_home=target_bootstrap.node_home,
            project_name=project_name,
        )
        return ActionResult(ok=True, message=f"Proyecto '{project_name}' añadido.")

    hub_result = _with_surface(
        repo_root=hub_repo_root,
        node_home=hub_node_home,
        command="web_adopt_folder",
        callback=_callback,
        agent_id=WEB_AGENT_ID,
        session_id=WEB_SESSION_ID,
    )
    if not hub_result.ok:
        return hub_result, None
    return ActionResult(ok=True, message=f"Proyecto '{project_name}' listo en {folder}."), project_id


def load_web_snapshot(
    *,
    hub_repo_root: Path,
    hub_node_home: Path | None,
    as_of: str | None = None,
) -> "AppSnapshot":
    from runtime.tui.data import AppSnapshot

    resolved_as_of = resolve_as_of(as_of)
    snapshot = load_home_snapshot(repo_root=hub_repo_root, node_home=hub_node_home, as_of=resolved_as_of)
    if not snapshot.workspaces:
        return snapshot

    from runtime.web.project_registry import load_registry

    registry = load_registry(hub_repo_root)
    if not registry:
        return snapshot

    workspaces = []
    for workspace in snapshot.workspaces:
        projects = []
        for project in workspace.projects:
            registered = registry.get(project.project_id)
            if registered is None:
                projects.append(project)
                continue
            external = _load_registered_project(registered, as_of=resolved_as_of)
            projects.append(external if external is not None else project)
        workspaces.append(replace(workspace, projects=tuple(projects)))
    snapshot.workspaces = tuple(workspaces)
    return snapshot


def _load_registered_project(registered, *, as_of: str):
    from runtime.tui.data import ProjectSnapshot

    bootstrap = NodeBootstrap(repo_root=registered.repo_root, node_home=registered.node_home)
    try:
        state = bootstrap.status(interactive=False)
    except Exception:
        return None
    if state.state != "adopted":
        return None

    store = NodeStore.from_file(state.node_db_path)
    workspace_id = ""
    try:
        project = store.get_project(registered.project_id)
        if not project:
            return None
        workspace_id = project["workspace_id"]
        surface = NodeMCPSurface(store=store, router=NodeRouter(store), local_node_id=state.local_node_id)
        actor = ActorIdentity(node_id=state.local_node_id, agent_id=LOCAL_AGENT_ID, session_id=LOCAL_SESSION_ID)
        return load_project_snapshot(
            store=store,
            surface=surface,
            actor=actor,
            as_of=as_of,
            workspace_id=workspace_id,
            project=project,
        )
    except Exception:
        return ProjectSnapshot(
            project_id=registered.project_id,
            workspace_id=workspace_id,
            name=registered.project_name,
            canonical_link=f"file://{registered.repo_root.as_posix()}",
        )
    finally:
        store.close()
