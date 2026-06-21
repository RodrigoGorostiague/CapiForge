from __future__ import annotations

TASK_STATE_ORDER = ("proposed", "ready", "claimed", "in_progress", "blocked", "done", "cancelled")
TASK_PRIORITY_ORDER = ("low", "medium", "high", "critical")
TASK_EFFORT_ORDER = ("low", "medium", "high")
TASK_RISK_ORDER = ("low", "medium", "high")
TASK_TYPE_ORDER = ("fix", "feature", "audit_followup", "doc", "refactor", "ops")

TASK_FIELD_OPTIONS: dict[str, tuple[str, ...]] = {
    "state": TASK_STATE_ORDER,
    "priority": TASK_PRIORITY_ORDER,
    "effort": TASK_EFFORT_ORDER,
    "risk": TASK_RISK_ORDER,
    "task_type": TASK_TYPE_ORDER,
}

TASK_FIELD_DB_COLUMN = {
    "state": "state",
    "priority": "priority",
    "effort": "effort",
    "risk": "risk",
    "task_type": "type",
}

TASK_SORTABLE_COLUMNS = frozenset(
    {"description", "state", "priority", "task_type", "effort", "risk"}
)

TASK_FILTER_OPTIONS = (
    ("all", "Todas", "1"),
    ("active", "Activas", "2"),
    ("blocked", "Bloqueadas", "3"),
    ("done", "Hechas", "4"),
)
