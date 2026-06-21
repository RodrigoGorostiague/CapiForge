from __future__ import annotations

from runtime.hub.data import AuditPreview, TaskPreview

TASKS_PAGE_SIZE = 12


def find_audit(audits: tuple[AuditPreview, ...], audit_id: str | None) -> AuditPreview | None:
    if not audit_id:
        return None
    for audit in audits:
        if audit.audit_id == audit_id:
            return audit
    return None


def paginate_tasks(tasks: tuple[TaskPreview, ...], *, page: int, page_size: int = TASKS_PAGE_SIZE) -> dict:
    total = len(tasks)
    total_pages = max(1, (total + page_size - 1) // page_size) if total else 1
    safe_page = min(max(page, 1), total_pages)
    start = (safe_page - 1) * page_size
    end = start + page_size
    return {
        "page": safe_page,
        "page_size": page_size,
        "total": total,
        "total_pages": total_pages,
        "items": tasks[start:end],
        "has_prev": safe_page > 1,
        "has_next": safe_page < total_pages,
    }
