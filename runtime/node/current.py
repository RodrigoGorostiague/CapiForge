from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from uuid import NAMESPACE_URL, uuid5
from typing import Any, Callable

from runtime.coordinator.claims import ClaimRegistry
from runtime.node.bootstrap import BootstrapState, NodeBootstrap
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity, canonical_id, derive_node_proof


def resolve_as_of(raw: str | None) -> str:
    if raw:
        return raw
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def state_payload(state: BootstrapState) -> dict[str, Any]:
    return {
        "bootstrap_state": state.state,
        "local_node_id": state.local_node_id,
        "node_home": state.node_home,
        "node_db_path": state.node_db_path,
        "adopted_project": state.adopted_project,
    }


def resolve_lease_window(*, lease_minutes: int, started_at: str | None = None) -> tuple[str, str]:
    started = datetime.fromisoformat(started_at.replace("Z", "+00:00")) if started_at else datetime.now(timezone.utc)
    started = started.astimezone(timezone.utc).replace(microsecond=0)
    expires = started + timedelta(minutes=lease_minutes)
    return (
        started.isoformat().replace("+00:00", "Z"),
        expires.isoformat().replace("+00:00", "Z"),
    )


def _build_local_actor(store: NodeStore, state: BootstrapState, *, agent_id: str, session_id: str) -> ActorIdentity:
    invitation_fingerprint = store.ensure_local_node_actor(node_id=state.local_node_id)
    return ActorIdentity(
        node_id=state.local_node_id,
        agent_id=agent_id,
        session_id=session_id,
        node_proof=derive_node_proof(
            node_id=state.local_node_id,
            agent_id=agent_id,
            session_id=session_id,
            invitation_fingerprint=invitation_fingerprint,
        ),
    )


def _with_adopted_surface(
    bootstrap: NodeBootstrap,
    *,
    as_of: str | None,
    lock_timeout_seconds: float,
    recover_stale_lock: bool,
    agent_id: str,
    session_id: str,
    command: str,
    wait_reporter: Callable[[str, dict[str, Any]], None] | None,
    reader: Callable[[BootstrapState, NodeStore, NodeMCPSurface, ActorIdentity, str], dict[str, Any]],
) -> dict[str, Any]:
    resolved_as_of = resolve_as_of(as_of)
    with bootstrap.bootstrap_session(
        command=command,
        timeout=lock_timeout_seconds,
        interactive=False,
        verbose=False,
        recover_stale_lock=recover_stale_lock,
        wait_reporter=wait_reporter,
    ):
        state, store = bootstrap._open_adopted_store_unlocked()
        try:
            actor = _build_local_actor(store, state, agent_id=agent_id, session_id=session_id)
            surface = NodeMCPSurface(
                store=store,
                router=NodeRouter(store),
                claims=ClaimRegistry(store.db),
                local_node_id=state.local_node_id,
            )
            return reader(state, store, surface, actor, resolved_as_of)
        finally:
            store.close()


