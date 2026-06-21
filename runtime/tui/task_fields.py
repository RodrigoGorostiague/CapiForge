from __future__ import annotations

from runtime.tui.view import (
    TASK_EFFORT_ORDER,
    TASK_PRIORITY_ORDER,
    TASK_RISK_ORDER,
    TASK_STATE_ORDER,
    TASK_TYPE_ORDER,
)

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
