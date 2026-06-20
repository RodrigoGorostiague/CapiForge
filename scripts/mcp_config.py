from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.integration_config import (
    SERVER_NAME,
    build_cursor_server_entry,
    write_cursor_config,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write or merge CapiForge MCP editor configuration.")
    parser.add_argument("--editor", choices=("cursor",), required=True)
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--command", required=True)
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--node-home", required=True)
    parser.add_argument("--server-name", default=SERVER_NAME)
    args = parser.parse_args(argv)

    entry = build_cursor_server_entry(
        command=args.command,
        repo_root=str(Path(args.repo_root).resolve()),
        node_home=str(Path(args.node_home).resolve()),
    )
    write_cursor_config(
        config_path=Path(args.config_path),
        capiforge_bin=args.command,
        repo_root=str(Path(args.repo_root).resolve()),
        node_home=str(Path(args.node_home).resolve()),
    )
    print(json.dumps(entry, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
