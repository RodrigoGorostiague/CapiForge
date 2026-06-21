from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from uuid import uuid4

from runtime.coordinator.claims import ClaimRegistry
from runtime.node.bootstrap import NodeBootstrap
from runtime.node.current import _build_local_actor, resolve_as_of, resolve_lease_window
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity, canonical_id
from runtime.tui.data import LOCAL_AGENT_ID, LOCAL_SESSION_ID, slugify_name
from runtime.tui.task_fields import TASK_FIELD_DB_COLUMN, TASK_FIELD_OPTIONS

LOCK_TIMEOUT_SECONDS = 30.0
WEB_AGENT_ID = "capiforge-web"
WEB_SESSION_ID = "capiforge-web-session"


@dataclass(frozen=True)
class ActionResult:
    ok: bool
    message: str


def _with_surface(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    command: str,
    callback: Callable[[NodeBootstrap, NodeStore, NodeMCPSurface, ActorIdentity, str], ActionResult],
    agent_id: str = LOCAL_AGENT_ID,
    session_id: str = LOCAL_SESSION_ID,
) -> ActionResult:
    bootstrap = NodeBootstrap(repo_root=repo_root, node_home=node_home)
    resolved_as_of = resolve_as_of(None)
    try:
        with bootstrap.bootstrap_session(
            command=command,
            timeout=LOCK_TIMEOUT_SECONDS,
            interactive=False,
            verbose=False,
            recover_stale_lock=False,
        ):
            state = bootstrap._status_unlocked()
            if state.state == "uninitialized":
                state = bootstrap._open_or_init_unlocked()
            node_db_path = state.node_db_path
            store = NodeStore.from_file(node_db_path)
            try:
                actor = _build_local_actor(store, state, agent_id=agent_id, session_id=session_id)
                surface = NodeMCPSurface(
                    store=store,
                    router=NodeRouter(store),
                    claims=ClaimRegistry(store.db),
                    local_node_id=state.local_node_id,
                )
                result = callback(bootstrap, store, surface, actor, resolved_as_of)
                if result.ok:
                    store.db.commit()
                    from runtime.events.notify import notify_local_write

                    notify_local_write(node_db_path)
                return result
            finally:
                store.close()
    except SurfaceError as exc:
        return ActionResult(ok=False, message=f"{exc.code}: {exc.message}")
    except Exception as exc:
        return ActionResult(ok=False, message=str(exc))


def create_workspace(*, repo_root: str | Path, node_home: str | Path | None, name: str, canonical_link: str | None = None) -> ActionResult:
    cleaned_name = name.strip()
    if not cleaned_name:
        return ActionResult(ok=False, message="Workspace name is required.")
    link = canonical_link.strip() if canonical_link else f"workspace://{slugify_name(cleaned_name)}"
    workspace_id = canonical_id("workspace", link)

    def _callback(_bootstrap, store, _surface, _actor, _as_of) -> ActionResult:
        if store.get_workspace(workspace_id):
            return ActionResult(ok=False, message="Workspace already exists.")
        store.create_workspace(workspace_id, link, cleaned_name)
        return ActionResult(ok=True, message=f"Workspace '{cleaned_name}' created.")

    return _with_surface(repo_root=repo_root, node_home=node_home, command="tui_create_workspace", callback=_callback)


def create_project(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    workspace_id: str,
    name: str,
    canonical_link: str | None = None,
) -> ActionResult:
    cleaned_name = name.strip()
    if not cleaned_name:
        return ActionResult(ok=False, message="Project name is required.")
    link = canonical_link.strip() if canonical_link else f"project://{slugify_name(cleaned_name)}"
    project_id = canonical_id("project", link)

    def _callback(_bootstrap, store, _surface, _actor, _as_of) -> ActionResult:
        if not store.get_workspace(workspace_id):
            return ActionResult(ok=False, message="Workspace not found.")
        if store.get_project(project_id):
            return ActionResult(ok=False, message="Project already exists.")
        store.upsert_project(project_id, workspace_id, _actor.node_id, link, cleaned_name)
        return ActionResult(ok=True, message=f"Project '{cleaned_name}' created.")

    return _with_surface(repo_root=repo_root, node_home=node_home, command="tui_create_project", callback=_callback)


