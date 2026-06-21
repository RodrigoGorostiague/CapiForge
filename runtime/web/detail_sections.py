from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class DetailRow:
    label: str
    value: str
    kind: Literal["text", "pill", "code"] = "text"
    pill_key: str | None = None
    pill_tone: Literal["state", "priority", "effort", "risk", "type", "audit"] | None = None


@dataclass(frozen=True)
class DetailTaskLink:
    task_id: str
    description: str
    state: str


@dataclass(frozen=True)
class DetailSection:
    title: str
    rows: tuple[DetailRow, ...] = ()
    summary: str | None = None
    bullets: tuple[str, ...] = ()
    audit_id: str | None = None
    audit_title: str | None = None
    audit_state: str | None = None
    linked_tasks: tuple[DetailTaskLink, ...] = ()
