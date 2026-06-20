from __future__ import annotations

import argparse
import json
import sys

from runtime.node.bootstrap import DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS, BootstrapState, NodeBootstrap
from runtime.node.current import claim_ready_task, read_current, read_ready_tasks, state_payload, tasks_reconcile_finish, tasks_reconcile_start
from runtime.shared.errors import SurfaceError


LOCAL_AGENT_ID = "capiforge-cli"
LOCAL_SESSION_ID = "capiforge-cli-current"


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SurfaceError("INVALID_ARGUMENTS", message)


def _non_negative_float(raw: str) -> float:
    value = float(raw)
    if value < 0:
        raise argparse.ArgumentTypeError("--lock-timeout-seconds must be greater than or equal to 0")
    return value


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return value


def _json_object(raw: str, *, field_name: str) -> dict:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:  # pragma: no cover - argparse surface
        raise SurfaceError("INVALID_ARGUMENTS", f"{field_name} must be valid JSON") from exc
    if not isinstance(payload, dict):
        raise SurfaceError("INVALID_ARGUMENTS", f"{field_name} must decode to a JSON object")
    return payload


def _state_payload(state: BootstrapState) -> dict:
    return state_payload(state)


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
    _write_stderr(f"Bootstrap lock looks stale before running {command}. Recover it now? [y/N]")
    return input().strip().lower() in {"y", "yes"}


def _run_command(args: argparse.Namespace, bootstrap: NodeBootstrap) -> int:
    bootstrap_options = _bootstrap_options(args)
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

    if args.command == "current":
        current = _read_current(
            bootstrap,
            as_of=args.as_of,
            ready_limit=args.ready_limit,
            wait_reporter=wait_reporter,
            **bootstrap_options,
        )
        return _print_envelope(status="ok", data=current, error=None)

    if args.command == "tasks-ready":
        ready_tasks = _read_ready_tasks(
            bootstrap,
            as_of=args.as_of,
            limit=args.limit,
            wait_reporter=wait_reporter,
            **bootstrap_options,
        )
        return _print_envelope(status="ok", data=ready_tasks, error=None)

    if args.command == "tasks-claim":
        if not args.task_id:
            raise SurfaceError("INVALID_ARGUMENTS", "tasks-claim requires --task-id")
        if not args.plan:
            raise SurfaceError("INVALID_ARGUMENTS", "tasks-claim requires --plan")
        claimed_task = _claim_ready_task(
            bootstrap,
            task_id=args.task_id,
            plan=args.plan,
            lease_minutes=args.lease_minutes,
            wait_reporter=wait_reporter,
            **bootstrap_options,
        )
        return _print_envelope(status="claimed", data=claimed_task, error=None)

    if args.command == "tasks-start":
        if not args.lifecycle_key:
            raise SurfaceError("INVALID_ARGUMENTS", "tasks-start requires --lifecycle-key")
        if not args.plan:
            raise SurfaceError("INVALID_ARGUMENTS", "tasks-start requires --plan")
        started_task = _reconcile_start_task(
            bootstrap,
            lifecycle_key=args.lifecycle_key,
            plan=args.plan,
            lease_minutes=args.lease_minutes,
            origin_audit_id=args.origin_audit_id,
            description=args.description,
            priority=args.priority,
            effort=args.effort,
            risk=args.risk,
            task_type=args.task_type,
            justification_json=args.justification_json,
            execution_context_json=args.execution_context_json,
            wait_reporter=wait_reporter,
            **bootstrap_options,
        )
        return _print_envelope(status="accepted", data=started_task, error=None)

    if args.command == "tasks-finish":
        if not args.lifecycle_key:
            raise SurfaceError("INVALID_ARGUMENTS", "tasks-finish requires --lifecycle-key")
        if not args.outcome:
            raise SurfaceError("INVALID_ARGUMENTS", "tasks-finish requires --outcome")
        finished_task = _reconcile_finish_task(
            bootstrap,
            lifecycle_key=args.lifecycle_key,
            outcome=args.outcome,
            as_of=args.as_of,
            done_result=args.done_result,
            done_artifacts=args.done_artifacts,
            done_references=args.done_references,
            done_expected_impact=args.done_expected_impact,
            blocked_reason=args.blocked_reason,
            blocked_evidence=args.blocked_evidence,
            blocked_next_step=args.blocked_next_step,
            wait_reporter=wait_reporter,
            **bootstrap_options,
        )
        return _print_envelope(status="accepted", data=finished_task, error=None)

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


def _read_current(
    bootstrap: NodeBootstrap,
    *,
    as_of: str | None,
    ready_limit: int,
    lock_timeout_seconds: float,
    interactive: bool,
    verbose: bool,
    recover_stale_lock: bool,
    wait_reporter,
) -> dict:
    del interactive, verbose
    return read_current(
        bootstrap,
        as_of=as_of,
        ready_limit=ready_limit,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=LOCAL_AGENT_ID,
        session_id=LOCAL_SESSION_ID,
        command="current",
        wait_reporter=wait_reporter,
    )


def _read_ready_tasks(
    bootstrap: NodeBootstrap,
    *,
    as_of: str | None,
    limit: int,
    lock_timeout_seconds: float,
    interactive: bool,
    verbose: bool,
    recover_stale_lock: bool,
    wait_reporter,
) -> dict:
    del interactive, verbose
    return read_ready_tasks(
        bootstrap,
        as_of=as_of,
        limit=limit,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=LOCAL_AGENT_ID,
        session_id=LOCAL_SESSION_ID,
        command="tasks_ready",
        wait_reporter=wait_reporter,
    )


