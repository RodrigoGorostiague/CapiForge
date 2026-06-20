from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_VERSION = 1
SERVER_NAME = "capiforge"
VALID_TARGETS = frozenset({"cursor", "opencode"})


@dataclass
class IntegrationPaths:
    cursor_global: str | None = None
    cursor_project: str | None = None
    opencode: str | None = None

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> IntegrationPaths:
        if not payload:
            return cls()
        return cls(
            cursor_global=payload.get("cursor_global"),
            cursor_project=payload.get("cursor_project"),
            opencode=payload.get("opencode"),
        )

    def to_dict(self) -> dict[str, str]:
        result: dict[str, str] = {}
        if self.cursor_global:
            result["cursor_global"] = self.cursor_global
        if self.cursor_project:
            result["cursor_project"] = self.cursor_project
        if self.opencode:
            result["opencode"] = self.opencode
        return result


@dataclass
class InstallerState:
    version: int = STATE_VERSION
    installed_at: str = ""
    backend: str = "uv"
    capiforge_bin: str = ""
    repo_root: str = ""
    node_home: str = ""
    checkout_root: str = ""
    install_tui_extra: bool = True
    targets: list[str] = field(default_factory=list)
    integration_paths: IntegrationPaths = field(default_factory=IntegrationPaths)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> InstallerState:
        targets = [target for target in payload.get("targets", []) if target in VALID_TARGETS]
        return cls(
            version=int(payload.get("version", STATE_VERSION)),
            installed_at=str(payload.get("installed_at", "")),
            backend=str(payload.get("backend", "uv")),
            capiforge_bin=str(payload.get("capiforge_bin", "")),
            repo_root=str(payload.get("repo_root", "")),
            node_home=str(payload.get("node_home", "")),
            checkout_root=str(payload.get("checkout_root", "")),
            install_tui_extra=bool(payload.get("install_tui_extra", True)),
            targets=targets,
            integration_paths=IntegrationPaths.from_dict(payload.get("integration_paths")),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["integration_paths"] = self.integration_paths.to_dict()
        return payload


def default_state_path() -> Path:
    return Path.home() / ".capiforge" / "installer-state.json"


def load_state(path: Path | None = None) -> InstallerState | None:
    state_path = path or default_state_path()
    if not state_path.exists():
        return None
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("installer state must be a JSON object")
    return InstallerState.from_dict(payload)


def save_state(state: InstallerState, path: Path | None = None) -> Path:
    state_path = path or default_state_path()
    state_path.parent.mkdir(parents=True, exist_ok=True)
    if not state.installed_at:
        state.installed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    state_path.write_text(json.dumps(state.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return state_path


def clear_state(path: Path | None = None) -> None:
    state_path = path or default_state_path()
    if state_path.exists():
        state_path.unlink()


def default_integration_paths(*, repo_root: Path, home: Path | None = None) -> IntegrationPaths:
    home = home or Path.home()
    return IntegrationPaths(
        cursor_global=str(home / ".cursor" / "mcp.json"),
        cursor_project=str((repo_root / ".cursor" / "mcp.json").resolve()),
        opencode=str(home / ".config" / "opencode" / "opencode.json"),
    )


def detect_capiforge_bin() -> str | None:
    return shutil.which("capiforge")


def detect_backend(capiforge_bin: str | None = None) -> str | None:
    if shutil.which("uv") and _uv_has_capiforge():
        return "uv"
    if shutil.which("pipx") and _pipx_has_capiforge():
        return "pipx"
    if capiforge_bin:
        return "unknown"
    return None


def _uv_has_capiforge() -> bool:
    import subprocess

    try:
        completed = subprocess.run(
            ["uv", "tool", "list"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    return completed.returncode == 0 and any(line.startswith("capiforge ") for line in completed.stdout.splitlines())


def _pipx_has_capiforge() -> bool:
    import subprocess

    try:
        completed = subprocess.run(
            ["pipx", "list", "--json"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    if completed.returncode != 0:
        return False
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return False
    venvs = payload.get("venvs", {})
    return isinstance(venvs, dict) and "capiforge" in venvs


def detect_existing_state(*, checkout_root: Path | None = None) -> InstallerState | None:
    saved = load_state()
    if saved is not None:
        return saved

    capiforge_bin = detect_capiforge_bin()
    if not capiforge_bin:
        return None

    repo_root = checkout_root
    if repo_root is None:
        repo_root = Path.cwd()
    repo_root = repo_root.resolve()
    node_home = repo_root / ".capiforge" / "node"
    backend = detect_backend(capiforge_bin) or "unknown"
    integration_paths = default_integration_paths(repo_root=repo_root)

    return InstallerState(
        backend=backend,
        capiforge_bin=capiforge_bin,
        repo_root=str(repo_root),
        node_home=str(node_home.resolve()),
        checkout_root=str(checkout_root.resolve()) if checkout_root else str(repo_root),
        targets=[],
        integration_paths=integration_paths,
    )
