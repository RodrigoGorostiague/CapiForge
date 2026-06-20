from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator
from uuid import NAMESPACE_URL, uuid5

from runtime.node.bootstrap import DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS, BootstrapState, NodeBootstrap
from runtime.node.current import (
    audit_create_brief,
    audit_publish,
    claim_ready_task,
    read_current,
    read_ready_tasks,
    release_task,
    renew_task_claim,
    tasks_reconcile_finish,
    tasks_reconcile_start,
    transition_task,
)
from runtime.node.index import INDEXES
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity

PROTOCOL_VERSION = "2025-03-26"
SERVER_NAME = "capiforge"
SERVER_VERSION = "0.1.0"
LOCAL_AGENT_ID = "capiforge-mcp-server"
LOCAL_SESSION_ID = "local-stdio-session"


@dataclass(frozen=True)
class McpActorContext:
    agent_id: str
    session_id: str


def resolve_mcp_actor_context(*, client_info: dict[str, Any] | None = None) -> McpActorContext:
    agent_id = os.environ.get("CAPIFORGE_AGENT_ID", LOCAL_AGENT_ID).strip() or LOCAL_AGENT_ID
    session_override = os.environ.get("CAPIFORGE_SESSION_ID", "").strip()
    if session_override:
        session_id = session_override
    elif isinstance(client_info, dict):
        client_name = str(client_info.get("name", "unknown-client")).strip() or "unknown-client"
        client_version = str(client_info.get("version", "0")).strip() or "0"
        digest = uuid5(NAMESPACE_URL, f"{client_name}:{client_version}").hex[:12]
        session_id = f"mcp-{client_name}-{digest}"
    else:
        session_id = LOCAL_SESSION_ID
    return McpActorContext(agent_id=agent_id, session_id=session_id)


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SurfaceError("INVALID_ARGUMENTS", message)


def _non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("--lock-timeout-seconds must be greater than or equal to 0")
    return value


@dataclass(frozen=True)
class SurfaceContext:
    state: BootstrapState
    surface: NodeMCPSurface
    store: NodeStore


@dataclass(frozen=True)
class ServerOptions:
    repo_root: str
    node_home: str | None
    lock_timeout_seconds: float
    recover_stale_lock: bool


def _write_stdout(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, sort_keys=True) + "\n")
    sys.stdout.flush()


def _write_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _jsonrpc_error(message_id: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        payload["error"]["data"] = data
    return payload


def _jsonrpc_result(message_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": message_id, "result": result}


def _tool_result(payload: dict[str, Any], *, is_error: bool = False) -> dict[str, Any]:
    text = json.dumps(payload, indent=2, sort_keys=True)
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }


from runtime.paths import default_repo_root


def _build_parser(*, prog: str = "capiforge_mcp_server") -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog=prog)
    parser.add_argument("--repo-root", default=str(default_repo_root()))
    parser.add_argument("--node-home")
    parser.add_argument("--lock-timeout-seconds", type=_non_negative_float, default=DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS)
    parser.add_argument("--recover-stale-lock", action="store_true")
    return parser


def _bootstrap(options: ServerOptions) -> NodeBootstrap:
    return NodeBootstrap(repo_root=options.repo_root, node_home=options.node_home)


def _local_actor(state: BootstrapState, *, actor_context: McpActorContext) -> ActorIdentity:
    return ActorIdentity(
        node_id=state.local_node_id,
        agent_id=actor_context.agent_id,
        session_id=actor_context.session_id,
    )


@contextmanager
def _surface_context(options: ServerOptions) -> Iterator[SurfaceContext]:
    bootstrap = _bootstrap(options)
    with bootstrap.bootstrap_session(
        command="mcp_surface",
        timeout=options.lock_timeout_seconds,
        interactive=False,
        verbose=False,
        recover_stale_lock=options.recover_stale_lock,
    ):
        state, store = bootstrap._open_adopted_store_unlocked()
        try:
            yield SurfaceContext(
                state=state,
                surface=NodeMCPSurface(store=store, router=NodeRouter(store), local_node_id=state.local_node_id),
                store=store,
            )
        finally:
            store.close()