def _resolve_published_audit_id(store: NodeStore, project_id: str, audit_id: str | None = None) -> str | None:
    if audit_id:
        audit = store.get_audit(audit_id)
        if audit and audit["project_id"] == project_id and audit["state"] == "published":
            return audit_id
        return None
    for audit in store.list_project_audits(project_id):
        if audit["state"] == "published":
            return audit["audit_id"]
    return None


def create_task(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    project_id: str,
    description: str,
    priority: str = "medium",
    task_type: str = "feature",
    initial_state: str = "ready",
    audit_id: str | None = None,
) -> ActionResult:
    cleaned_description = description.strip()
    if not cleaned_description:
        return ActionResult(ok=False, message="Task description is required.")

    def _callback(_bootstrap, store, surface, actor, _as_of) -> ActionResult:
        if not store.get_project(project_id):
            return ActionResult(ok=False, message="Project not found.")
        resolved_audit_id = _resolve_published_audit_id(store, project_id, audit_id)
        if not resolved_audit_id:
            return ActionResult(ok=False, message="Publish an audit before creating tasks.")
        task_id = f"tsk_tui_{uuid4().hex[:12]}"
        mutation_id = f"mut_tui_{uuid4().hex[:12]}"
        surface.tasks_create_from_audit(
            task_id=task_id,
            project_id=project_id,
            audit_id=resolved_audit_id,
            mutation_id=mutation_id,
            actor=actor,
            priority=priority,
            effort="medium",
            risk="low",
            task_type=task_type,
            description=cleaned_description,
            justification=_default_justification(f"Create task from TUI: {cleaned_description}"),
            execution_context={"source": "tui"},
            initial_state=initial_state,
        )
        return ActionResult(ok=True, message=f"Task '{cleaned_description}' created.")

    return _with_surface(repo_root=repo_root, node_home=node_home, command="tui_create_task", callback=_callback)


def _default_justification(summary: str) -> JustificationPayload:
    return JustificationPayload(
        summary=summary,
        evidence_refs=("tui://action",),
        expected_impact="Advance task lifecycle from the TUI",
    )


def claim_task(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    project_id: str,
    task_id: str,
    plan: str = "Claimed from TUI",
    agent_id: str = LOCAL_AGENT_ID,
    session_id: str = LOCAL_SESSION_ID,
) -> ActionResult:
    lease_started_at, lease_expires_at = resolve_lease_window(lease_minutes=30)

    def _callback(_bootstrap, store, surface, actor, _as_of) -> ActionResult:
        claim_id = canonical_id("claim", project_id, task_id, actor.session_id, lease_started_at, plan)
        surface.tasks_claim(
            claim_id=claim_id,
            project_id=project_id,
            task_id=task_id,
            actor=actor,
            plan=plan,
            lease_started_at=lease_started_at,
            lease_expires_at=lease_expires_at,
        )
        return ActionResult(ok=True, message="Task claimed.")

    return _with_surface(
        repo_root=repo_root,
        node_home=node_home,
        command="tui_claim",
        callback=_callback,
        agent_id=agent_id,
        session_id=session_id,
    )


def release_task(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    project_id: str,
    task_id: str,
    agent_id: str = LOCAL_AGENT_ID,
    session_id: str = LOCAL_SESSION_ID,
) -> ActionResult:
    def _callback(_bootstrap, store, surface, actor, as_of) -> ActionResult:
        if not surface.claims:
            return ActionResult(ok=False, message="Claim registry unavailable.")
        active = surface.claims.get_active_claim(project_id=project_id, task_id=task_id, as_of=as_of)
        if not active:
            return ActionResult(ok=False, message="No active claim for this task.")
        surface.tasks_release(project_id=project_id, task_id=task_id, claim_id=active.claim_id, actor=actor)
        return ActionResult(ok=True, message="Claim released.")

    return _with_surface(
        repo_root=repo_root,
        node_home=node_home,
        command="tui_release",
        callback=_callback,
        agent_id=agent_id,
        session_id=session_id,
    )


