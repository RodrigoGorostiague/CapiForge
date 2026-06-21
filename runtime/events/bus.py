from __future__ import annotations

import asyncio
from pathlib import Path

from runtime.events.types import ChangeEvent


class EventBus:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[ChangeEvent | None]] = set()
        self._lock = asyncio.Lock()

    def create_subscription(self) -> asyncio.Queue[ChangeEvent | None]:
        queue: asyncio.Queue[ChangeEvent | None] = asyncio.Queue()
        self._subscribers.add(queue)
        return queue

    def remove_subscription(self, queue: asyncio.Queue[ChangeEvent | None]) -> None:
        self._subscribers.discard(queue)

    async def publish(self, event: ChangeEvent) -> None:
        for queue in list(self._subscribers):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                pass

    async def close(self) -> None:
        subscribers = list(self._subscribers)
        self._subscribers.clear()
        for queue in subscribers:
            try:
                queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    def publish_local(self, db_path: Path, *, version: int = -1) -> None:
        event = ChangeEvent(db_path=db_path.resolve(), version=version)

        async def _emit() -> None:
            await self.publish(event)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(_emit())
