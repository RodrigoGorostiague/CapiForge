from __future__ import annotations

import argparse
import json
from pathlib import Path

SERVER_NAME = "capiforge"


def build_mcp_argv(*, capiforge_bin: str, repo_root: str, node_home: str) -> list[str]:
    return [
        capiforge_bin,
        "mcp",
        "serve",
        "--repo-root",
        str(Path(repo_root).resolve()),
        "--node-home",
        str(Path(node_home).resolve()),
    ]


def build_cursor_server_entry(*, capiforge_bin: str, repo_root: str, node_home: str) -> dict:
    argv = build_mcp_argv(capiforge_bin=capiforge_bin, repo_root=repo_root, node_home=node_home)
    return {"command": argv[0], "args": argv[1:]}


def build_opencode_server_entry(*, capiforge_bin: str, repo_root: str, node_home: str) -> dict:
    return {
        "command": build_mcp_argv(capiforge_bin=capiforge_bin, repo_root=repo_root, node_home=node_home),
        "type": "local",
        "enabled": True,
    }


def _load_json_object(path: Path) -> dict:
    if not path.exists():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return loaded


def _write_json_object(path: Path, payload: dict) -> Path:
    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def merge_cursor_config(*, config_path: Path, server_entry: dict, server_name: str = SERVER_NAME) -> dict:
    config = _load_json_object(config_path)
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise ValueError("mcpServers must be a JSON object")
    servers[server_name] = server_entry
    return config


def merge_opencode_config(*, config_path: Path, server_entry: dict, server_name: str = SERVER_NAME) -> dict:
    config = _load_json_object(config_path)
    servers = config.setdefault("mcp", {})
    if not isinstance(servers, dict):
        raise ValueError("mcp must be a JSON object")
    servers[server_name] = server_entry
    return config


def write_cursor_config(*, config_path: Path, capiforge_bin: str, repo_root: str, node_home: str) -> Path:
    entry = build_cursor_server_entry(
        capiforge_bin=capiforge_bin,
        repo_root=repo_root,
        node_home=node_home,
    )
    merged = merge_cursor_config(config_path=config_path, server_entry=entry)
    return _write_json_object(config_path, merged)


def write_opencode_config(*, config_path: Path, capiforge_bin: str, repo_root: str, node_home: str) -> Path:
    entry = build_opencode_server_entry(
        capiforge_bin=capiforge_bin,
        repo_root=repo_root,
        node_home=node_home,
    )
    merged = merge_opencode_config(config_path=config_path, server_entry=entry)
    return _write_json_object(config_path, merged)


def remove_cursor_config(*, config_path: Path, server_name: str = SERVER_NAME) -> bool:
    if not config_path.exists():
        return False
    config = _load_json_object(config_path)
    servers = config.get("mcpServers")
    if not isinstance(servers, dict) or server_name not in servers:
        return False
    del servers[server_name]
    if not servers:
        config.pop("mcpServers", None)
    _write_json_object(config_path, config)
    return True


def remove_opencode_config(*, config_path: Path, server_name: str = SERVER_NAME) -> bool:
    if not config_path.exists():
        return False
    config = _load_json_object(config_path)
    servers = config.get("mcp")
    if not isinstance(servers, dict) or server_name not in servers:
        return False
    del servers[server_name]
    if not servers:
        config.pop("mcp", None)
    _write_json_object(config_path, config)
    return True


def integration_present(*, config_path: Path, target: str, server_name: str = SERVER_NAME) -> bool:
    if not config_path.exists():
        return False
    config = _load_json_object(config_path)
    if target == "cursor":
        servers = config.get("mcpServers", {})
        return isinstance(servers, dict) and server_name in servers
    if target == "opencode":
        servers = config.get("mcp", {})
        return isinstance(servers, dict) and server_name in servers
    raise ValueError(f"unsupported target: {target}")


def verify_cursor_config(*, config_path: Path, capiforge_bin: str, repo_root: str, node_home: str) -> list[str]:
    issues: list[str] = []
    if not config_path.exists():
        issues.append(f"missing Cursor config: {config_path}")
        return issues
    config = _load_json_object(config_path)
    servers = config.get("mcpServers", {})
    entry = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        issues.append(f"Cursor config missing {SERVER_NAME} entry")
        return issues
    command = entry.get("command")
    args = entry.get("args", [])
    if command != capiforge_bin:
        issues.append("Cursor command does not match installed capiforge binary")
    expected_args = build_mcp_argv(capiforge_bin=capiforge_bin, repo_root=repo_root, node_home=node_home)[1:]
    if list(args) != expected_args:
        issues.append("Cursor args do not match expected capiforge mcp serve invocation")
    return issues


def verify_opencode_config(*, config_path: Path, capiforge_bin: str, repo_root: str, node_home: str) -> list[str]:
    issues: list[str] = []
    if not config_path.exists():
        issues.append(f"missing OpenCode config: {config_path}")
        return issues
    config = _load_json_object(config_path)
    servers = config.get("mcp", {})
    entry = servers.get(SERVER_NAME) if isinstance(servers, dict) else None
    if not isinstance(entry, dict):
        issues.append(f"OpenCode config missing {SERVER_NAME} entry")
        return issues
    command = entry.get("command", [])
    expected = build_mcp_argv(capiforge_bin=capiforge_bin, repo_root=repo_root, node_home=node_home)
    if list(command) != expected:
        issues.append("OpenCode command array does not match expected capiforge mcp serve invocation")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Merge or remove CapiForge integration configuration.")
    parser.add_argument("action", choices=("write-cursor", "write-opencode", "remove-cursor", "remove-opencode"))
    parser.add_argument("--config-path", required=True)
    parser.add_argument("--command", default="")
    parser.add_argument("--repo-root", default="")
    parser.add_argument("--node-home", default="")
    args = parser.parse_args(argv)
    path = Path(args.config_path)

    if args.action == "write-cursor":
        write_cursor_config(
            config_path=path,
            capiforge_bin=args.command,
            repo_root=args.repo_root,
            node_home=args.node_home,
        )
    elif args.action == "write-opencode":
        write_opencode_config(
            config_path=path,
            capiforge_bin=args.command,
            repo_root=args.repo_root,
            node_home=args.node_home,
        )
    elif args.action == "remove-cursor":
        remove_cursor_config(config_path=path)
    elif args.action == "remove-opencode":
        remove_opencode_config(config_path=path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
