from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RegisteredProject:
    project_id: str
    repo_root: Path
    node_home: Path
    project_name: str


def registry_path(hub_repo_root: Path) -> Path:
    return hub_repo_root / ".capiforge" / "web" / "project-repos.json"


def _parse_registry_entry(project_id: str, entry: object) -> RegisteredProject | None:
    if not isinstance(entry, dict):
        return None
    repo_root_raw = entry.get("repo_root")
    if not repo_root_raw or not isinstance(repo_root_raw, str):
        return None
    try:
        repo_root = Path(repo_root_raw).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    if not repo_root.is_dir():
        return None
    node_home_raw = entry.get("node_home") or str(repo_root / ".capiforge" / "node")
    if not isinstance(node_home_raw, str):
        return None
    try:
        node_home = Path(node_home_raw).expanduser().resolve()
    except (OSError, RuntimeError):
        return None
    project_name = entry.get("project_name")
    if not project_name or not isinstance(project_name, str):
        project_name = repo_root.name
    return RegisteredProject(
        project_id=project_id,
        repo_root=repo_root,
        node_home=node_home,
        project_name=project_name,
    )


def load_registry(hub_repo_root: Path, *, prune_invalid: bool = False) -> dict[str, RegisteredProject]:
    path = registry_path(hub_repo_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw_projects = payload.get("projects", {})
    if not isinstance(raw_projects, dict):
        return {}
    projects: dict[str, RegisteredProject] = {}
    invalid_ids: list[str] = []
    for project_id, entry in raw_projects.items():
        if not isinstance(project_id, str) or not project_id:
            continue
        parsed = _parse_registry_entry(project_id, entry)
        if parsed is None:
            invalid_ids.append(project_id)
            continue
        projects[project_id] = parsed
    if prune_invalid and invalid_ids:
        cleaned = {
            project_id: {
                "repo_root": str(entry.repo_root),
                "node_home": str(entry.node_home),
                "project_name": entry.project_name,
            }
            for project_id, entry in projects.items()
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"projects": cleaned}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return projects


def list_registered_projects(hub_repo_root: Path) -> tuple[RegisteredProject, ...]:
    return tuple(load_registry(hub_repo_root).values())


def save_registry_entry(
    hub_repo_root: Path,
    *,
    project_id: str,
    repo_root: Path,
    node_home: Path,
    project_name: str,
) -> None:
    path = registry_path(hub_repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict = {"projects": {}}
    if path.exists():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {"projects": {}}
    payload.setdefault("projects", {})
    payload["projects"][project_id] = {
        "repo_root": str(repo_root.resolve()),
        "node_home": str(node_home.resolve()),
        "project_name": project_name,
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def remove_registry_entry(hub_repo_root: Path, project_id: str) -> bool:
    path = registry_path(hub_repo_root)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    projects = payload.get("projects", {})
    if not isinstance(projects, dict) or project_id not in projects:
        return False
    del projects[project_id]
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return True


def resolve_project_repo(hub_repo_root: Path, project_id: str | None) -> RegisteredProject | None:
    if not project_id:
        return None
    return load_registry(hub_repo_root).get(project_id)


def active_project_repo_path(
    hub_repo_root: Path,
    hub_node_home: Path | None,
    project_id: str | None,
) -> Path:
    registered = resolve_project_repo(hub_repo_root, project_id)
    if registered is not None:
        return registered.repo_root
    return hub_repo_root.resolve()


def content_repo_for_project(hub_repo_root: Path, hub_node_home: Path | None, project_id: str | None) -> tuple[Path, Path | None]:
    registered = resolve_project_repo(hub_repo_root, project_id)
    if registered is not None:
        return registered.repo_root, registered.node_home
    return hub_repo_root, hub_node_home
