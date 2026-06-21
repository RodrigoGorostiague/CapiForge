from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Protocol


class ChangeSource(Protocol):
    def read_signal(self, db_path: Path) -> int | None:
        """Return a monotonic change signal for the database, or None if unreadable."""

    def close(self) -> None:
        """Release any resources held by the source."""


class DataVersionSource:
    """Reads PRAGMA data_version through persistent observer connections."""

    def __init__(self) -> None:
        self._observers: dict[Path, sqlite3.Connection] = {}

    def read_signal(self, db_path: Path) -> int | None:
        resolved = db_path.resolve()
        if not resolved.exists():
            return None
        connection = self._observers.get(resolved)
        if connection is None:
            try:
                connection = sqlite3.connect(resolved, check_same_thread=False)
            except sqlite3.Error:
                return None
            self._observers[resolved] = connection
        try:
            row = connection.execute("PRAGMA data_version").fetchone()
            return int(row[0]) if row else None
        except sqlite3.Error:
            return None

    def close(self) -> None:
        for connection in self._observers.values():
            connection.close()
        self._observers.clear()
