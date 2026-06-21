from __future__ import annotations

from pathlib import Path

from runtime.node.bootstrap import NodeBootstrap


def resolve_web_db_paths(hub_repo_root: Path, hub_node_home: Path | None) -> list[Path]:
    paths: list[Path] = []
    bootstrap = NodeBootstrap(repo_root=hub_repo_root, node_home=hub_node_home)
    try:
        state = bootstrap.status(interactive=False)
        if state.state == "adopted" and state.node_db_path:
            hub_db = Path(state.node_db_path).resolve()
            if hub_db.exists():
                paths.append(hub_db)
    except Exception:
        pass

    from runtime.web.project_registry import load_registry

    for registered in load_registry(hub_repo_root).values():
        db_path = (registered.node_home / "node.sqlite3").resolve()
        if db_path.exists() and db_path not in paths:
            paths.append(db_path)
    return paths
