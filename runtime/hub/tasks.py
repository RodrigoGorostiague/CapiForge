from __future__ import annotations

from runtime.hub.data import TaskPreview
from runtime.hub.task_fields import (
    TASK_EFFORT_ORDER,
    TASK_FILTER_OPTIONS,
    TASK_PRIORITY_ORDER,
    TASK_RISK_ORDER,
    TASK_SORTABLE_COLUMNS,
    TASK_STATE_ORDER,
    TASK_TYPE_ORDER,
)

__all__ = (
    "TASK_FILTER_OPTIONS",
    "TASK_SORTABLE_COLUMNS",
    "sort_tasks_for_view",
)


def _ordered_index(order: tuple[str, ...], value: str) -> int:
    try:
        return order.index(value)
    except ValueError:
        return len(order)


def sort_tasks_for_view(
    tasks: tuple[TaskPreview, ...],
    *,
    sort_column: str,
    reverse: bool = False,
) -> tuple[TaskPreview, ...]:
    if sort_column not in TASK_SORTABLE_COLUMNS:
        return tasks

    def sort_key(task: TaskPreview):
        if sort_column == "description":
            return (task.description or "").casefold()
        if sort_column == "state":
            return _ordered_index(TASK_STATE_ORDER, task.state)
        if sort_column == "priority":
            return _ordered_index(TASK_PRIORITY_ORDER, task.priority)
        if sort_column == "task_type":
            return _ordered_index(TASK_TYPE_ORDER, task.task_type)
        if sort_column == "effort":
            return _ordered_index(TASK_EFFORT_ORDER, task.effort)
        if sort_column == "risk":
            return _ordered_index(TASK_RISK_ORDER, task.risk)
        return ""

    return tuple(sorted(tasks, key=sort_key, reverse=reverse))
