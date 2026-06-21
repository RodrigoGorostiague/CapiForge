from __future__ import annotations

import asyncio
from pathlib import Path

from runtime.events.bus import EventBus
from runtime.events.sources import ChangeSource, DataVersionSource
from runtime.events.types import ChangeEvent


class ChangeWatcher:
    def __init__(
        self,
        *,
        poll_interval_seconds: float = 0.3,
        debounce_seconds: float = 0.15,
        source: ChangeSource | None = None,
    ) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self.debounce_seconds = debounce_seconds
        self.source = source or DataVersionSource()
        self.bus = EventBus()
        self._versions: dict[Path, int] = {}
        self._stop = asyncio.Event()
        self._pending: dict[Path, ChangeEvent] = {}
        self._debounce_handle: asyncio.TimerHandle | None = None

    def stop(self) -> None:
        self._stop.set()
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()
            self._debounce_handle = None

    async def run(self, db_paths: list[Path]) -> None:
        normalized = [path.resolve() for path in db_paths]
        try:
            for path in normalized:
                version = self.source.read_signal(path)
                if version is not None:
                    self._versions[path] = version
            while not self._stop.is_set():
                for path in normalized:
                    if self._stop.is_set():
                        break
                    version = self.source.read_signal(path)
                    if version is None:
                        continue
                    previous = self._versions.get(path)
                    if previous is None:
                        self._versions[path] = version
                        continue
                    if version != previous:
                        self._versions[path] = version
                        self._schedule_publish(ChangeEvent(db_path=path, version=version))
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_seconds)
                except asyncio.TimeoutError:
                    continue
        finally:
            await self.bus.close()
            if hasattr(self.source, "close"):
                self.source.close()

    def notify_local_write(self, db_path: Path) -> None:
        resolved = db_path.resolve()
        version = self._versions.get(resolved, 0) + 1
        self._versions[resolved] = version
        self.bus.publish_local(resolved, version=version)

    def _schedule_publish(self, event: ChangeEvent) -> None:
        self._pending[event.db_path] = event
        if self._debounce_handle is not None:
            self._debounce_handle.cancel()

        loop = asyncio.get_running_loop()

        def _flush() -> None:
            self._debounce_handle = None
            pending = list(self._pending.values())
            self._pending.clear()
            for item in pending:
                asyncio.create_task(self.bus.publish(item))

        self._debounce_handle = loop.call_later(self.debounce_seconds, _flush)