def _require_text(value: str | None, *, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SurfaceError("INVALID_ARGUMENTS", f"{field_name} must be a non-empty string")
    return value.strip()


def _coerce_justification(payload: JustificationPayload | dict[str, Any] | None) -> JustificationPayload:
    if isinstance(payload, JustificationPayload):
        return payload
    if not isinstance(payload, dict):
        raise SurfaceError(
            "INVALID_ARGUMENTS",
            "justification must be a JustificationPayload or dict with summary, evidence_refs, and expected_impact",
        )
    evidence_refs = payload.get("evidence_refs")
    if isinstance(evidence_refs, str):
        evidence_refs = (evidence_refs,)
    elif isinstance(evidence_refs, list):
        evidence_refs = tuple(evidence_refs)
    if not isinstance(evidence_refs, tuple):
        raise SurfaceError("INVALID_ARGUMENTS", "justification.evidence_refs must be a string or list/tuple of strings")
    return JustificationPayload(
        summary=str(payload.get("summary", "")),
        evidence_refs=tuple(str(ref) for ref in evidence_refs),
        expected_impact=str(payload.get("expected_impact", "")),
    )


def _lifecycle_justification(*, lifecycle_key: str, plan: str) -> JustificationPayload:
    return JustificationPayload(
        summary=plan,
        evidence_refs=(lifecycle_key,),
        expected_impact="Move the lifecycle task into active same-project execution",
    )


def _lifecycle_finish_justification(*, lifecycle_key: str, outcome: str) -> JustificationPayload:
    return JustificationPayload(
        summary=f"Close lifecycle work as {outcome}",
        evidence_refs=(lifecycle_key,),
        expected_impact="Record a deterministic same-project lifecycle closeout",
    )


def _require_create_seed(
    *,
    origin_audit_id: str | None,
    description: str | None,
    priority: str | None,
    effort: str | None,
    risk: str | None,
    task_type: str | None,
    justification: JustificationPayload | dict[str, Any] | None,
    execution_context: dict[str, Any] | None,
) -> tuple[str, str, str, str, str, JustificationPayload, dict[str, Any]]:
    missing: list[str] = []
    if not isinstance(origin_audit_id, str) or not origin_audit_id.strip():
        missing.append("origin_audit_id")
    if not isinstance(description, str) or not description.strip():
        missing.append("description")
    if not isinstance(priority, str) or not priority.strip():
        missing.append("priority")
    if not isinstance(effort, str) or not effort.strip():
        missing.append("effort")
    if not isinstance(risk, str) or not risk.strip():
        missing.append("risk")
    if not isinstance(task_type, str) or not task_type.strip():
        missing.append("task_type")
    if justification is None:
        missing.append("justification")
    if execution_context is None:
        missing.append("execution_context")
    if missing:
        joined = ", ".join(missing)
        raise SurfaceError("INVALID_ARGUMENTS", f"lifecycle create requires: {joined}")
    if not isinstance(execution_context, dict):
        raise SurfaceError("INVALID_ARGUMENTS", "execution_context must be an object")
    return (
        origin_audit_id.strip(),
        description.strip(),
        priority.strip(),
        effort.strip(),
        risk.strip(),
        _coerce_justification(justification),
        deepcopy(execution_context),
    )


def _validate_same_project_context(*, project_id: str, execution_context: dict[str, Any]) -> dict[str, Any]:
    for field in ("project_id", "source_project_id"):
        value = execution_context.get(field)
        if value is not None and value != project_id:
            raise SurfaceError("INVALID_TASK_STATE", f"lifecycle execution_context.{field} must stay within the adopted project")
    return execution_context


def _require_published_origin_audit(*, store: NodeStore, project_id: str, audit_id: str) -> dict[str, Any]:
    audit = store.get_audit(audit_id)
    if not audit or audit["project_id"] != project_id:
        raise SurfaceError("INVALID_TASK_STATE", "lifecycle origin audit must stay within the adopted project")
    if audit["state"] != "published":
        raise SurfaceError("INVALID_TASK_STATE", "lifecycle create requires a published origin audit")
    return audit


def _mutation_id(*parts: str) -> str:
    digest = uuid5(NAMESPACE_URL, ":".join(parts)).hex[:16]
    return f"mut_{digest}"


def _require_finish_metadata(
    *,
    outcome: str,
    done_result: str | None,
    done_artifacts: str | None,
    done_references: str | None,
    done_expected_impact: str | None,
    blocked_reason: str | None,
    blocked_evidence: str | None,
    blocked_next_step: str | None,
) -> dict[str, str]:
    if outcome == "done":
        payload = {
            "done_result": done_result,
            "done_artifacts": done_artifacts,
            "done_references": done_references,
            "done_expected_impact": done_expected_impact,
        }
    elif outcome == "blocked":
        payload = {
            "blocked_reason": blocked_reason,
            "blocked_evidence": blocked_evidence,
            "blocked_next_step": blocked_next_step,
        }
    else:
        raise SurfaceError("INVALID_ARGUMENTS", "outcome must be 'done' or 'blocked'")
    missing = [field_name for field_name, value in payload.items() if not isinstance(value, str) or not value.strip()]
    if missing:
        raise SurfaceError("INVALID_ARGUMENTS", f"lifecycle finish requires: {', '.join(missing)}")
    return {field_name: value.strip() for field_name, value in payload.items()}


def _raise_finish_claim_error(*, store: NodeStore, task_id: str, session_id: str, as_of: str) -> None:
    cached_claim = store.get_cached_claim(task_id)
    if cached_claim and cached_claim["holder_session_id"] == session_id:
        if cached_claim["status"] == "expired" or cached_claim["lease_expires_at"] <= as_of:
            raise SurfaceError("CLAIM_EXPIRED", "lifecycle finish requires an active claim; reconcile-start again after lease expiry")
        if cached_claim["status"] == "released":
            raise SurfaceError("INVALID_TASK_STATE", "lifecycle finish requires an active claim; reconcile-start again after the claim was released")
    raise SurfaceError("INVALID_TASK_STATE", "lifecycle finish requires a matching active claim")


def _prepare_reusable_task(
    *,
    surface: NodeMCPSurface,
    store: NodeStore,
    project_id: str,
    task: dict[str, Any],
    actor: ActorIdentity,
    lifecycle_key: str,
    plan: str,
    as_of: str,
) -> tuple[dict[str, Any], str | None]:
    task_id = task["task_id"]
    if task["state"] in {"claimed", "in_progress"}:
        surface._sync_active_claim_state(project_id=project_id, task_id=task_id, as_of=as_of, expected_session_id=actor.session_id)
        task = store.get_task(task_id)
    if task["state"] == "blocked":
        surface.tasks_transition(
            project_id=project_id,
            task_id=task_id,
            mutation_id=_mutation_id("lifecycle", "resume", task_id, actor.session_id, as_of),
            actor=actor,
            requested_state="ready",
            justification=_lifecycle_justification(lifecycle_key=lifecycle_key, plan=plan),
            metadata={"conflict_status": "clear"},
        )
        task = store.get_task(task_id)
    if task["state"] == "ready":
        return task, None
    if task["state"] in {"claimed", "in_progress"}:
        active_claim = surface.claims.get_active_claim(project_id=project_id, task_id=task_id, as_of=as_of) if surface.claims else None
        if not active_claim or active_claim.session_id != actor.session_id:
            raise SurfaceError("CLAIM_CONFLICT", "lifecycle task already has an active claim owned by another session")
        return task, active_claim.claim_id
    raise SurfaceError(
        "INVALID_TASK_STATE",
        f"lifecycle task {task_id} is not reusable from state {task['state']}",
    )


def read_ready_tasks(
    bootstrap: NodeBootstrap,
    *,
    as_of: str | None,
    limit: int,
    lock_timeout_seconds: float,
    recover_stale_lock: bool,
    agent_id: str,
    session_id: str,
    command: str = "tasks_ready",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, resolved_as_of: str) -> dict[str, Any]:
        del store
        project_id = state.adopted_project["project_id"]
        ready_tasks = surface.tasks_list_by_index(
            project_id=project_id,
            index_name="ready",
            as_of=resolved_as_of,
            limit=limit,
            actor=actor,
        )["data"]
        tasks = ready_tasks["tasks"]
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            "index_name": ready_tasks["index_name"],
            "as_of": resolved_as_of,
            "count": len(tasks),
            "limit": limit,
            "tasks": tasks,
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=as_of,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def read_current(
    bootstrap: NodeBootstrap,
    *,
    as_of: str | None,
    ready_limit: int,
    lock_timeout_seconds: float,
    recover_stale_lock: bool,
    agent_id: str,
    session_id: str,
    command: str = "current",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, resolved_as_of: str) -> dict[str, Any]:
        del store
        project_id = state.adopted_project["project_id"]
        entrypoint = surface.project_entrypoint_get_local(project_id=project_id, as_of=resolved_as_of)["data"]
        sync_status = surface.sync_status(project_id=project_id, actor=actor)["data"]
        ready_tasks = surface.tasks_list_by_index(
            project_id=project_id,
            index_name="ready",
            as_of=resolved_as_of,
            limit=ready_limit,
            actor=actor,
        )["data"]
        return {
            **state_payload(state),
            "as_of": resolved_as_of,
            "entrypoint": entrypoint,
            "sync_status": sync_status,
            "ready_tasks": {
                "project_id": ready_tasks["project_id"],
                "index_name": ready_tasks["index_name"],
                "limit": ready_limit,
                "tasks": ready_tasks["tasks"],
            },
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=as_of,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def claim_ready_task(
    bootstrap: NodeBootstrap,
    *,
    task_id: str,
    plan: str,
    lease_minutes: int,
    lock_timeout_seconds: float,
    recover_stale_lock: bool,
    agent_id: str,
    session_id: str,
    command: str = "tasks_claim",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    lease_started_at, lease_expires_at = resolve_lease_window(lease_minutes=lease_minutes)

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, _resolved_as_of: str) -> dict[str, Any]:
        project_id = state.adopted_project["project_id"]
        claim_id = canonical_id("claim", project_id, task_id, actor.session_id, lease_started_at, plan)
        result = surface.tasks_claim(
            claim_id=claim_id,
            project_id=project_id,
            task_id=task_id,
            actor=actor,
            plan=plan,
            lease_started_at=lease_started_at,
            lease_expires_at=lease_expires_at,
        )
        store.db.commit()
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            **result["data"],
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=lease_started_at,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def audit_create_brief(
    bootstrap: NodeBootstrap,
    *,
    title: str,
    content: str,
    as_of: str | None = None,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "audit_create_brief",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_title = _require_text(title, field_name="title")
    resolved_content = _require_text(content, field_name="content")

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, resolved_as_of: str) -> dict[str, Any]:
        del store
        project_id = state.adopted_project["project_id"]
        audit_id = canonical_id("audit", project_id, resolved_as_of, resolved_title)
        result = surface.audit_create_brief(
            audit_id=audit_id,
            project_id=project_id,
            title=resolved_title,
            content=resolved_content,
            actor=actor,
        )
        surface.store.db.commit()
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            **result["data"],
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=as_of,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def audit_publish(
    bootstrap: NodeBootstrap,
    *,
    audit_id: str,
    as_of: str | None = None,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "audit_publish",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_audit_id = _require_text(audit_id, field_name="audit_id")

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, _resolved_as_of: str) -> dict[str, Any]:
        del store
        project_id = state.adopted_project["project_id"]
        result = surface.audit_publish(project_id=project_id, audit_id=resolved_audit_id, actor=actor)
        surface.store.db.commit()
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            **result["data"],
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=as_of,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def tasks_reconcile_start(
    bootstrap: NodeBootstrap,
    *,
    lifecycle_key: str,
    plan: str,
    lease_minutes: int,
    origin_audit_id: str | None = None,
    description: str | None = None,
    priority: str | None = None,
    effort: str | None = None,
    risk: str | None = None,
    task_type: str | None = None,
    justification: JustificationPayload | dict[str, Any] | None = None,
    execution_context: dict[str, Any] | None = None,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "tasks_reconcile_start",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_lifecycle_key = _require_text(lifecycle_key, field_name="lifecycle_key")
    resolved_plan = _require_text(plan, field_name="plan")
    if lease_minutes <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "lease_minutes must be a positive integer")
    lease_started_at, lease_expires_at = resolve_lease_window(lease_minutes=lease_minutes)

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, resolved_as_of: str) -> dict[str, Any]:
        project_id = state.adopted_project["project_id"]
        task = store.get_task_by_lifecycle_key(project_id, resolved_lifecycle_key)
        created_task = False
        if task is None:
            (
                create_origin_audit_id,
                create_description,
                create_priority,
                create_effort,
                create_risk,
                create_justification,
                create_execution_context,
            ) = _require_create_seed(
                origin_audit_id=origin_audit_id,
                description=description,
                priority=priority,
                effort=effort,
                risk=risk,
                task_type=task_type,
                justification=justification,
                execution_context=execution_context,
            )
            _require_published_origin_audit(store=store, project_id=project_id, audit_id=create_origin_audit_id)
            create_execution_context = _validate_same_project_context(project_id=project_id, execution_context=create_execution_context)
            create_execution_context.update(
                {
                    "project_id": project_id,
                    "lifecycle_key": resolved_lifecycle_key,
                    "lifecycle_plan": resolved_plan,
                    "lifecycle_creator": {
                        "node_id": actor.node_id,
                        "agent_id": actor.agent_id,
                        "session_id": actor.session_id,
                    },
                }
            )
            task_id = canonical_id("task", project_id, resolved_lifecycle_key)
            surface.tasks_create_from_audit(
                task_id=task_id,
                project_id=project_id,
                audit_id=create_origin_audit_id,
                mutation_id=_mutation_id("lifecycle", "create", task_id, actor.session_id, resolved_as_of),
                actor=actor,
                priority=create_priority,
                effort=create_effort,
                risk=create_risk,
                task_type=task_type.strip(),
                description=create_description,
                justification=create_justification,
                execution_context=create_execution_context,
                initial_state="ready",
                lifecycle_key=resolved_lifecycle_key,
            )
            task = store.get_task(task_id)
            created_task = True
        task, claim_id = _prepare_reusable_task(
            surface=surface,
            store=store,
            project_id=project_id,
            task=task,
            actor=actor,
            lifecycle_key=resolved_lifecycle_key,
            plan=resolved_plan,
            as_of=resolved_as_of,
        )
        if claim_id is None:
            claim_id = canonical_id("claim", project_id, task["task_id"], actor.session_id, lease_started_at, resolved_plan)
            surface.tasks_claim(
                claim_id=claim_id,
                project_id=project_id,
                task_id=task["task_id"],
                actor=actor,
                plan=resolved_plan,
                lease_started_at=lease_started_at,
                lease_expires_at=lease_expires_at,
            )
        refreshed_task = store.get_task(task["task_id"])
        if refreshed_task["state"] == "claimed":
            surface.tasks_transition(
                project_id=project_id,
                task_id=task["task_id"],
                mutation_id=_mutation_id("lifecycle", "start", task["task_id"], actor.session_id, resolved_as_of),
                actor=actor,
                requested_state="in_progress",
                justification=_lifecycle_justification(lifecycle_key=resolved_lifecycle_key, plan=resolved_plan),
                metadata={"active_claim_session_id": actor.session_id, "as_of": resolved_as_of},
            )
            refreshed_task = store.get_task(task["task_id"])
        store.db.commit()
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            "task_id": refreshed_task["task_id"],
            "claim_id": claim_id,
            "state": refreshed_task["state"],
            "lifecycle_key": resolved_lifecycle_key,
            "created_task": created_task,
            "lease_started_at": lease_started_at,
            "lease_expires_at": lease_expires_at,
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=lease_started_at,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def tasks_reconcile_finish(
    bootstrap: NodeBootstrap,
    *,
    lifecycle_key: str,
    outcome: str,
    as_of: str | None = None,
    done_result: str | None = None,
    done_artifacts: str | None = None,
    done_references: str | None = None,
    done_expected_impact: str | None = None,
    blocked_reason: str | None = None,
    blocked_evidence: str | None = None,
    blocked_next_step: str | None = None,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "tasks_reconcile_finish",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_lifecycle_key = _require_text(lifecycle_key, field_name="lifecycle_key")
    resolved_outcome = _require_text(outcome, field_name="outcome")
    finish_metadata = _require_finish_metadata(
        outcome=resolved_outcome,
        done_result=done_result,
        done_artifacts=done_artifacts,
        done_references=done_references,
        done_expected_impact=done_expected_impact,
        blocked_reason=blocked_reason,
        blocked_evidence=blocked_evidence,
        blocked_next_step=blocked_next_step,
    )

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, resolved_as_of: str) -> dict[str, Any]:
        project_id = state.adopted_project["project_id"]
        task = store.get_task_by_lifecycle_key(project_id, resolved_lifecycle_key)
        if task is None:
            raise SurfaceError("UNKNOWN_RESOURCE", f"unknown lifecycle task: {resolved_lifecycle_key}")
        task_id = task["task_id"]
        surface._sync_active_claim_state(
            project_id=project_id,
            task_id=task_id,
            as_of=resolved_as_of,
            expected_session_id=actor.session_id,
        )
        active_claim = surface.claims.get_active_claim(project_id=project_id, task_id=task_id, as_of=resolved_as_of) if surface.claims else None
        if not active_claim or active_claim.session_id != actor.session_id:
            store.db.commit()
            _raise_finish_claim_error(store=store, task_id=task_id, session_id=actor.session_id, as_of=resolved_as_of)
        surface.tasks_transition(
            project_id=project_id,
            task_id=task_id,
            mutation_id=_mutation_id("lifecycle", resolved_outcome, task_id, actor.session_id, resolved_as_of),
            actor=actor,
            requested_state=resolved_outcome,
            justification=_lifecycle_finish_justification(lifecycle_key=resolved_lifecycle_key, outcome=resolved_outcome),
            metadata=finish_metadata,
        )
        surface.tasks_release(project_id=project_id, task_id=task_id, claim_id=active_claim.claim_id, actor=actor)
        store.clear_cached_claim(task_id)
        store.db.commit()
        refreshed_task = store.get_task(task_id)
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            "task_id": refreshed_task["task_id"],
            "state": refreshed_task["state"],
            "lifecycle_key": resolved_lifecycle_key,
            "outcome": resolved_outcome,
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=as_of,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def _default_transition_justification(*, task_id: str, requested_state: str, summary: str | None = None) -> JustificationPayload:
    return JustificationPayload(
        summary=summary or f"Transition task {task_id} to {requested_state}",
        evidence_refs=(task_id, requested_state),
        expected_impact=f"Move task into state {requested_state}",
    )


def transition_task(
    bootstrap: NodeBootstrap,
    *,
    task_id: str,
    requested_state: str,
    justification: JustificationPayload | dict[str, Any] | None = None,
    summary: str | None = None,
    as_of: str | None = None,
    done_result: str | None = None,
    done_artifacts: str | None = None,
    done_references: str | None = None,
    done_expected_impact: str | None = None,
    blocked_reason: str | None = None,
    blocked_evidence: str | None = None,
    blocked_next_step: str | None = None,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "tasks_transition",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_task_id = _require_text(task_id, field_name="task_id")
    resolved_state = _require_text(requested_state, field_name="requested_state")
    metadata: dict[str, Any] = {}
    if resolved_state == "done":
        metadata.update(
            _require_finish_metadata(
                outcome="done",
                done_result=done_result,
                done_artifacts=done_artifacts,
                done_references=done_references,
                done_expected_impact=done_expected_impact,
                blocked_reason=None,
                blocked_evidence=None,
                blocked_next_step=None,
            )
        )
    elif resolved_state == "blocked":
        metadata.update(
            _require_finish_metadata(
                outcome="blocked",
                done_result=None,
                done_artifacts=None,
                done_references=None,
                done_expected_impact=None,
                blocked_reason=blocked_reason,
                blocked_evidence=blocked_evidence,
                blocked_next_step=blocked_next_step,
            )
        )

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, resolved_as_of: str) -> dict[str, Any]:
        project_id = state.adopted_project["project_id"]
        task = store.get_task(resolved_task_id)
        if not task:
            raise SurfaceError("UNKNOWN_RESOURCE", f"unknown task: {resolved_task_id}")
        if task["project_id"] != project_id:
            raise SurfaceError("INVALID_TASK_STATE", "task does not belong to the adopted project")
        previous_state = task["state"]
        justification_payload = (
            _coerce_justification(justification)
            if justification is not None
            else _default_transition_justification(task_id=resolved_task_id, requested_state=resolved_state, summary=summary)
        )
        if resolved_state in {"claimed", "in_progress"}:
            metadata["active_claim_session_id"] = actor.session_id
        metadata["as_of"] = resolved_as_of
        result = surface.tasks_transition(
            project_id=project_id,
            task_id=resolved_task_id,
            mutation_id=_mutation_id("transition", resolved_task_id, actor.session_id, resolved_as_of, resolved_state),
            actor=actor,
            requested_state=resolved_state,
            justification=justification_payload,
            metadata=metadata,
        )
        if resolved_state in {"done", "blocked", "cancelled"} and surface.claims:
            active_claim = surface.claims.get_active_claim(project_id=project_id, task_id=resolved_task_id, as_of=resolved_as_of)
            if active_claim and active_claim.session_id == actor.session_id:
                surface.tasks_release(
                    project_id=project_id,
                    task_id=resolved_task_id,
                    claim_id=active_claim.claim_id,
                    actor=actor,
                )
                store.clear_cached_claim(resolved_task_id)
        store.db.commit()
        refreshed_task = store.get_task(resolved_task_id)
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            "task_id": refreshed_task["task_id"],
            "previous_state": previous_state,
            "state": refreshed_task["state"],
            "requested_state": resolved_state,
            "authority_mode": result["data"].get("authority_mode"),
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=as_of,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def release_task(
    bootstrap: NodeBootstrap,
    *,
    task_id: str,
    claim_id: str,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "tasks_release",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_task_id = _require_text(task_id, field_name="task_id")
    resolved_claim_id = _require_text(claim_id, field_name="claim_id")

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, _resolved_as_of: str) -> dict[str, Any]:
        project_id = state.adopted_project["project_id"]
        result = surface.tasks_release(
            project_id=project_id,
            task_id=resolved_task_id,
            claim_id=resolved_claim_id,
            actor=actor,
        )
        store.clear_cached_claim(resolved_task_id)
        store.db.commit()
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            **result["data"],
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=None,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )


