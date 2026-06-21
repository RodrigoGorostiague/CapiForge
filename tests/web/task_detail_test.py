import unittest

from runtime.hub.data import AuditPreview, TaskPreview
from runtime.web.task_detail import build_task_detail_sections


class TaskDetailSectionsTest(unittest.TestCase):
    def test_builds_metric_and_identity_sections(self) -> None:
        task = TaskPreview(
            task_id="tsk_demo",
            description="Demo task",
            state="ready",
            priority="high",
            effort="medium",
            risk="low",
            task_type="feature",
            lifecycle_key="audit/v0.4/web/demo",
        )
        sections = build_task_detail_sections(task, None)
        titles = [section.title for section in sections]
        self.assertEqual(titles[:2], ["Atributos", "Identidad"])
        identity_values = [row.value for row in sections[1].rows]
        self.assertIn("tsk_demo", identity_values)
        self.assertIn("audit/v0.4/web/demo", identity_values)

    def test_includes_justification_and_audit(self) -> None:
        task = TaskPreview(
            task_id="tsk_demo",
            description="Demo task",
            state="ready",
            priority="high",
            effort="medium",
            risk="low",
            task_type="feature",
            origin_audit_id="aud_demo",
            justification_summary="Resumen breve",
            justification_evidence_refs=("audit://aud_demo",),
            justification_expected_impact="Mejor lectura",
        )
        audit = AuditPreview(audit_id="aud_demo", title="Auditoría demo", state="published")
        sections = build_task_detail_sections(task, audit)
        titles = [section.title for section in sections]
        self.assertIn("Justificación", titles)
        self.assertIn("Auditoría de origen", titles)
        justification = next(section for section in sections if section.title == "Justificación")
        self.assertEqual(justification.summary, "Resumen breve")
        self.assertEqual(justification.bullets, ("audit://aud_demo",))


if __name__ == "__main__":
    unittest.main()
