from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

from runtime.node.store import DEFAULT_NODE_SCHEMA_PATH, NodeStore
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import canonical_id


@dataclass(frozen=True)
class BootstrapState:
    state: Literal["uninitialized", "initialized", "adopted"]
    local_node_id: str
    node_home: str
    node_db_path: str
    adopted_project: dict | None


class NodeBootstrap:
    def __init__(
        self,
        *,
        repo_root: str | Path,
        node_home: str | Path | None = None,
        schema_path: str | Path = DEFAULT_NODE_SCHEMA_PATH,
    ):
        self.repo_root = Path(repo_root).resolve()
        self.node_home = (Path(node_home) if node_home is not None else self.repo_root / ".capiforge" / "node").resolve()
        self.schema_path = Path(schema_path)
        self.manifest_path = self.node_home / "bootstrap.json"
        self.node_db_path = self.node_home / "node.sqlite3"
        self.local_node_id = canonical_id("node", self.repo_root.as_posix())

    def status(self) -> BootstrapState:
        if not self.manifest_path.exists():
            return BootstrapState(
                state="uninitialized",
                local_node_id=self.local_node_id,
                node_home=str(self.node_home),
                node_db_path=str(self.node_db_path),
                adopted_project=None,
            )
        payload = json.loads(self.manifest_path.read_text())
        return self._validate_state(
            BootstrapState(
                state=payload["state"],
                local_node_id=payload["local_node_id"],
                node_home=payload["node_home"],
                node_db_path=payload["node_db_path"],
                adopted_project=payload.get("adopted_project"),
            )
        )

    def open_or_init(self) -> BootstrapState:
        if self.manifest_path.exists():
            return self.status()

        self.node_home.mkdir(parents=True, exist_ok=True)
        store = NodeStore.from_file(self.node_db_path, schema_path=self.schema_path)
        store.close()
        state = BootstrapState(
            state="initialized",
            local_node_id=self.local_node_id,
            node_home=str(self.node_home),
            node_db_path=str(self.node_db_path),
            adopted_project=None,
        )
        self._save_state(state)
        return state

    def adopt_repo(self, repo_root: str | Path | None = None) -> BootstrapState:
        state = self.status()
        if state.state == "uninitialized":
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap initialization is required before adoption")

        adopted_repo_root = Path(repo_root or self.repo_root).resolve()
        if adopted_repo_root != self.repo_root:
            raise SurfaceError("TRUST_BOUNDARY_VIOLATION", "bootstrap adoption is limited to the local repository root")
        metadata = self._build_adopted_project(adopted_repo_root)
        if state.adopted_project:
            existing_root = Path(state.adopted_project["repo_root"]).resolve()
            if existing_root != adopted_repo_root:
                raise SurfaceError("TRUST_BOUNDARY_VIOLATION", "bootstrap is already bound to a different local repository")
            return state

        store = NodeStore.from_file(self.node_db_path, schema_path=self.schema_path)
        try:
            if not store.get_workspace(metadata["workspace_id"]):
                store.create_workspace(metadata["workspace_id"], metadata["workspace_canonical_link"], metadata["workspace_name"])
            store.upsert_project(
                metadata["project_id"],
                metadata["workspace_id"],
                self.local_node_id,
                metadata["project_canonical_link"],
                metadata["project_name"],
            )
            store.db.commit()
        finally:
            store.close()

        adopted_state = BootstrapState(
            state="adopted",
            local_node_id=self.local_node_id,
            node_home=str(self.node_home),
            node_db_path=str(self.node_db_path),
            adopted_project=metadata,
        )
        self._save_state(adopted_state)
        return adopted_state

    def require_adopted(self) -> BootstrapState:
        state = self.status()
        if state.state != "adopted" or state.adopted_project is None:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap adoption is required before reads")
        return state

    def _save_state(self, state: BootstrapState) -> None:
        self.node_home.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True) + "\n")

    def _build_adopted_project(self, repo_root: Path) -> dict:
        workspace_root = repo_root.parent.resolve()
        return {
            "repo_root": str(repo_root),
            "workspace_id": canonical_id("workspace", workspace_root.as_posix()),
            "workspace_name": workspace_root.name,
            "workspace_canonical_link": f"workspace://{workspace_root.name}",
            "project_id": canonical_id("project", repo_root.as_posix()),
            "project_name": repo_root.name,
            "project_canonical_link": f"project://{repo_root.name}",
        }

    def _validate_state(self, state: BootstrapState) -> BootstrapState:
        if state.local_node_id != self.local_node_id:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap manifest points to an unexpected local node identity")
        if Path(state.node_home) != self.node_home:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap manifest points to an unexpected node home")
        if Path(state.node_db_path) != self.node_db_path:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap manifest points to an unexpected node database path")
        if state.state == "adopted" and state.adopted_project is None:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "adopted bootstrap state requires persisted project metadata")
        if state.state == "initialized" and state.adopted_project is not None:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "initialized bootstrap state cannot include adopted project metadata")
        return state
