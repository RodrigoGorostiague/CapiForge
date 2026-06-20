from __future__ import annotations

import os
import subprocess
from functools import lru_cache
from pathlib import Path

SYSTEM_SHARE_ROOT = Path("/usr/share/capiforge")


@lru_cache(maxsize=1)
def share_root() -> Path:
    override = os.environ.get("CAPIFORGE_SHARE", "").strip()
    if override:
        return Path(override).resolve()
    if SYSTEM_SHARE_ROOT.is_dir():
        return SYSTEM_SHARE_ROOT
    return dev_repo_root()


def dev_repo_root() -> Path:
    git_root = _git_root(Path.cwd())
    if git_root is not None:
        return git_root
    runtime_dir = Path(__file__).resolve().parent
    return runtime_dir.parent


def _git_root(path: Path) -> Path | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return Path(value).resolve() if value else None


def schema_path(name: str) -> Path:
    return share_root() / "storage" / name


def asset_path(relative: str | Path) -> Path:
    return share_root() / Path(relative)


def skills_root() -> Path:
    return share_root() / "skills"


def default_repo_root() -> Path:
    return Path.cwd().resolve()


def system_share_installed() -> bool:
    schema = SYSTEM_SHARE_ROOT / "storage" / "node-schema.sql"
    return SYSTEM_SHARE_ROOT.is_dir() and schema.is_file()
