from __future__ import annotations

from runtime.hub.data import AuditPreview, TaskPreview
from runtime.web.detail_sections import DetailRow, DetailSection
from runtime.web.i18n import FIELD_LABELS


def _format_timestamp(raw: str | None) -> str | None:
    if not raw:
        return None
    return raw.replace("T", " ").replace("Z", " UTC")


def build_task_detail_sections(task: TaskPreview, audit: AuditPreview | None) -> tuple[DetailSection, ...]:
    sections: list[DetailSection] = []

    metric_rows = (
        DetailRow(FIELD_LABELS["state"], task.state, kind="pill", pill_key=task.state, pill_tone="state"),
        DetailRow(FIELD_LABELS["priority"], task.priority, kind="pill", pill_key=task.priority, pill_tone="priority"),
        DetailRow(FIELD_LABELS["task_type"], task.task_type, kind="pill", pill_key=task.task_type, pill_tone="type"),
        DetailRow(FIELD_LABELS["effort"], task.effort, kind="pill", pill_key=task.effort, pill_tone="effort"),
        DetailRow(FIELD_LABELS["risk"], task.risk, kind="pill", pill_key=task.risk, pill_tone="risk"),
    )
    meta_rows: list[DetailRow] = []
    if task.lifecycle_key:
        meta_rows.append(DetailRow("Clave de ciclo", task.lifecycle_key, kind="code"))
    meta_rows.append(DetailRow("Identificador", task.task_id, kind="code"))
    sections.append(DetailSection(title="Atributos", rows=metric_rows))
    sections.append(DetailSection(title="Identidad", rows=tuple(meta_rows)))

    if task.justification_summary or task.justification_evidence_refs or task.justification_expected_impact:
        sections.append(
            DetailSection(
                title="Justificación",
                summary=task.justification_summary,
                bullets=task.justification_evidence_refs,
                rows=(
                    (DetailRow("Impacto esperado", task.justification_expected_impact),)
                    if task.justification_expected_impact
                    else ()
                ),
            )
        )

    if task.state == "blocked" and (task.blocked_reason or task.blocked_evidence or task.blocked_next_step):
        blocked_rows: list[DetailRow] = []
        if task.blocked_reason:
            blocked_rows.append(DetailRow("Motivo", task.blocked_reason))
        if task.blocked_evidence:
            blocked_rows.append(DetailRow("Evidencia", task.blocked_evidence))
        if task.blocked_next_step:
            blocked_rows.append(DetailRow("Siguiente paso", task.blocked_next_step))
        sections.append(DetailSection(title="Bloqueo", rows=tuple(blocked_rows)))

    if task.state == "done" and any(
        (task.done_result, task.done_artifacts, task.done_references, task.done_expected_impact)
    ):
        closure_rows: list[DetailRow] = []
        if task.done_result:
            closure_rows.append(DetailRow("Resultado", task.done_result))
        if task.done_artifacts:
            closure_rows.append(DetailRow("Artefactos", task.done_artifacts))
        if task.done_references:
            closure_rows.append(DetailRow("Referencias", task.done_references))
        if task.done_expected_impact:
            closure_rows.append(DetailRow("Impacto logrado", task.done_expected_impact))
        sections.append(DetailSection(title="Cierre", rows=tuple(closure_rows)))

    if task.claim_plan or task.claim_lease_expires_at:
        claim_rows: list[DetailRow] = []
        if task.claim_plan:
            claim_rows.append(DetailRow("Plan", task.claim_plan))
        lease = _format_timestamp(task.claim_lease_expires_at)
        if lease:
            claim_rows.append(DetailRow("Reclamación expira", lease))
        sections.append(DetailSection(title="Reclamación activa", rows=tuple(claim_rows)))

    if task.origin_audit_id:
        sections.append(
            DetailSection(
                title="Auditoría de origen",
                audit_id=task.origin_audit_id,
                audit_title=(audit.title if audit else None) or task.origin_audit_id,
                audit_state=audit.state if audit else None,
            )
        )

    return tuple(sections)
