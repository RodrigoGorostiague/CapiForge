from __future__ import annotations

import json

from runtime.node.store import NodeStore

INDEXES = ("ready", "blocked", "done", "critical", "expired_claim")


class NodeIndexBuilder:
    def __init__(self, store: NodeStore):
        self.store = store

    def build_project_entrypoint(self, project_id: str, as_of: str) -> dict:
        project = self.store.get_project(project_id)
        if not project:
            raise ValueError(f"unknown project: {project_id}")
        refs = {name: f"{project['canonical_link']}#indexes/{name}" for name in INDEXES}
        indexes = {name: self.store.list_tasks_for_index(project_id, name, as_of) for name in INDEXES}
        summary = {
            "project_id": project["project_id"],
            "project_name": project["name"],
            "project_link": project["canonical_link"],
            "owner_node_id": project["owner_node_id"],
            "linked_projects": self.store.list_linked_projects(project_id),
            "active_audits": self.store.list_active_audits(project_id),
            "queue_counts": {name: len(indexes[name]) for name in INDEXES},
            "index_refs": refs,
            "generated_at": as_of,
        }
        self.store.upsert_project_entrypoint(project_id, project["owner_node_id"], json.dumps(summary, sort_keys=True), refs)
        return {"entrypoint": summary, "indexes": indexes}