def transition_task(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    project_id: str,
    task_id: str,
    requested_state: str,
    metadata: dict | None = None,
    justification: JustificationPayload | None = None,
    agent_id: str = LOCAL_AGENT_ID,
    session_id: str = LOCAL_SESSION_ID,
) -> ActionResult:
    resolved_metadata = dict(metadata or {})
    resolved_justification = justification or _default_justification(f"Transition to {requested_state}")

    def _callback(_bootstrap, store, surface, actor, as_of) -> ActionResult:
        resolved_metadata.setdefault("active_claim_session_id", actor.session_id)
        resolved_metadata.setdefault("as_of", as_of)
        if requested_state == "blocked":
            resolved_metadata.setdefault("blocked_reason", "Blocked from TUI")
            resolved_metadata.setdefault("blocked_evidence", "tui://blocked")
            resolved_metadata.setdefault("blocked_next_step", "Unblock when ready")
        if requested_state == "done":
            resolved_metadata.setdefault("done_result", "Completed from TUI")
            resolved_metadata.setdefault("done_artifacts", "tui://done")
            resolved_metadata.setdefault("done_references", "tui://done")
            resolved_metadata.setdefault("done_expected_impact", "Task completed via TUI")
        mutation_id = f"mut_tui_{uuid4().hex[:12]}"
        surface.tasks_transition(
            project_id=project_id,
            task_id=task_id,
            mutation_id=mutation_id,
            actor=actor,
            requested_state=requested_state,
            justification=resolved_justification,
            metadata=resolved_metadata,
        )
        return ActionResult(ok=True, message=f"Task moved to {requested_state.replace('_', ' ')}.")

    return _with_surface(
        repo_root=repo_root,
        node_home=node_home,
        command="tui_transition",
        callback=_callback,
        agent_id=agent_id,
        session_id=session_id,
    )


def update_task_attribute(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    project_id: str,
    task_id: str,
    field: str,
    value: str,
    agent_id: str = LOCAL_AGENT_ID,
    session_id: str = LOCAL_SESSION_ID,
) -> ActionResult:
    options = TASK_FIELD_OPTIONS.get(field)
    if options is None or value not in options:
        return ActionResult(ok=False, message="Invalid task field or value.")

    if field == "state":
        if value in {"claimed", "in_progress"}:
            return ActionResult(ok=False, message="Use Claim or Start for that state.")
        return transition_task(
            repo_root=repo_root,
            node_home=node_home,
            project_id=project_id,
            task_id=task_id,
            requested_state=value,
            agent_id=agent_id,
            session_id=session_id,
        )

    column = TASK_FIELD_DB_COLUMN.get(field)
    if column is None:
        return ActionResult(ok=False, message="Invalid task field.")

    def _callback(_bootstrap, store, _surface, _actor, _as_of) -> ActionResult:
        if not store.task_belongs_to_project(task_id, project_id):
            return ActionResult(ok=False, message="Task not found in project.")
        attr_kwargs = {"task_type": value} if field == "task_type" else {field: value}
        store.update_task_attribute(task_id, **attr_kwargs)
        return ActionResult(ok=True, message=f"Updated {field.replace('_', ' ')}.")

    return _with_surface(
        repo_root=repo_root,
        node_home=node_home,
        command="tui_update_task_attribute",
        callback=_callback,
        agent_id=agent_id,
        session_id=session_id,
    )


def upsert_project_page(
    *,
    repo_root: str | Path,
    node_home: str | Path | None,
    project_id: str,
    page_type: str,
    title: str,
    content: str,
    agent_id: str = WEB_AGENT_ID,
    session_id: str = WEB_SESSION_ID,
) -> ActionResult:
    if page_type not in {"purpose", "architecture", "custom"}:
        return ActionResult(ok=False, message="Invalid page type.")

    def _callback(_bootstrap, store, _surface, _actor, as_of) -> ActionResult:
        project = store.get_project(project_id)
        if not project:
            return ActionResult(ok=False, message="Project not found.")
        page_id = canonical_id("page", project_id, page_type)
        store.upsert_project_page(
            page_id=page_id,
            project_id=project_id,
            page_type=page_type,
            title=title.strip() or page_type.title(),
            content=content,
            updated_at=as_of,
        )
        store.db.commit()
        return ActionResult(ok=True, message="Project page saved.")

    return _with_surface(
        repo_root=repo_root,
        node_home=node_home,
        command="web_upsert_project_page",
        callback=_callback,
        agent_id=agent_id,
        session_id=session_id,
    )
