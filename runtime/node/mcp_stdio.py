from __future__ import annotations

import argparse
import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from runtime.node.bootstrap import DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS, BootstrapState, NodeBootstrap
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


def _build_parser(*, prog: str = "capiforge_mcp_server") -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog=prog)
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[2]))
    parser.add_argument("--node-home")
    parser.add_argument("--lock-timeout-seconds", type=_non_negative_float, default=DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS)
    parser.add_argument("--recover-stale-lock", action="store_true")
    return parser


def _bootstrap(options: ServerOptions) -> NodeBootstrap:
    return NodeBootstrap(repo_root=options.repo_root, node_home=options.node_home)


def _local_actor(state: BootstrapState) -> ActorIdentity:
    return ActorIdentity(node_id=state.local_node_id, agent_id=LOCAL_AGENT_ID, session_id=LOCAL_SESSION_ID)


@contextmanager
def _surface_context(options: ServerOptions) -> Iterator[SurfaceContext]:
    bootstrap = _bootstrap(options)
    state = bootstrap.require_adopted(
        lock_timeout_seconds=options.lock_timeout_seconds,
        interactive=False,
        recover_stale_lock=options.recover_stale_lock,
    )
    store = NodeStore.from_file(state.node_db_path)
    try:
        yield SurfaceContext(
            state=state,
            surface=NodeMCPSurface(store=store, router=NodeRouter(store), local_node_id=state.local_node_id),
            store=store,
        )
    finally:
        store.close()


def _workspace_get_current(options: ServerOptions, arguments: dict[str, Any]) -> dict[str, Any]:
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


def _project_entrypoint_get(options: ServerOptions, arguments: dict[str, Any]) -> dict[str, Any]:
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


def _tasks_list_by_index(options: ServerOptions, arguments: dict[str, Any]) -> dict[str, Any]:
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
        actor = _local_actor(context.state)
        result = context.surface.tasks_list_by_index(
            project_id=context.state.adopted_project["project_id"],
            index_name=index_name,
            as_of=as_of,
            limit=limit,
            actor=actor,
        )
        return {"status": result["status"], "data": {"adopted_project": context.state.adopted_project, **result["data"]}}


def _sync_status(options: ServerOptions, arguments: dict[str, Any]) -> dict[str, Any]:
    del arguments
    with _surface_context(options) as context:
        actor = _local_actor(context.state)
        result = context.surface.sync_status(project_id=context.state.adopted_project["project_id"], actor=actor)
        return {"status": result["status"], "data": {"adopted_project": context.state.adopted_project, **result["data"]}}


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
}


class MCPServer:
    def __init__(self, options: ServerOptions):
        self.options = options
        self.initialized = False

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
        return _jsonrpc_result(
            message_id,
            {
                "protocolVersion": PROTOCOL_VERSION if requested_version != PROTOCOL_VERSION else requested_version,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": "CapiForge exposes read-only local node tools over stdio for adopted repositories.",
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
            payload = TOOLS[tool_name]["handler"](self.options, arguments)
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
