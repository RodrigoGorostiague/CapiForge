from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.node.bootstrap import BootstrapState, NodeBootstrap
from runtime.node.mcp import NodeMCPSurface
from runtime.node.router import NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.errors import SurfaceError


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SurfaceError("INVALID_ARGUMENTS", message)


def _state_payload(state: BootstrapState) -> dict:
    return {
        "bootstrap_state": state.state,
        "local_node_id": state.local_node_id,
        "node_home": state.node_home,
        "node_db_path": state.node_db_path,
        "adopted_project": state.adopted_project,
    }


def _print_envelope(*, status: str, data: dict | None = None, error: dict | None = None) -> int:
    print(json.dumps({"status": status, "data": data, "error": error}, sort_keys=True))
    return 0 if status != "error" else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="capiforge_cli")
    parser.add_argument("command", choices=("init", "adopt", "status", "read"))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--node-home")
    parser.add_argument("--as-of")
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _build_parser().parse_args(argv)
        bootstrap = NodeBootstrap(repo_root=args.repo_root, node_home=args.node_home)

        if args.command == "init":
            state = bootstrap.open_or_init()
            return _print_envelope(status="accepted", data=_state_payload(state), error=None)

        if args.command == "adopt":
            state = bootstrap.adopt_repo()
            return _print_envelope(status="accepted", data=_state_payload(state), error=None)

        if args.command == "status":
            state = bootstrap.status()
            return _print_envelope(status="ok", data=_state_payload(state), error=None)

        if not args.as_of:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "read requires --as-of for deterministic output")

        state = bootstrap.require_adopted()
        store = NodeStore.from_file(state.node_db_path)
        try:
            surface = NodeMCPSurface(store=store, router=NodeRouter(store), local_node_id=state.local_node_id)
            entrypoint = surface.project_entrypoint_get_local(
                project_id=state.adopted_project["project_id"],
                as_of=args.as_of,
            )
        finally:
            store.close()
        return _print_envelope(
            status="ok",
            data={
                **_state_payload(state),
                "project": state.adopted_project,
                "entrypoint": entrypoint["data"],
            },
            error=None,
        )
    except SurfaceError as exc:
        return _print_envelope(status="error", data=None, error=exc.to_dict())


if __name__ == "__main__":
    raise SystemExit(main())