def _claim_ready_task(
    bootstrap: NodeBootstrap,
    *,
    task_id: str,
    plan: str,
    lease_minutes: int,
    lock_timeout_seconds: float,
    interactive: bool,
    verbose: bool,
    recover_stale_lock: bool,
    wait_reporter,
) -> dict:
    del interactive, verbose
    return claim_ready_task(
        bootstrap,
        task_id=task_id,
        plan=plan,
        lease_minutes=lease_minutes,
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=LOCAL_AGENT_ID,
        session_id=LOCAL_SESSION_ID,
        command="tasks_claim",
        wait_reporter=wait_reporter,
    )


def _reconcile_start_task(
    bootstrap: NodeBootstrap,
    *,
    lifecycle_key: str,
    plan: str,
    lease_minutes: int,
    origin_audit_id: str | None,
    description: str | None,
    priority: str | None,
    effort: str | None,
    risk: str | None,
    task_type: str | None,
    justification_json: str | None,
    execution_context_json: str | None,
    lock_timeout_seconds: float,
    interactive: bool,
    verbose: bool,
    recover_stale_lock: bool,
    wait_reporter,
) -> dict:
    del interactive, verbose
    justification = _json_object(justification_json, field_name="--justification-json") if justification_json else None
    execution_context = _json_object(execution_context_json, field_name="--execution-context-json") if execution_context_json else None
    return tasks_reconcile_start(
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
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=LOCAL_AGENT_ID,
        session_id=LOCAL_SESSION_ID,
        command="tasks_reconcile_start",
        wait_reporter=wait_reporter,
    )


def _reconcile_finish_task(
    bootstrap: NodeBootstrap,
    *,
    lifecycle_key: str,
    outcome: str,
    as_of: str | None,
    done_result: str | None,
    done_artifacts: str | None,
    done_references: str | None,
    done_expected_impact: str | None,
    blocked_reason: str | None,
    blocked_evidence: str | None,
    blocked_next_step: str | None,
    lock_timeout_seconds: float,
    interactive: bool,
    verbose: bool,
    recover_stale_lock: bool,
    wait_reporter,
) -> dict:
    del interactive, verbose
    return tasks_reconcile_finish(
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
        lock_timeout_seconds=lock_timeout_seconds,
        recover_stale_lock=recover_stale_lock,
        agent_id=LOCAL_AGENT_ID,
        session_id=LOCAL_SESSION_ID,
        command="tasks_reconcile_finish",
        wait_reporter=wait_reporter,
    )


def build_parser(*, prog: str = "capiforge", repo_root_default: str = ".") -> argparse.ArgumentParser:
    parser = JsonArgumentParser(
        prog=prog,
        description=(
            "Owner-local adopted-project JSON CLI for bootstrap state, ready-task claims, "
            "and lifecycle start/finish reconciliation."
        ),
        epilog=(
            "Lifecycle commands:\n"
            "  tasks-start   Reconcile owner-local same-project lifecycle work into an adopted in-progress task.\n"
            "  tasks-finish  Close owner-local adopted lifecycle work to done or blocked when the active claim is still valid."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("command", choices=("init", "adopt", "status", "read", "current", "tasks-ready", "tasks-claim", "tasks-start", "tasks-finish"))
    parser.add_argument("--repo-root", default=repo_root_default)
    parser.add_argument("--node-home")
    parser.add_argument("--as-of")
    parser.add_argument("--task-id")
    parser.add_argument("--lifecycle-key", help="Deterministic lifecycle key for same-project task reconciliation.")
    parser.add_argument("--outcome", help="Lifecycle closeout outcome: done or blocked.")
    parser.add_argument("--plan", help="Claim plan recorded when lifecycle work starts.")
    parser.add_argument("--origin-audit-id", help="Published origin audit required for lifecycle auto-create on miss.")
    parser.add_argument("--description", help="Task description used only when lifecycle start creates a new task.")
    parser.add_argument("--priority")
    parser.add_argument("--effort")
    parser.add_argument("--risk")
    parser.add_argument("--task-type")
    parser.add_argument("--justification-json", help="JSON object with lifecycle task justification metadata.")
    parser.add_argument("--execution-context-json", help="JSON object that must stay within the adopted project.")
    parser.add_argument("--done-result", help="Required done summary for lifecycle finish --outcome done.")
    parser.add_argument("--done-artifacts", help="Required done artifacts reference for lifecycle finish --outcome done.")
    parser.add_argument("--done-references", help="Required done linked references for lifecycle finish --outcome done.")
    parser.add_argument("--done-expected-impact", help="Required done expected impact for lifecycle finish --outcome done.")
    parser.add_argument("--blocked-reason", help="Required blocked reason for lifecycle finish --outcome blocked.")
    parser.add_argument("--blocked-evidence", help="Required blocked evidence reference for lifecycle finish --outcome blocked.")
    parser.add_argument("--blocked-next-step", help="Required blocked next step for lifecycle finish --outcome blocked.")
    parser.add_argument("--lease-minutes", type=_positive_int, default=5)
    parser.add_argument("--ready-limit", type=_positive_int, default=10)
    parser.add_argument("--limit", type=_positive_int, default=20)
    parser.add_argument("--lock-timeout-seconds", type=_non_negative_float, default=DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS)
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--recover-stale-lock", action="store_true")
    return parser


def main(argv: list[str] | None = None, *, prog: str = "capiforge", repo_root_default: str = ".") -> int:
    args: argparse.Namespace | None = None
    bootstrap: NodeBootstrap | None = None
    try:
        args = build_parser(prog=prog, repo_root_default=repo_root_default).parse_args(argv)
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