def renew_task_claim(
    bootstrap: NodeBootstrap,
    *,
    task_id: str,
    claim_id: str,
    lease_minutes: int,
    lock_timeout_seconds: float = 30.0,
    recover_stale_lock: bool = False,
    agent_id: str = "capiforge-agent",
    session_id: str = "capiforge-agent-session",
    command: str = "tasks_claim_renew",
    wait_reporter: Callable[[str, dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    resolved_task_id = _require_text(task_id, field_name="task_id")
    resolved_claim_id = _require_text(claim_id, field_name="claim_id")
    if lease_minutes <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "lease_minutes must be a positive integer")
    renewed_at, lease_expires_at = resolve_lease_window(lease_minutes=lease_minutes)

    def _reader(state: BootstrapState, store: NodeStore, surface: NodeMCPSurface, actor: ActorIdentity, _resolved_as_of: str) -> dict[str, Any]:
        project_id = state.adopted_project["project_id"]
        if not surface.claims:
            raise SurfaceError("UNKNOWN_RESOURCE", "claim registry is unavailable")
        claim = surface.claims.renew_claim(
            claim_id=resolved_claim_id,
            actor=actor,
            lease_expires_at=lease_expires_at,
            renewed_at=renewed_at,
        )
        if claim.project_id != project_id or claim.task_id != resolved_task_id:
            raise SurfaceError("INVALID_TASK_STATE", "claim does not match the supplied project and task")
        store.cache_claim(
            resolved_task_id,
            claim.claim_id,
            claim.status,
            claim.lease_expires_at,
            claim.node_id,
            claim.agent_id,
            claim.session_id,
            claim.plan,
        )
        store.db.commit()
        return {
            "bootstrap_state": state.state,
            "adopted_project": state.adopted_project,
            "claim_id": claim.claim_id,
            "task_id": claim.task_id,
            "status": claim.status,
            "lease_expires_at": claim.lease_expires_at,
        }

    return _with_adopted_surface(
        bootstrap,
        as_of=renewed_at,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=agent_id,
        session_id=session_id,
        command=command,
        wait_reporter=wait_reporter,
        reader=_reader,
    )
