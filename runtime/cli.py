from __future__ import annotations

import argparse
import sys
from typing import Sequence

from runtime import bootstrap_cli
from runtime.node import mcp_stdio
BOOTSTRAP_COMMANDS = {"init", "adopt", "status", "read", "current"}
MCP_COMMANDS = {"serve"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capiforge")
    subparsers = parser.add_subparsers(dest="command")

    mcp_parser = subparsers.add_parser("mcp", help="Run MCP surfaces")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("serve", help="Start the local MCP stdio server")
    tasks_parser = subparsers.add_parser("tasks", help="Read task queues, execution claims, and lifecycle wrappers")
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command")
    tasks_subparsers.add_parser("ready", help="Read the adopted ready task queue as a JSON envelope")
    claim_parser = tasks_subparsers.add_parser("claim", help="Claim an adopted ready task as a JSON envelope")
    claim_parser.add_argument("--task-id")
    claim_parser.add_argument("--plan")
    claim_parser.add_argument("--lease-minutes")
    claim_parser.add_argument("--repo-root")
    claim_parser.add_argument("--node-home")
    claim_parser.add_argument("--lock-timeout-seconds")
    claim_parser.add_argument("--recover-stale-lock", action="store_true")
    start_parser = tasks_subparsers.add_parser("start", help="Reconcile owner-local same-project lifecycle work into an adopted in-progress task as a JSON envelope")
    start_parser.add_argument("--lifecycle-key")
    start_parser.add_argument("--plan")
    start_parser.add_argument("--lease-minutes")
    start_parser.add_argument("--origin-audit-id")
    start_parser.add_argument("--description")
    start_parser.add_argument("--priority")
    start_parser.add_argument("--effort")
    start_parser.add_argument("--risk")
    start_parser.add_argument("--task-type")
    start_parser.add_argument("--justification-json")
    start_parser.add_argument("--execution-context-json")
    start_parser.add_argument("--repo-root")
    start_parser.add_argument("--node-home")
    start_parser.add_argument("--lock-timeout-seconds")
    start_parser.add_argument("--recover-stale-lock", action="store_true")
    finish_parser = tasks_subparsers.add_parser("finish", help="Close owner-local adopted lifecycle work to done or blocked as a JSON envelope")
    finish_parser.add_argument("--lifecycle-key")
    finish_parser.add_argument("--outcome")
    finish_parser.add_argument("--as-of")
    finish_parser.add_argument("--done-result")
    finish_parser.add_argument("--done-artifacts")
    finish_parser.add_argument("--done-references")
    finish_parser.add_argument("--done-expected-impact")
    finish_parser.add_argument("--blocked-reason")
    finish_parser.add_argument("--blocked-evidence")
    finish_parser.add_argument("--blocked-next-step")
    finish_parser.add_argument("--repo-root")
    finish_parser.add_argument("--node-home")
    finish_parser.add_argument("--lock-timeout-seconds")
    finish_parser.add_argument("--recover-stale-lock", action="store_true")
    subparsers.add_parser("init", help="Initialize bootstrap state for the current repository")
    subparsers.add_parser("adopt", help="Adopt the current repository into bootstrap state")
    subparsers.add_parser("status", help="Read bootstrap status as a JSON envelope")
    subparsers.add_parser("read", help="Read deterministic project data as a JSON envelope")
    subparsers.add_parser("current", help="Read the adopted project summary as a JSON envelope")

    return parser


def _handle_mcp_serve(argv: Sequence[str]) -> int:
    return mcp_stdio.main(list(argv), prog="capiforge mcp serve")
def _handle_tasks(argv: Sequence[str]) -> int:
    if len(argv) >= 2 and argv[0] == "tasks" and argv[1] == "ready":
        return bootstrap_cli.main(["tasks-ready", *argv[2:]], prog="capiforge")
    if len(argv) >= 2 and argv[0] == "tasks" and argv[1] == "claim":
        return bootstrap_cli.main(["tasks-claim", *argv[2:]], prog="capiforge")
    if len(argv) >= 2 and argv[0] == "tasks" and argv[1] == "start":
        return bootstrap_cli.main(["tasks-start", *argv[2:]], prog="capiforge")
    if len(argv) >= 2 and argv[0] == "tasks" and argv[1] == "finish":
        return bootstrap_cli.main(["tasks-finish", *argv[2:]], prog="capiforge")
    parser = _build_parser()
    parser.parse_args(list(argv))
    parser.print_help()
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] in BOOTSTRAP_COMMANDS:
        return bootstrap_cli.main(raw_argv, prog="capiforge")
    if len(raw_argv) >= 2 and raw_argv[0] == "mcp" and raw_argv[1] == "serve":
        return _handle_mcp_serve(raw_argv[2:])
    if raw_argv and raw_argv[0] == "tasks":
        return _handle_tasks(raw_argv)

    parser = _build_parser()
    args = parser.parse_args(raw_argv)
    if args.command == "mcp":
        parser.parse_args(["mcp", "--help"])
    parser.print_help()
    return 1
