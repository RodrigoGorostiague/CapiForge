from __future__ import annotations

from typing import Any

from rich.console import RenderableType
from textual.widgets import Static


class NavRow(Static):
    """Clickable sidenav row bound to a tree index."""

    def __init__(self, label: str, *, node_index: int, classes: str = "", **kwargs: Any) -> None:
        super().__init__(label, classes=classes, **kwargs)
        self.node_index = node_index


class FilterPill(Static):
    """Clickable task filter pill."""

    def __init__(self, label: str, *, filter_id: str, classes: str = "", **kwargs: Any) -> None:
        super().__init__(label, classes=classes, **kwargs)
        self.filter_id = filter_id


class DocRow(Static):
    """Clickable documentation audit row."""

    def __init__(self, label: RenderableType, *, audit_id: str, classes: str = "", **kwargs: Any) -> None:
        super().__init__(label, classes=classes, **kwargs)
        self.audit_id = audit_id


class AuditTaskRow(Static):
    """Clickable linked task row shown under an audit in Documentation."""

    def __init__(self, label: RenderableType, *, task_id: str, classes: str = "", **kwargs: Any) -> None:
        super().__init__(label, classes=classes, **kwargs)
        self.task_id = task_id
