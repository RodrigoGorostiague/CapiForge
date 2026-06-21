from __future__ import annotations

from pathlib import Path

from runtime.events.bus import EventBus

_event_bus: EventBus | None = None


def set_event_bus(bus: EventBus | None) -> None:
    global _event_bus
    _event_bus = bus


def notify_local_write(db_path: str | Path) -> None:
    if _event_bus is None:
        return
    _event_bus.publish_local(Path(db_path))