def _workspace_get_current(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    del arguments
    with _surface_context(options) as context:
        workspace_id = context.state.adopted_project["workspace_id"]
        return {
            "status": "ok",
            "data": {
                "adopted_project": context.state.adopted_project,
                "workspace": context.surface.workspace_get(workspace_id=workspace_id)["data"],
            },
        }


def _project_entrypoint_get(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    as_of = arguments.get("as_of")
    if not isinstance(as_of, str) or not as_of:
        raise SurfaceError("INVALID_ARGUMENTS", "project_entrypoint_get requires a non-empty string as_of")
    bootstrap = _bootstrap(options)
    state, entrypoint = bootstrap.read_entrypoint(
        as_of=as_of,
        lock_timeout_seconds=options.lock_timeout_seconds,
        interactive=False,
        recover_stale_lock=options.recover_stale_lock,
    )
    return {"status": "ok", "data": {"adopted_project": state.adopted_project, "entrypoint": entrypoint}}


def _tasks_list_by_index(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    index_name = arguments.get("index_name")
    as_of = arguments.get("as_of")
    limit = arguments.get("limit", 20)
    if index_name not in INDEXES:
        raise SurfaceError("INVALID_ARGUMENTS", f"index_name must be one of: {', '.join(INDEXES)}")
    if not isinstance(as_of, str) or not as_of:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_list_by_index requires a non-empty string as_of")
    if not isinstance(limit, int) or limit <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_list_by_index requires limit to be a positive integer")
    with _surface_context(options) as context:
        actor = _local_actor(context.state, actor_context=actor_context)
        result = context.surface.tasks_list_by_index(
            project_id=context.state.adopted_project["project_id"],
            index_name=index_name,
            as_of=as_of,
            limit=limit,
            actor=actor,
        )
        return {"status": result["status"], "data": {"adopted_project": context.state.adopted_project, **result["data"]}}


def _sync_status(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    del arguments
    with _surface_context(options) as context:
        actor = _local_actor(context.state, actor_context=actor_context)
        result = context.surface.sync_status(project_id=context.state.adopted_project["project_id"], actor=actor)
        return {"status": result["status"], "data": {"adopted_project": context.state.adopted_project, **result["data"]}}


def _current_get(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    as_of = arguments.get("as_of")
    ready_limit = arguments.get("ready_limit", 10)
    if as_of is not None and (not isinstance(as_of, str) or not as_of):
        raise SurfaceError("INVALID_ARGUMENTS", "current_get requires as_of to be a non-empty string when provided")
    if not isinstance(ready_limit, int) or ready_limit <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "current_get requires ready_limit to be a positive integer")
    bootstrap = _bootstrap(options)
    return {
        "status": "ok",
        "data": read_current(
            bootstrap,
            as_of=as_of,
            ready_limit=ready_limit,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="current_get",
        ),
    }


def _tasks_ready_get(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    as_of = arguments.get("as_of")
    limit = arguments.get("limit", 20)
    if as_of is not None and (not isinstance(as_of, str) or not as_of):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_ready_get requires as_of to be a non-empty string when provided")
    if not isinstance(limit, int) or limit <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_ready_get requires limit to be a positive integer")
    bootstrap = _bootstrap(options)
    return {
        "status": "ok",
        "data": read_ready_tasks(
            bootstrap,
            as_of=as_of,
            limit=limit,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_ready_get",
        ),
    }


def _tasks_claim(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    task_id = arguments.get("task_id")
    plan = arguments.get("plan")
    lease_minutes = arguments.get("lease_minutes", 5)
    if not isinstance(task_id, str) or not task_id:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_claim requires task_id to be a non-empty string")
    if not isinstance(plan, str) or not plan:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_claim requires plan to be a non-empty string")
    if not isinstance(lease_minutes, int) or lease_minutes <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_claim requires lease_minutes to be a positive integer")
    bootstrap = _bootstrap(options)
    return {
        "status": "claimed",
        "data": claim_ready_task(
            bootstrap,
            task_id=task_id,
            plan=plan,
            lease_minutes=lease_minutes,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_claim",
        ),
    }


def _audit_create_brief(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    title = arguments.get("title")
    content = arguments.get("content")
    as_of = arguments.get("as_of")
    if not isinstance(title, str) or not title:
        raise SurfaceError("INVALID_ARGUMENTS", "audit_create_brief requires title to be a non-empty string")
    if not isinstance(content, str) or not content:
        raise SurfaceError("INVALID_ARGUMENTS", "audit_create_brief requires content to be a non-empty string")
    if as_of is not None and (not isinstance(as_of, str) or not as_of):
        raise SurfaceError("INVALID_ARGUMENTS", "audit_create_brief requires as_of to be a non-empty string when provided")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": audit_create_brief(
            bootstrap,
            title=title,
            content=content,
            as_of=as_of,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="audit_create_brief",
        ),
    }


def _audit_publish(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    audit_id = arguments.get("audit_id")
    as_of = arguments.get("as_of")
    if not isinstance(audit_id, str) or not audit_id:
        raise SurfaceError("INVALID_ARGUMENTS", "audit_publish requires audit_id to be a non-empty string")
    if as_of is not None and (not isinstance(as_of, str) or not as_of):
        raise SurfaceError("INVALID_ARGUMENTS", "audit_publish requires as_of to be a non-empty string when provided")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": audit_publish(
            bootstrap,
            audit_id=audit_id,
            as_of=as_of,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="audit_publish",
        ),
    }


def _tasks_reconcile_start(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    lifecycle_key = arguments.get("lifecycle_key")
    plan = arguments.get("plan")
    lease_minutes = arguments.get("lease_minutes", 5)
    origin_audit_id = arguments.get("origin_audit_id")
    description = arguments.get("description")
    priority = arguments.get("priority")
    effort = arguments.get("effort")
    risk = arguments.get("risk")
    task_type = arguments.get("task_type")
    justification = arguments.get("justification")
    execution_context = arguments.get("execution_context")
    if not isinstance(lifecycle_key, str) or not lifecycle_key:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_reconcile_start requires lifecycle_key to be a non-empty string")
    if not isinstance(plan, str) or not plan:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_reconcile_start requires plan to be a non-empty string")
    if not isinstance(lease_minutes, int) or lease_minutes <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_reconcile_start requires lease_minutes to be a positive integer")
    for field_name, value in (
        ("origin_audit_id", origin_audit_id),
        ("description", description),
        ("priority", priority),
        ("effort", effort),
        ("risk", risk),
        ("task_type", task_type),
    ):
        if value is not None and (not isinstance(value, str) or not value):
            raise SurfaceError("INVALID_ARGUMENTS", f"tasks_reconcile_start requires {field_name} to be a non-empty string when provided")
    if justification is not None and not isinstance(justification, dict):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_reconcile_start requires justification to be an object when provided")
    if execution_context is not None and not isinstance(execution_context, dict):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_reconcile_start requires execution_context to be an object when provided")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": tasks_reconcile_start(
            bootstrap,
            lifecycle_key=lifecycle_key,
            plan=plan,
            lease_minutes=lease_minutes,
            origin_audit_id=origin_audit_id,
            description=description,
            priority=priority,
            effort=effort,
            risk=risk,
            task_type=task_type,
            justification=justification,
            execution_context=execution_context,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_reconcile_start",
        ),
    }


def _tasks_reconcile_finish(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    lifecycle_key = arguments.get("lifecycle_key")
    outcome = arguments.get("outcome")
    as_of = arguments.get("as_of")
    done_result = arguments.get("done_result")
    done_artifacts = arguments.get("done_artifacts")
    done_references = arguments.get("done_references")
    done_expected_impact = arguments.get("done_expected_impact")
    blocked_reason = arguments.get("blocked_reason")
    blocked_evidence = arguments.get("blocked_evidence")
    blocked_next_step = arguments.get("blocked_next_step")
    for field_name, value in (("lifecycle_key", lifecycle_key), ("outcome", outcome)):
        if not isinstance(value, str) or not value:
            raise SurfaceError("INVALID_ARGUMENTS", f"tasks_reconcile_finish requires {field_name} to be a non-empty string")
    if as_of is not None and (not isinstance(as_of, str) or not as_of):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_reconcile_finish requires as_of to be a non-empty string when provided")
    for field_name, value in (
        ("done_result", done_result),
        ("done_artifacts", done_artifacts),
        ("done_references", done_references),
        ("done_expected_impact", done_expected_impact),
        ("blocked_reason", blocked_reason),
        ("blocked_evidence", blocked_evidence),
        ("blocked_next_step", blocked_next_step),
    ):
        if value is not None and (not isinstance(value, str) or not value):
            raise SurfaceError("INVALID_ARGUMENTS", f"tasks_reconcile_finish requires {field_name} to be a non-empty string when provided")
    if outcome == "done":
        missing = [
            field_name
            for field_name, value in (
                ("done_result", done_result),
                ("done_artifacts", done_artifacts),
                ("done_references", done_references),
                ("done_expected_impact", done_expected_impact),
            )
            if not isinstance(value, str) or not value
        ]
    else:
        missing = [
            field_name
            for field_name, value in (
                ("blocked_reason", blocked_reason),
                ("blocked_evidence", blocked_evidence),
                ("blocked_next_step", blocked_next_step),
            )
            if not isinstance(value, str) or not value
        ]
    if missing:
        raise SurfaceError("INVALID_ARGUMENTS", f"tasks_reconcile_finish requires explicit finish metadata: {', '.join(missing)}")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": tasks_reconcile_finish(
            bootstrap,
            lifecycle_key=lifecycle_key,
            outcome=outcome,
            as_of=as_of,
            done_result=done_result,
            done_artifacts=done_artifacts,
            done_references=done_references,
            done_expected_impact=done_expected_impact,
            blocked_reason=blocked_reason,
            blocked_evidence=blocked_evidence,
            blocked_next_step=blocked_next_step,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_reconcile_finish",
        ),
    }


def _tasks_transition(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    task_id = arguments.get("task_id")
    requested_state = arguments.get("requested_state")
    as_of = arguments.get("as_of")
    summary = arguments.get("summary")
    justification = arguments.get("justification")
    done_result = arguments.get("done_result")
    done_artifacts = arguments.get("done_artifacts")
    done_references = arguments.get("done_references")
    done_expected_impact = arguments.get("done_expected_impact")
    blocked_reason = arguments.get("blocked_reason")
    blocked_evidence = arguments.get("blocked_evidence")
    blocked_next_step = arguments.get("blocked_next_step")
    if not isinstance(task_id, str) or not task_id:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_transition requires task_id to be a non-empty string")
    if not isinstance(requested_state, str) or not requested_state:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_transition requires requested_state to be a non-empty string")
    if as_of is not None and (not isinstance(as_of, str) or not as_of):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_transition requires as_of to be a non-empty string when provided")
    if summary is not None and (not isinstance(summary, str) or not summary):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_transition requires summary to be a non-empty string when provided")
    if justification is not None and not isinstance(justification, dict):
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_transition requires justification to be an object when provided")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": transition_task(
            bootstrap,
            task_id=task_id,
            requested_state=requested_state,
            justification=justification,
            summary=summary,
            as_of=as_of,
            done_result=done_result,
            done_artifacts=done_artifacts,
            done_references=done_references,
            done_expected_impact=done_expected_impact,
            blocked_reason=blocked_reason,
            blocked_evidence=blocked_evidence,
            blocked_next_step=blocked_next_step,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_transition",
        ),
    }


def _tasks_release(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    task_id = arguments.get("task_id")
    claim_id = arguments.get("claim_id")
    if not isinstance(task_id, str) or not task_id:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_release requires task_id to be a non-empty string")
    if not isinstance(claim_id, str) or not claim_id:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_release requires claim_id to be a non-empty string")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": release_task(
            bootstrap,
            task_id=task_id,
            claim_id=claim_id,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_release",
        ),
    }


def _tasks_claim_renew(options: ServerOptions, arguments: dict[str, Any], actor_context: McpActorContext) -> dict[str, Any]:
    task_id = arguments.get("task_id")
    claim_id = arguments.get("claim_id")
    lease_minutes = arguments.get("lease_minutes", 5)
    if not isinstance(task_id, str) or not task_id:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_claim_renew requires task_id to be a non-empty string")
    if not isinstance(claim_id, str) or not claim_id:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_claim_renew requires claim_id to be a non-empty string")
    if not isinstance(lease_minutes, int) or lease_minutes <= 0:
        raise SurfaceError("INVALID_ARGUMENTS", "tasks_claim_renew requires lease_minutes to be a positive integer")
    bootstrap = _bootstrap(options)
    return {
        "status": "accepted",
        "data": renew_task_claim(
            bootstrap,
            task_id=task_id,
            claim_id=claim_id,
            lease_minutes=lease_minutes,
            lock_timeout_seconds=options.lock_timeout_seconds,
            recover_stale_lock=options.recover_stale_lock,
            agent_id=actor_context.agent_id,
            session_id=actor_context.session_id,
            command="tasks_claim_renew",
        ),
    }


TOOLS: dict[str, dict[str, Any]] = {
    "workspace_get_current": {
        "description": "Read the adopted workspace and its locally visible projects.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _workspace_get_current,
    },
    "project_entrypoint_get": {
        "description": "Read the adopted project's deterministic entrypoint for a specific as_of timestamp.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "as_of": {
                    "type": "string",
                    "description": "Deterministic timestamp for generated output, for example 2026-06-19T13:45:00Z.",
                }
            },
            "required": ["as_of"],
            "additionalProperties": False,
        },
        "handler": _project_entrypoint_get,
    },
    "tasks_list_by_index": {
        "description": "Read a bounded task queue for the adopted project.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "index_name": {"type": "string", "enum": list(INDEXES)},
                "as_of": {
                    "type": "string",
                    "description": "Deterministic timestamp used for expired claim evaluation.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "required": ["index_name", "as_of"],
            "additionalProperties": False,
        },
        "handler": _tasks_list_by_index,
    },
    "sync_status": {
        "description": "Read sync visibility for the adopted project. Local-only bootstrap returns degraded non-authoritative status.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
        "handler": _sync_status,
    },
    "current_get": {
        "description": "Read the adopted project's aggregate current payload, matching the CLI current flow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "as_of": {
                    "type": "string",
                    "description": "Optional deterministic timestamp for generated output, for example 2026-06-19T13:45:00Z.",
                },
                "ready_limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 10},
            },
            "additionalProperties": False,
        },
        "handler": _current_get,
    },
    "tasks_ready_get": {
        "description": "Read the adopted ready task queue, matching the CLI tasks ready flow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "as_of": {
                    "type": "string",
                    "description": "Optional deterministic timestamp used for expired claim evaluation.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
            "additionalProperties": False,
        },
        "handler": _tasks_ready_get,
    },
    "tasks_claim": {
        "description": "Claim an adopted ready task, matching the CLI tasks claim flow.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "plan": {"type": "string"},
                "lease_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 5},
            },
            "required": ["task_id", "plan"],
            "additionalProperties": False,
        },
        "handler": _tasks_claim,
    },
    "tasks_transition": {
        "description": "Transition an adopted task state with claim validation and explicit finish metadata for terminal states.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "requested_state": {
                    "type": "string",
                    "enum": ["claimed", "in_progress", "blocked", "done", "cancelled", "ready"],
                },
                "as_of": {"type": "string"},
                "summary": {"type": "string"},
                "justification": {"type": "object", "additionalProperties": True},
                "done_result": {"type": "string"},
                "done_artifacts": {"type": "string"},
                "done_references": {"type": "string"},
                "done_expected_impact": {"type": "string"},
                "blocked_reason": {"type": "string"},
                "blocked_evidence": {"type": "string"},
                "blocked_next_step": {"type": "string"},
            },
            "required": ["task_id", "requested_state"],
            "additionalProperties": False,
        },
        "handler": _tasks_transition,
    },
    "tasks_release": {
        "description": "Release an active claim for an adopted task without closing the task.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "claim_id": {"type": "string"},
            },
            "required": ["task_id", "claim_id"],
            "additionalProperties": False,
        },
        "handler": _tasks_release,
    },
    "tasks_claim_renew": {
        "description": "Renew an active claim lease for long-running adopted-task work.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "claim_id": {"type": "string"},
                "lease_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 5},
            },
            "required": ["task_id", "claim_id"],
            "additionalProperties": False,
        },
        "handler": _tasks_claim_renew,
    },
    "audit_create_brief": {
        "description": "Create a draft brief audit for the adopted project using the public owner-local surface.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "as_of": {
                    "type": "string",
                    "description": "Optional deterministic timestamp used for canonical audit ID generation.",
                },
            },
            "required": ["title", "content"],
            "additionalProperties": False,
        },
        "handler": _audit_create_brief,
    },
    "audit_publish": {
        "description": "Publish a draft brief audit for the adopted project using the public owner-local surface.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "audit_id": {"type": "string"},
                "as_of": {
                    "type": "string",
                    "description": "Optional deterministic timestamp used for validation context.",
                },
            },
            "required": ["audit_id"],
            "additionalProperties": False,
        },
        "handler": _audit_publish,
    },
    "tasks_reconcile_start": {
        "description": "Reconcile owner-local same-project lifecycle work into an adopted in-progress task, creating on miss only from a published same-project audit.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lifecycle_key": {"type": "string"},
                "plan": {"type": "string"},
                "lease_minutes": {"type": "integer", "minimum": 1, "maximum": 1440, "default": 5},
                "origin_audit_id": {"type": "string"},
                "description": {"type": "string"},
                "priority": {"type": "string"},
                "effort": {"type": "string"},
                "risk": {"type": "string"},
                "task_type": {"type": "string"},
                "justification": {"type": "object", "additionalProperties": True},
                "execution_context": {"type": "object", "additionalProperties": True},
            },
            "required": ["lifecycle_key", "plan"],
            "additionalProperties": False,
        },
        "handler": _tasks_reconcile_start,
    },
    "tasks_reconcile_finish": {
        "description": "Close owner-local adopted lifecycle work to done or blocked when the active claim is still valid and explicit finish metadata is supplied.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "lifecycle_key": {"type": "string"},
                "outcome": {"type": "string", "enum": ["done", "blocked"]},
                "as_of": {
                    "type": "string",
                    "description": "Optional deterministic timestamp used for expired claim evaluation.",
                },
                "done_result": {"type": "string"},
                "done_artifacts": {"type": "string"},
                "done_references": {"type": "string"},
                "done_expected_impact": {"type": "string"},
                "blocked_reason": {"type": "string"},
                "blocked_evidence": {"type": "string"},
                "blocked_next_step": {"type": "string"},
            },
            "required": ["lifecycle_key", "outcome"],
            "additionalProperties": False,
        },
        "handler": _tasks_reconcile_finish,
    },
}


