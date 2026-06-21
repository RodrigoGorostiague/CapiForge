#!/usr/bin/env python3
"""Index docs/**/*.md into local_documents for the adopted project."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore
from runtime.web.project_registry import content_repo_for_project, resolve_project_repo


def document_id_for_path(project_id: str, storage_path: str) -> str:
    digest = uuid5(NAMESPACE_URL, f"local_document:{project_id}:{storage_path}").hex[:16]
    return f"doc_{digest}"


def collect_markdown_files(docs_root: Path) -> list[Path]:
    if not docs_root.is_dir():
        return []
    return sorted(path for path in docs_root.rglob("*.md") if path.is_file())


def index_local_docs(
    *,
    repo_root: Path,
    node_home: Path | None,
    project_id: str | None,
    docs_dir: Path,
    dry_run: bool,
) -> dict:
    content_root, content_node_home = content_repo_for_project(repo_root, node_home, project_id)
    bootstrap = NodeBootstrap(repo_root=content_root, node_home=content_node_home)
    state = bootstrap.status(interactive=False)
    if state.state != "adopted" or not state.adopted_project:
        raise SystemExit("Repository is not adopted. Run capiforge adopt first.")

    adopted_project_id = project_id or state.adopted_project["project_id"]
    docs_root = docs_dir if docs_dir.is_absolute() else content_root / docs_dir
    markdown_files = collect_markdown_files(docs_root)
    if not markdown_files:
        return {
            "project_id": adopted_project_id,
            "docs_root": str(docs_root),
            "indexed": 0,
            "created": 0,
            "updated": 0,
            "paths": [],
        }

    store = NodeStore.from_file(state.node_db_path)
    try:
        created = 0
        updated = 0
        paths: list[dict[str, str]] = []
        for path in markdown_files:
            storage_path = path.relative_to(content_root).as_posix()
            document_id = document_id_for_path(adopted_project_id, storage_path)
            existing = store.get_local_document_by_path(adopted_project_id, storage_path)
            if existing:
                updated += 1
            else:
                created += 1
            if not dry_run:
                store.upsert_local_document(document_id, adopted_project_id, storage_path)
            paths.append({"document_id": document_id, "storage_path": storage_path})
        if not dry_run:
            store.db.commit()
    finally:
        store.close()

    return {
        "project_id": adopted_project_id,
        "docs_root": str(docs_root),
        "indexed": len(paths),
        "created": created,
        "updated": updated,
        "dry_run": dry_run,
        "paths": paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Index docs/**/*.md into local_documents.")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help="Hub repo root (default: CapiForge checkout)")
    parser.add_argument("--project-id", help="Project id (default: bootstrap adopted project)")
    parser.add_argument("--docs-dir", type=Path, default=Path("docs"), help="Docs directory relative to content repo")
    parser.add_argument("--dry-run", action="store_true", help="Report paths without writing to SQLite")
    args = parser.parse_args()

    hub_root = args.repo_root.resolve()
    hub_bootstrap = NodeBootstrap(repo_root=hub_root)
    hub_state = hub_bootstrap.status(interactive=False)
    hub_node_home = hub_state.node_home if hub_state.state != "uninitialized" else None

    if args.project_id and resolve_project_repo(hub_root, args.project_id) is None:
        hub_adopted = hub_state.adopted_project or {}
        if args.project_id != hub_adopted.get("project_id"):
            raise SystemExit(f"Unknown project_id for hub registry: {args.project_id}")

    result = index_local_docs(
        repo_root=hub_root,
        node_home=hub_node_home,
        project_id=args.project_id,
        docs_dir=args.docs_dir,
        dry_run=args.dry_run,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
