from __future__ import annotations

from pathlib import PurePosixPath

from runtime.hub.data import AuditPreview, LocalDocumentPreview, TaskPreview
from runtime.web.detail_sections import DetailRow, DetailSection, DetailTaskLink
from runtime.web.i18n import FIELD_LABELS, linked_task_count_label


def _linked_task_links(tasks: tuple[TaskPreview, ...]) -> tuple[DetailTaskLink, ...]:
    return tuple(
        DetailTaskLink(task_id=task.task_id, description=task.description, state=task.state) for task in tasks
    )


def _document_display_title(document: LocalDocumentPreview) -> str:
    stem = PurePosixPath(document.storage_path).stem
    if stem:
        return stem.replace("-", " ").replace("_", " ")
    return document.document_id


def resolve_docs_detail_title(
    audit: AuditPreview | None,
    document: LocalDocumentPreview | None,
) -> str | None:
    if audit is not None:
        return audit.title or audit.audit_id
    if document is not None:
        return _document_display_title(document)
    return None


def build_audit_detail_sections(
    audit: AuditPreview,
    linked_tasks: tuple[TaskPreview, ...],
) -> tuple[DetailSection, ...]:
    sections: list[DetailSection] = [
        DetailSection(
            title="Atributos",
            rows=(
                DetailRow(
                    FIELD_LABELS["state"],
                    audit.state,
                    kind="pill",
                    pill_key=audit.state,
                    pill_tone="audit",
                ),
                DetailRow("Tareas vinculadas", linked_task_count_label(len(linked_tasks))),
            ),
        ),
        DetailSection(
            title="Identidad",
            rows=(DetailRow("Identificador", audit.audit_id, kind="code"),),
        ),
    ]
    if linked_tasks:
        sections.append(
            DetailSection(
                title="Tareas vinculadas",
                linked_tasks=_linked_task_links(linked_tasks),
            )
        )
    return tuple(sections)


def build_document_detail_sections(
    document: LocalDocumentPreview,
    document_error: str | None = None,
) -> tuple[DetailSection, ...]:
    identity_rows: list[DetailRow] = []
    if document.document_id != document.storage_path:
        identity_rows.append(DetailRow("Identificador", document.document_id, kind="code"))
    identity_rows.append(DetailRow("Ruta", document.storage_path, kind="code"))

    sections: list[DetailSection] = [
        DetailSection(
            title="Atributos",
            rows=(DetailRow("Tipo", "Documento local"),),
        ),
        DetailSection(title="Identidad", rows=tuple(identity_rows)),
    ]
    if document_error:
        sections.append(DetailSection(title="Error", summary=document_error))
    return tuple(sections)
