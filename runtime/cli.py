from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version
from typing import Sequence

from runtime import bootstrap_cli
from runtime.node import mcp_stdio
from runtime.version import __version__

BOOTSTRAP_COMMANDS = {"init", "adopt", "status", "read", "current"}
MCP_COMMANDS = {"serve"}


def _package_version() -> str:
    try:
        return version("capiforge")
    except PackageNotFoundError:
        return __version__


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capiforge")
    parser.add_argument("-V", "--version", action="version", version=f"%(prog)s {_package_version()}")
    subparsers = parser.add_subparsers(dest="command")

    mcp_parser = subparsers.add_parser("mcp", help="Run MCP surfaces")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("serve", help="Start the local MCP stdio server")
    audit_parser = subparsers.add_parser("audit", help="Create and publish adopted-project brief audits")
    audit_subparsers = audit_parser.add_subparsers(dest="audit_command")
    audit_create_parser = audit_subparsers.add_parser("create", help="Create a draft brief audit as a JSON envelope")
    audit_create_parser.add_argument("--title")
    audit_create_parser.add_argument("--content")
    audit_create_parser.add_argument("--as-of")
    audit_create_parser.add_argument("--repo-root")
    audit_create_parser.add_argument("--node-home")
    audit_create_parser.add_argument("--lock-timeout-seconds")
    audit_create_parser.add_argument("--recover-stale-lock", action="store_true")
    audit_publish_parser = audit_subparsers.add_parser("publish", help="Publish a draft brief audit as a JSON envelope")
    audit_publish_parser.add_argument("--audit-id")
    audit_publish_parser.add_argument("--as-of")
    audit_publish_parser.add_argument("--repo-root")
    audit_publish_parser.add_argument("--node-home")
    audit_publish_parser.add_argument("--lock-timeout-seconds")
    audit_publish_parser.add_argument("--recover-stale-lock", action="store_true")
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
    tui_parser = subparsers.add_parser("tui", help="Open the CapiForge terminal UI")
    tui_parser.add_argument("--repo-root")
    tui_parser.add_argument("--node-home")
    tui_parser.add_argument("--as-of")
    tui_parser.add_argument("--theme", choices=("neon", "notion", "light"))
    tui_parser.add_argument("--auto-refresh", type=int, choices=(0, 15, 30, 60))
    web_parser = subparsers.add_parser("web", help="Open the CapiForge web UI in your browser")
    web_parser.add_argument("--repo-root")
    web_parser.add_argument("--node-home")
    web_parser.add_argument("--as-of")
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8741)
    web_parser.add_argument("--no-open", action="store_true")
    web_parser.add_argument("--refresh", type=int, choices=(0, 15, 30, 60))

    return parser


def _handle_web(argv: Sequence[str]) -> int:
    try:
        from runtime.web.cli import main as web_main
    except ImportError:
        from runtime.web.deps import web_deps_install_hint

        print(web_deps_install_hint(), file=sys.stderr)
        return 1
    return web_main(argv, prog="capiforge web")


def _handle_tui(argv: Sequence[str]) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print("The TUI requires an interactive terminal.", file=sys.stderr)
        return 1
    try:
        from runtime.tui.shell import main as tui_main
    except ImportError:
        print(
            "TUI dependencies are missing. Reinstall with the optional [tui] extra:\n"
            "  uv tool install --reinstall --editable '.[tui]' --directory <repo>\n"
            "  or: pip install -e '.[tui]'",
            file=sys.stderr,
        )
        return 1
    return tui_main(argv, prog="capiforge tui")


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


def _handle_audit(argv: Sequence[str]) -> int:
    if len(argv) >= 2 and argv[0] == "audit" and argv[1] == "create":
        return bootstrap_cli.main(["audit-create", *argv[2:]], prog="capiforge")
    if len(argv) >= 2 and argv[0] == "audit" and argv[1] == "publish":
        return bootstrap_cli.main(["audit-publish", *argv[2:]], prog="capiforge")
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
    if raw_argv and raw_argv[0] == "audit":
        return _handle_audit(raw_argv)
    if raw_argv and raw_argv[0] == "tasks":
        return _handle_tasks(raw_argv)
    if raw_argv and raw_argv[0] == "tui":
        if "-h" in raw_argv[1:] or "--help" in raw_argv[1:]:
            _build_parser().parse_args(raw_argv)
            return 0
        return _handle_tui(raw_argv[1:])
    if raw_argv and raw_argv[0] == "web":
        if "-h" in raw_argv[1:] or "--help" in raw_argv[1:]:
            _build_parser().parse_args(raw_argv)
            return 0
        return _handle_web(raw_argv[1:])

    parser = _build_parser()
    args = parser.parse_args(raw_argv)
    if args.command == "mcp":
        parser.parse_args(["mcp", "--help"])
    if args.command == "tui":
        return _handle_tui(raw_argv[1:])
    if args.command == "web":
        return _handle_web(raw_argv[1:])
    parser.print_help()
    return 1
