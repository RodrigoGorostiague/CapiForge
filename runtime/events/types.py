from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ChangeEvent:
    db_path: Path
    version: int
    topic: str | None = None
