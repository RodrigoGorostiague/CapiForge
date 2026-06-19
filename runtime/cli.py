from __future__ import annotations

import argparse
import sys
from typing import Sequence

from runtime import bootstrap_cli
from runtime.node import mcp_stdio


BOOTSTRAP_COMMANDS = {"init", "adopt", "status", "read"}
MCP_COMMANDS = {"serve"}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="capiforge")
    subparsers = parser.add_subparsers(dest="command")

    mcp_parser = subparsers.add_parser("mcp", help="Run MCP surfaces")
    mcp_subparsers = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_subparsers.add_parser("serve", help="Start the local MCP stdio server")
    subparsers.add_parser("init", help="Initialize bootstrap state for the current repository")
    subparsers.add_parser("adopt", help="Adopt the current repository into bootstrap state")
    subparsers.add_parser("status", help="Read bootstrap status as a JSON envelope")
    subparsers.add_parser("read", help="Read deterministic project data as a JSON envelope")

    return parser


def _handle_mcp_serve(argv: Sequence[str]) -> int:
    return mcp_stdio.main(list(argv), prog="capiforge mcp serve")


def main(argv: Sequence[str] | None = None) -> int:
    raw_argv = list(argv) if argv is not None else sys.argv[1:]
    if raw_argv and raw_argv[0] in BOOTSTRAP_COMMANDS:
        return bootstrap_cli.main(raw_argv, prog="capiforge")
    if len(raw_argv) >= 2 and raw_argv[0] == "mcp" and raw_argv[1] == "serve":
        return _handle_mcp_serve(raw_argv[2:])

    parser = _build_parser()
    args = parser.parse_args(raw_argv)
    if args.command == "mcp":
        parser.parse_args(["mcp", "--help"])
    parser.print_help()
    return 1