class MCPServer:
    def __init__(self, options: ServerOptions):
        self.options = options
        self.initialized = False
        self.actor_context = resolve_mcp_actor_context()

    def run(self) -> int:
        while True:
            raw = sys.stdin.readline()
            if raw == "":
                return 0
            raw = raw.strip()
            if not raw:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError as exc:
                _write_stdout(_jsonrpc_error(None, -32700, "Parse error", {"details": str(exc)}))
                continue
            responses = self._handle_message(message)
            for response in responses:
                if response is not None:
                    _write_stdout(response)

    def _handle_message(self, message: Any) -> list[dict[str, Any] | None]:
        if isinstance(message, list):
            return [self._handle_request(item) for item in message]
        return [self._handle_request(message)]

    def _handle_request(self, message: Any) -> dict[str, Any] | None:
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _jsonrpc_error(message.get("id") if isinstance(message, dict) else None, -32600, "Invalid Request")
        method = message.get("method")
        params = message.get("params") or {}
        message_id = message.get("id")
        if not isinstance(params, dict):
            return _jsonrpc_error(message_id, -32602, "Invalid params")
        if method == "initialize":
            return self._handle_initialize(message_id, params)
        if method == "notifications/initialized":
            self.initialized = True
            return None
        if method == "ping":
            return _jsonrpc_result(message_id, {}) if message_id is not None else None
        if not self.initialized:
            return _jsonrpc_error(message_id, -32002, "Server not initialized")
        if method == "tools/list":
            return self._handle_tools_list(message_id)
        if method == "tools/call":
            return self._handle_tools_call(message_id, params)
        if message_id is None:
            return None
        return _jsonrpc_error(message_id, -32601, f"Method not found: {method}")

    def _handle_initialize(self, message_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        requested_version = params.get("protocolVersion")
        if not isinstance(requested_version, str) or not requested_version:
            return _jsonrpc_error(message_id, -32602, "initialize requires protocolVersion")
        client_info = params.get("clientInfo")
        if isinstance(client_info, dict):
            self.actor_context = resolve_mcp_actor_context(client_info=client_info)
        return _jsonrpc_result(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION if requested_version != PROTOCOL_VERSION else requested_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "CapiForge exposes owner-local node tools over stdio for adopted repositories, including public brief-audit create/publish, claim/transition/release flows, and lifecycle start/finish reconciliation.",
            },
        )

    def _handle_tools_list(self, message_id: Any) -> dict[str, Any]:
        tools = [
            {
                "name": name,
                "description": definition["description"],
                "inputSchema": definition["inputSchema"],
            }
            for name, definition in TOOLS.items()
        ]
        return _jsonrpc_result(message_id, {"tools": tools})

    def _handle_tools_call(self, message_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        tool_name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(tool_name, str) or tool_name not in TOOLS:
            return _jsonrpc_error(message_id, -32602, f"Unknown tool: {tool_name}")
        if not isinstance(arguments, dict):
            return _jsonrpc_error(message_id, -32602, "Tool arguments must be an object")
        try:
            payload = TOOLS[tool_name]["handler"](self.options, arguments, self.actor_context)
            return _jsonrpc_result(message_id, _tool_result(payload))
        except SurfaceError as exc:
            return _jsonrpc_result(message_id, _tool_result({"status": "error", "error": exc.to_dict()}, is_error=True))
        except Exception as exc:  # pragma: no cover - defensive server boundary
            _write_stderr(f"Unhandled MCP server error: {exc}")
            return _jsonrpc_result(
                message_id,
                _tool_result({"status": "error", "error": {"code": "INTERNAL_ERROR", "message": str(exc)}}, is_error=True),
            )


def main(argv: list[str] | None = None, *, prog: str = "capiforge_mcp_server") -> int:
    args = _build_parser(prog=prog).parse_args(argv)
    options = ServerOptions(
        repo_root=args.repo_root,
        node_home=args.node_home,
        lock_timeout_seconds=args.lock_timeout_seconds,
        recover_stale_lock=args.recover_stale_lock,
    )
    return MCPServer(options).run()


if __name__ == "__main__":
    raise SystemExit(main())
