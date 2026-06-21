from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

SERVER_NAME = "capiforge"
OPENCODE_SKILLS_DIRNAME = "skills"
OPENCODE_AUTOMATION_SKILL_NAME = "capiforge-record-completed-work"
OPENCODE_AUTOMATION_SKILL_FILENAME = "SKILL.md"
CURSOR_SKILLS_DIRNAME = "skills"
CAPIFORGE_SKILL_NAMES = (
    "capiforge-publish-milestone",
    "capiforge-pickup-task",
    "capiforge-start-task",
    "capiforge-close-task",
    "capiforge-data-layer",
    "capiforge-record-completed-work",
)


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


def opencode_skill_root(*, config_path: Path) -> Path:
    return config_path.resolve().parent / OPENCODE_SKILLS_DIRNAME


def opencode_installed_skill_dir(*, config_path: Path) -> Path:
    return opencode_skill_root(config_path=config_path) / OPENCODE_AUTOMATION_SKILL_NAME


def opencode_installed_skill_file(*, config_path: Path) -> Path:
    return opencode_installed_skill_dir(config_path=config_path) / OPENCODE_AUTOMATION_SKILL_FILENAME


def repo_automation_skill_dir(*, repo_root: str) -> Path:
    project_skill = Path(repo_root).resolve() / "skills" / OPENCODE_AUTOMATION_SKILL_NAME
    if project_skill.exists():
        return project_skill
    from runtime.paths import skills_root

    share_skill = skills_root() / OPENCODE_AUTOMATION_SKILL_NAME
    if share_skill.exists():
        return share_skill
    return project_skill


def repo_skill_dir(*, repo_root: str, skill_name: str) -> Path:
    project_skill = Path(repo_root).resolve() / "skills" / skill_name
    if project_skill.exists():
        return project_skill
    from runtime.paths import skills_root

    share_skill = skills_root() / skill_name
    if share_skill.exists():
        return share_skill
    return project_skill


def cursor_installed_skills_root(*, repo_root: str) -> Path:
    return Path(repo_root).resolve() / ".cursor" / CURSOR_SKILLS_DIRNAME


def cursor_installed_skill_dir(*, repo_root: str, skill_name: str) -> Path:
    return cursor_installed_skills_root(repo_root=repo_root) / skill_name


def write_cursor_skills_artifacts(*, repo_root: str) -> list[Path]:
    installed: list[Path] = []
    for skill_name in CAPIFORGE_SKILL_NAMES:
        source_dir = repo_skill_dir(repo_root=repo_root, skill_name=skill_name)
        if not source_dir.exists():
            raise FileNotFoundError(f"missing Cursor skill source: {source_dir}")
        target_dir = cursor_installed_skill_dir(repo_root=repo_root, skill_name=skill_name)
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, target_dir)
        installed.append(target_dir / OPENCODE_AUTOMATION_SKILL_FILENAME)
    return installed


def remove_cursor_skills_artifacts(*, repo_root: str) -> bool:
    root = cursor_installed_skills_root(repo_root=repo_root)
    if not root.exists():
        return False
    for skill_name in CAPIFORGE_SKILL_NAMES:
        target_dir = root / skill_name
        if target_dir.exists():
            shutil.rmtree(target_dir)
    if root.exists() and not any(root.iterdir()):
        root.rmdir()
    return True


def verify_cursor_skills(*, repo_root: str) -> list[str]:
    issues: list[str] = []
    for skill_name in CAPIFORGE_SKILL_NAMES:
        skill_file = cursor_installed_skill_dir(repo_root=repo_root, skill_name=skill_name) / OPENCODE_AUTOMATION_SKILL_FILENAME
        if not skill_file.exists():
            issues.append(f"missing Cursor skill artifact: {skill_file}")
    return issues


def write_opencode_automation_artifact(*, config_path: Path, repo_root: str) -> Path:
    source_dir = repo_automation_skill_dir(repo_root=repo_root)
    if not source_dir.exists():
        raise FileNotFoundError(f"missing OpenCode automation artifact source: {source_dir}")
    target_dir = opencode_installed_skill_dir(config_path=config_path)
    if target_dir.exists():
        shutil.rmtree(target_dir)
    target_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source_dir, target_dir)
    return target_dir / OPENCODE_AUTOMATION_SKILL_FILENAME


def remove_opencode_automation_artifact(*, config_path: Path) -> bool:
    target_dir = opencode_installed_skill_dir(config_path=config_path)
    if not target_dir.exists():
        return False
    shutil.rmtree(target_dir)
    skills_root = target_dir.parent
    if skills_root.exists() and not any(skills_root.iterdir()):
        skills_root.rmdir()
    return True


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
    skills = config.setdefault("skills", {})
    if not isinstance(skills, dict):
        raise ValueError("skills must be a JSON object")
    skill_paths = skills.setdefault("paths", [])
    if not isinstance(skill_paths, list):
        raise ValueError("skills.paths must be a JSON array")
    expected_skill_root = str(opencode_skill_root(config_path=config_path))
    if expected_skill_root not in skill_paths:
        skill_paths.append(expected_skill_root)
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
    changed = False
    servers = config.get("mcp")
    if isinstance(servers, dict) and server_name in servers:
        del servers[server_name]
        changed = True
        if not servers:
            config.pop("mcp", None)
    skills = config.get("skills")
    if isinstance(skills, dict):
        skill_paths = skills.get("paths")
        expected_skill_root = str(opencode_skill_root(config_path=config_path))
        if isinstance(skill_paths, list) and expected_skill_root in skill_paths:
            skills["paths"] = [value for value in skill_paths if value != expected_skill_root]
            changed = True
            if not skills["paths"]:
                skills.pop("paths", None)
        if not skills:
            config.pop("skills", None)
    if not changed:
        return False
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
    skills = config.get("skills", {})
    skill_paths = skills.get("paths", []) if isinstance(skills, dict) else []
    expected_skill_root = str(opencode_skill_root(config_path=config_path))
    if expected_skill_root not in skill_paths:
        issues.append("OpenCode skills.paths is missing the CapiForge automation skill root")
    skill_file = opencode_installed_skill_file(config_path=config_path)
    if not skill_file.exists():
        issues.append(f"missing OpenCode automation artifact: {skill_file}")
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
