from __future__ import annotations

import fcntl
import json
import os
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Literal

from runtime.node.store import DEFAULT_NODE_SCHEMA_PATH, NodeStore
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import canonical_id


DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS = 30.0
BOOTSTRAP_LOCK_POLL_INTERVAL_SECONDS = 0.05
BOOTSTRAP_LOCK_SUSPECT_AGE_SECONDS = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS


@dataclass(frozen=True)
class BootstrapState:
    state: Literal["uninitialized", "initialized", "adopted"]
    local_node_id: str
    node_home: str
    node_db_path: str
    adopted_project: dict | None


@dataclass(frozen=True)
class BootstrapLockInfo:
    owner_node_id: str
    pid: int | None
    command: str
    acquired_at: str
    last_seen_at: str


@dataclass(frozen=True)
class BootstrapLockOutcome:
    status: Literal["acquired", "timeout", "suspect"]
    info: BootstrapLockInfo | None


BootstrapWaitReporter = Callable[[str, dict], None]


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
        self.lock_path = self.node_home / "bootstrap.lock"
        self.local_node_id = canonical_id("node", self.repo_root.as_posix())

    def status(
        self,
        *,
        lock_timeout_seconds: float = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
        interactive: bool = True,
        verbose: bool = False,
        recover_stale_lock: bool = False,
        wait_reporter: BootstrapWaitReporter | None = None,
    ) -> BootstrapState:
        with self.bootstrap_session(
            command="status",
            timeout=lock_timeout_seconds,
            interactive=interactive,
            verbose=verbose,
            recover_stale_lock=recover_stale_lock,
            wait_reporter=wait_reporter,
        ):
            return self._status_unlocked()

    def _status_unlocked(self) -> BootstrapState:
        state = self._load_state_unlocked()
        if state.state == "adopted":
            self._ensure_adopted_store_ready(state)
        return state

    def _load_state_unlocked(self) -> BootstrapState:
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

    def open_or_init(
        self,
        *,
        lock_timeout_seconds: float = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
        interactive: bool = True,
        verbose: bool = False,
        recover_stale_lock: bool = False,
        wait_reporter: BootstrapWaitReporter | None = None,
    ) -> BootstrapState:
        with self.bootstrap_session(
            command="init",
            timeout=lock_timeout_seconds,
            interactive=interactive,
            verbose=verbose,
            recover_stale_lock=recover_stale_lock,
            wait_reporter=wait_reporter,
        ):
            return self._open_or_init_unlocked()

    def _open_or_init_unlocked(self) -> BootstrapState:
        if self.manifest_path.exists():
            return self._status_unlocked()

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

    def adopt_repo(
        self,
        repo_root: str | Path | None = None,
        *,
        lock_timeout_seconds: float = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
        interactive: bool = True,
        verbose: bool = False,
        recover_stale_lock: bool = False,
        wait_reporter: BootstrapWaitReporter | None = None,
    ) -> BootstrapState:
        with self.bootstrap_session(
            command="adopt",
            timeout=lock_timeout_seconds,
            interactive=interactive,
            verbose=verbose,
            recover_stale_lock=recover_stale_lock,
            wait_reporter=wait_reporter,
        ):
            return self._adopt_repo_unlocked(repo_root)

    def _adopt_repo_unlocked(self, repo_root: str | Path | None = None) -> BootstrapState:
        state = self._status_unlocked()
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

    def require_adopted(
        self,
        *,
        lock_timeout_seconds: float = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
        interactive: bool = True,
        verbose: bool = False,
        recover_stale_lock: bool = False,
        wait_reporter: BootstrapWaitReporter | None = None,
    ) -> BootstrapState:
        with self.bootstrap_session(
            command="read",
            timeout=lock_timeout_seconds,
            interactive=interactive,
            verbose=verbose,
            recover_stale_lock=recover_stale_lock,
            wait_reporter=wait_reporter,
        ):
            return self._require_adopted_unlocked()

    def _require_adopted_unlocked(self) -> BootstrapState:
        state = self._load_state_unlocked()
        if state.state != "adopted" or state.adopted_project is None:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap adoption is required before reads")
        self._ensure_adopted_store_ready(state)
        return state

    def _ensure_adopted_store_ready(self, state: BootstrapState) -> None:
        store: NodeStore | None = None
        try:
            _, store = self._open_adopted_store_unlocked(state)
        finally:
            if store is not None:
                store.close()

    def _open_adopted_store_unlocked(self, state: BootstrapState | None = None) -> tuple[BootstrapState, NodeStore]:
        resolved_state = state or self._load_state_unlocked()
        if resolved_state.state != "adopted" or resolved_state.adopted_project is None:
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "bootstrap adoption is required before reads")
        if not Path(resolved_state.node_db_path).exists():
            raise SurfaceError("INVALID_BOOTSTRAP_STATE", "adopted bootstrap state requires an existing owner-local node database")
        return resolved_state, NodeStore.from_file(resolved_state.node_db_path, schema_path=self.schema_path)

    def read_entrypoint(
        self,
        *,
        as_of: str,
        lock_timeout_seconds: float = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
        interactive: bool = True,
        verbose: bool = False,
        recover_stale_lock: bool = False,
        wait_reporter: BootstrapWaitReporter | None = None,
    ) -> tuple[BootstrapState, dict]:
        with self.bootstrap_session(
            command="read",
            timeout=lock_timeout_seconds,
            interactive=interactive,
            verbose=verbose,
            recover_stale_lock=recover_stale_lock,
            wait_reporter=wait_reporter,
        ):
            return self._read_entrypoint_unlocked(as_of)

    def _read_entrypoint_unlocked(self, as_of: str) -> tuple[BootstrapState, dict]:
        from runtime.node.mcp import NodeMCPSurface
        from runtime.node.router import NodeRouter

        state, store = self._open_adopted_store_unlocked()
        try:
            surface = NodeMCPSurface(store=store, router=NodeRouter(store), local_node_id=state.local_node_id)
            entrypoint = surface.project_entrypoint_get_local(
                project_id=state.adopted_project["project_id"],
                as_of=as_of,
            )
        finally:
            store.close()
        return state, entrypoint["data"]

    @contextmanager
    def bootstrap_session(
        self,
        *,
        command: str,
        timeout: float = DEFAULT_BOOTSTRAP_LOCK_TIMEOUT_SECONDS,
        interactive: bool = True,
        verbose: bool = False,
        recover_stale_lock: bool = False,
        wait_reporter: BootstrapWaitReporter | None = None,
    ) -> Iterator[BootstrapLockOutcome]:
        del interactive, verbose
        lock_handle, outcome = self._acquire_bootstrap_lock(
            command=command,
            timeout=timeout,
            recover_stale_lock=recover_stale_lock,
            wait_reporter=wait_reporter,
        )
        if outcome.status == "timeout":
            raise SurfaceError(
                "BOOTSTRAP_LOCK_TIMEOUT",
                f"timed out waiting for bootstrap lock while running {command}",
                details=self._lock_diagnostics(outcome.info),
            )
        if outcome.status == "suspect":
            raise SurfaceError(
                "BOOTSTRAP_LOCK_SUSPECT",
                f"bootstrap lock requires explicit recovery before running {command}",
                details=self._lock_diagnostics(outcome.info),
            )

        try:
            yield outcome
        finally:
            assert lock_handle is not None
            self._release_bootstrap_lock(lock_handle)

    def _save_state(self, state: BootstrapState) -> None:
        self.node_home.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(asdict(state), indent=2, sort_keys=True) + "\n")

    def _acquire_bootstrap_lock(
        self,
        *,
        command: str,
        timeout: float,
        recover_stale_lock: bool,
        wait_reporter: BootstrapWaitReporter | None,
    ) -> tuple[object | None, BootstrapLockOutcome]:
        self.node_home.mkdir(parents=True, exist_ok=True)
        timeout = max(timeout, 0.0)
        deadline = time.monotonic() + timeout
        wait_reported = False

        while True:
            lock_handle = self._open_lock_handle()
            try:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_handle.close()
                owner_info = self._read_lock_metadata()
                # Another process still owns the OS lock. If its metadata is incomplete,
                # dead, or too old, treat that owner as suspect instead of silently
                # waiting behind it.
                if self._active_lock_owner_is_suspect(owner_info, timeout=timeout):
                    return None, BootstrapLockOutcome(status="suspect", info=owner_info)
                if not wait_reported and wait_reporter is not None:
                    wait_reporter(command, self._lock_diagnostics(owner_info))
                    wait_reported = True
                if time.monotonic() >= deadline:
                    return None, BootstrapLockOutcome(status="timeout", info=owner_info)
                time.sleep(BOOTSTRAP_LOCK_POLL_INTERVAL_SECONDS)
                continue

            stale_info = self._read_lock_metadata(lock_handle)
            # We now own the OS lock, so any leftover metadata belongs to an abandoned
            # prior session. Recovery still requires an explicit operator opt-in.
            if stale_info is not None and not recover_stale_lock:
                fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                lock_handle.close()
                return None, BootstrapLockOutcome(status="suspect", info=stale_info)

            current_info = self._current_lock_info(command)
            self._write_lock_metadata(lock_handle, current_info)
            return lock_handle, BootstrapLockOutcome(status="acquired", info=current_info)

    def _release_bootstrap_lock(self, lock_handle: object) -> None:
        try:
            self._clear_lock_metadata(lock_handle)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            lock_handle.close()

    def _open_lock_handle(self):
        fd = os.open(self.lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        return os.fdopen(fd, "r+")

    def _current_lock_info(self, command: str) -> BootstrapLockInfo:
        timestamp = self._utc_now()
        return BootstrapLockInfo(
            owner_node_id=self.local_node_id,
            pid=os.getpid(),
            command=command,
            acquired_at=timestamp,
            last_seen_at=timestamp,
        )

    def _lock_diagnostics(self, info: BootstrapLockInfo | None) -> dict:
        if info is None:
            return {
                "owner_node_id": None,
                "pid": None,
                "command": None,
                "lock_age_seconds": None,
                "liveness": "unknown",
                "recovery_hint": "rerun with --recover-stale-lock only after confirming no other bootstrap command is active",
            }

        return {
            "owner_node_id": info.owner_node_id,
            "pid": info.pid,
            "command": info.command,
            "lock_age_seconds": self._lock_age_seconds(info),
            "liveness": self._pid_liveness(info.pid),
            "recovery_hint": "rerun with --recover-stale-lock only after confirming no other bootstrap command is active",
        }

    def _locked_owner_metadata_is_suspect(self, info: BootstrapLockInfo | None) -> bool:
        if info is None:
            return False
        if not info.owner_node_id or info.owner_node_id == "unknown":
            return True
        if info.pid is None:
            return True
        if not info.command or info.command == "unknown":
            return True
        return not info.acquired_at or info.acquired_at == "unknown"

    def _active_lock_owner_is_suspect(self, info: BootstrapLockInfo | None, *, timeout: float) -> bool:
        if self._locked_owner_metadata_is_suspect(info):
            return True
        assert info is not None
        if self._pid_liveness(info.pid) != "alive":
            return True
        age_seconds = self._lock_age_seconds(info)
        if age_seconds is None:
            return False
        suspect_age_threshold = max(BOOTSTRAP_LOCK_SUSPECT_AGE_SECONDS, timeout)
        return age_seconds >= suspect_age_threshold

    def _write_lock_metadata(self, lock_handle: object, info: BootstrapLockInfo) -> None:
        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.write(json.dumps(asdict(info), indent=2, sort_keys=True) + "\n")
        lock_handle.flush()
        os.fsync(lock_handle.fileno())

    def _clear_lock_metadata(self, lock_handle: object) -> None:
        lock_handle.seek(0)
        lock_handle.truncate()
        lock_handle.flush()
        os.fsync(lock_handle.fileno())

    def _read_lock_metadata(self, lock_handle: object | None = None) -> BootstrapLockInfo | None:
        if lock_handle is None:
            if not self.lock_path.exists():
                return None
            with self.lock_path.open() as handle:
                return self._read_lock_metadata(handle)

        lock_handle.seek(0)
        raw = lock_handle.read().strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return BootstrapLockInfo(
                owner_node_id="unknown",
                pid=None,
                command="unknown",
                acquired_at="unknown",
                last_seen_at="unknown",
            )

        return BootstrapLockInfo(
            owner_node_id=payload.get("owner_node_id") or "unknown",
            pid=payload.get("pid") if isinstance(payload.get("pid"), int) else None,
            command=payload.get("command") or "unknown",
            acquired_at=payload.get("acquired_at") or "unknown",
            last_seen_at=payload.get("last_seen_at") or payload.get("acquired_at") or "unknown",
        )

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

    def _lock_age_seconds(self, info: BootstrapLockInfo) -> float | None:
        try:
            acquired_at = datetime.fromisoformat(info.acquired_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        return max((datetime.now(timezone.utc) - acquired_at).total_seconds(), 0.0)

    def _pid_liveness(self, pid: int | None) -> str:
        if pid is None:
            return "unknown"
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return "dead"
        except PermissionError:
            return "unknown"
        return "alive"

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
