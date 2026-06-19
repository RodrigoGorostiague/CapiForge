from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.node.bootstrap import DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS, BootstrapState, NodeBootstrap
from runtime.shared.errors import SurfaceError


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SurfaceError("INVALID_ARGUMENTS", message)


def _non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("--lock-timeout-seconds must be greater than or equal to 0")
    return value


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


def _write_stderr(message: str) -> None:
    print(message, file=sys.stderr)


def _bootstrap_options(args: argparse.Namespace) -> dict:
    return {
        "lock_timeout_seconds": args.lock_timeout_seconds,
        "interactive": not args.non_interactive,
        "verbose": args.verbose,
        "recover_stale_lock": args.recover_stale_lock,
    }


def _emit_lock_wait_status(command: str, details: dict, *, verbose: bool) -> None:
    owner_command = details.get("command") or "unknown"
    owner_node_id = details.get("owner_node_id") or "unknown"
    message = f"Waiting for bootstrap lock before running {command}; active owner command={owner_command} node={owner_node_id}."
    if verbose:
        diagnostics: list[str] = []
        if details.get("pid") is not None:
            diagnostics.append(f"pid={details['pid']}")
        if details.get("lock_age_seconds") is not None:
            diagnostics.append(f"age={details['lock_age_seconds']:.2f}s")
        diagnostics.append(f"liveness={details.get('liveness') or 'unknown'}")
        message = f"{message} Diagnostics: {', '.join(diagnostics)}."
    _write_stderr(message)


def _emit_bootstrap_lock_error(error: SurfaceError) -> None:
    if error.code not in {"BOOTSTRAP_LOCK_TIMEOUT", "BOOTSTRAP_LOCK_SUSPECT"}:
        return
    details = error.details or {}
    diagnostics: list[str] = []
    if details.get("owner_node_id") is not None:
        diagnostics.append(f"owner_node_id={details['owner_node_id']}")
    if details.get("command") is not None:
        diagnostics.append(f"owner_command={details['command']}")
    if details.get("pid") is not None:
        diagnostics.append(f"pid={details['pid']}")
    if details.get("lock_age_seconds") is not None:
        diagnostics.append(f"lock_age_seconds={details['lock_age_seconds']:.2f}")
    if details.get("liveness") is not None:
        diagnostics.append(f"liveness={details['liveness']}")
    if details.get("recovery_hint"):
        diagnostics.append(f"recovery_hint={details['recovery_hint']}")
    if diagnostics:
        _write_stderr(f"{error.message}. {'; '.join(diagnostics)}")
        return
    _write_stderr(error.message)


def _prompt_stale_lock_recovery_confirmation(command: str) -> bool:
    # Keep stdout reserved for the final JSON envelope; interactive recovery stays on stderr/stdin.
    _write_stderr(
        f"Bootstrap lock looks stale before running {command}. Recover it now? [y/N]"
    )
    return input().strip().lower() in {"y", "yes"}


def _run_command(args: argparse.Namespace, bootstrap: NodeBootstrap) -> int:
    bootstrap_options = _bootstrap_options(args)
    # Every intermediate lock-status update is stderr-only so stdout stays machine-readable.
    wait_reporter = lambda command, details: _emit_lock_wait_status(command, details, verbose=args.verbose)

    if args.command == "init":
        state = bootstrap.open_or_init(wait_reporter=wait_reporter, **bootstrap_options)
        return _print_envelope(status="accepted", data=_state_payload(state), error=None)

    if args.command == "adopt":
        state = bootstrap.adopt_repo(wait_reporter=wait_reporter, **bootstrap_options)
        return _print_envelope(status="accepted", data=_state_payload(state), error=None)

    if args.command == "status":
        state = bootstrap.status(wait_reporter=wait_reporter, **bootstrap_options)
        return _print_envelope(status="ok", data=_state_payload(state), error=None)

    if not args.as_of:
        raise SurfaceError("INVALID_BOOTSTRAP_STATE", "read requires --as-of for deterministic output")

    state, entrypoint = bootstrap.read_entrypoint(as_of=args.as_of, wait_reporter=wait_reporter, **bootstrap_options)
    return _print_envelope(
        status="ok",
        data={
            **_state_payload(state),
            "project": state.adopted_project,
            "entrypoint": entrypoint,
        },
        error=None,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="capiforge_cli")
    parser.add_argument("command", choices=("init", "adopt", "status", "read"))
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--node-home")
    parser.add_argument("--as-of")
    parser.add_argument("--lock-timeout-seconds", type=_non_negative_float, default=DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--recover-stale-lock", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args: argparse.Namespace | None = None
    bootstrap: NodeBootstrap | None = None
    try:
        args = _build_parser().parse_args(argv)
        bootstrap = NodeBootstrap(repo_root=args.repo_root, node_home=args.node_home)
        return _run_command(args, bootstrap)
    except SurfaceError as exc:
        if (
            args is not None
            and bootstrap is not None
            and exc.code == "BOOTSTRAP_LOCK_SUSPECT"
            and not args.non_interactive
            and not args.recover_stale_lock
            and _prompt_stale_lock_recovery_confirmation(args.command)
        ):
            args.recover_stale_lock = True
            return _run_command(args, bootstrap)
        _emit_bootstrap_lock_error(exc)
        return _print_envelope(status="error", data=None, error=exc.to_dict())


if __name__ == "__main__":
    raise SystemExit(main())
