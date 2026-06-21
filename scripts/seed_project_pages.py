#!/usr/bin/env python3
"""Seed default purpose and architecture project pages."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore
from runtime.shared.ids import canonical_id

PURPOSE = """# CapiForge Purpose

CapiForge is a **local-first project hub** that keeps a adopted repository's **purpose**, **architecture**, **audits**, and **task state** current for a single owner with multiple AI agents.

It is **not** a replacement for Engram (agent memory) or OpenSpec (specs). Agents publish to CapiForge only at **milestones** to limit token use.

## Primary surfaces

- **Web UI** (`capiforge web`) — human onboarding and project tracking (Notion-style)
- **MCP / CLI** — agent milestone publication and optional queue coordination
"""

ARCHITECTURE = """# CapiForge Architecture (summary)

- **Owner-local SQLite** (`.capiforge/node/node.sqlite3`) — canonical project state
- **project_pages** — purpose and architecture (this hub)
- **audits** — milestone reports (markdown)
- **tasks** — tracked work with lifecycle states
- **Web UI** — primary human consumption surface
- **MCP** — 14 public tools; milestone-first agent contract

## Out of scope for MVP v0.3

- Engram session memory duplication
- Multi-user workspaces and sync (future)
- Admin BI dashboards (future)

See [architecture-v01.md](../docs/architecture-v01.md) and [audit-v03-scope-pivot.md](../docs/audits/audit-v03-scope-pivot.md).
"""


def seed_pages(*, repo_root: Path, dry_run: bool = False) -> list[dict]:
    bootstrap = NodeBootstrap(repo_root=str(repo_root))
    results: list[dict] = []
    with bootstrap.bootstrap_session(command="seed_project_pages", timeout=30.0, interactive=False):
        state, store = bootstrap._open_adopted_store_unlocked()
        try:
            project_id = state.adopted_project["project_id"]
            as_of = "2026-06-21T17:00:00Z"
            for page_type, title, content in (
                ("purpose", "Project Purpose", PURPOSE),
                ("architecture", "Architecture", ARCHITECTURE),
            ):
                existing = store.get_project_page(project_id, page_type)
                if existing:
                    results.append({"page_type": page_type, "status": "exists", "page_id": existing["page_id"]})
                    continue
                page_id = canonical_id("page", project_id, page_type)
                if dry_run:
                    results.append({"page_type": page_type, "status": "dry_run", "page_id": page_id})
                    continue
                store.upsert_project_page(
                    page_id=page_id,
                    project_id=project_id,
                    page_type=page_type,
                    title=title,
                    content=content,
                    updated_at=as_of,
                )
                results.append({"page_type": page_type, "status": "created", "page_id": page_id})
            if not dry_run:
                store.db.commit()
        finally:
            store.close()
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed default project pages.")
    parser.add_argument("--repo-root", default=str(REPO_ROOT))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = seed_pages(repo_root=Path(args.repo_root), dry_run=args.dry_run)
    if args.json:
        print(json.dumps({"pages": result}, indent=2, sort_keys=True))
    else:
        for item in result:
            print(f"{item['status']}: {item['page_type']} -> {item['page_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
