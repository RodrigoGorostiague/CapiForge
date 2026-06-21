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


def load_registry(hub_repo_root: Path) -> dict[str, RegisteredProject]:
    path = registry_path(hub_repo_root)
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    projects: dict[str, RegisteredProject] = {}
    for project_id, entry in payload.get("projects", {}).items():
        if not isinstance(entry, dict):
            continue
        repo_root = entry.get("repo_root")
        if not repo_root:
            continue
        node_home = entry.get("node_home") or str(Path(repo_root) / ".capiforge" / "node")
        projects[project_id] = RegisteredProject(
            project_id=project_id,
            repo_root=Path(repo_root).resolve(),
            node_home=Path(node_home).resolve(),
            project_name=str(entry.get("project_name") or Path(repo_root).name),
        )
    return projects


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


def resolve_project_repo(hub_repo_root: Path, project_id: str | None) -> RegisteredProject | None:
    if not project_id:
        return None
    return load_registry(hub_repo_root).get(project_id)


def content_repo_for_project(hub_repo_root: Path, hub_node_home: Path | None, project_id: str | None) -> tuple[Path, Path | None]:
    registered = resolve_project_repo(hub_repo_root, project_id)
    if registered is not None:
        return registered.repo_root, registered.node_home
    return hub_repo_root, hub_node_home
