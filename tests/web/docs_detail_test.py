import unittest

from runtime.hub.data import AuditPreview, LocalDocumentPreview, TaskPreview
from runtime.web.docs_detail import (
    build_audit_detail_sections,
    build_document_detail_sections,
    resolve_docs_detail_title,
)


class DocsDetailSectionsTest(unittest.TestCase):
    def test_audit_sections_include_state_and_linked_tasks(self) -> None:
        audit = AuditPreview(audit_id="aud_demo", title="Auditoría demo", state="published", content="# Demo")
        linked = (
            TaskPreview(
                task_id="tsk_one",
                description="Primera tarea",
                state="ready",
                priority="high",
                effort="medium",
                risk="low",
                task_type="feature",
                origin_audit_id="aud_demo",
            ),
        )
        sections = build_audit_detail_sections(audit, linked)
        titles = [section.title for section in sections]
        self.assertEqual(titles[:2], ["Atributos", "Identidad"])
        self.assertIn("Tareas vinculadas", titles)
        linked_section = next(section for section in sections if section.title == "Tareas vinculadas")
        self.assertEqual(len(linked_section.linked_tasks), 1)
        self.assertEqual(linked_section.linked_tasks[0].task_id, "tsk_one")

    def test_document_sections_include_path_and_error(self) -> None:
        document = LocalDocumentPreview(document_id="mvp-v04", storage_path="docs/mvp-v04.md")
        sections = build_document_detail_sections(document, "No se pudo leer el archivo.")
        titles = [section.title for section in sections]
        self.assertEqual(titles[:2], ["Atributos", "Identidad"])
        self.assertIn("Error", titles)
        identity_values = [row.value for row in sections[1].rows]
        self.assertIn("docs/mvp-v04.md", identity_values)

    def test_resolve_docs_detail_title_prefers_audit_title(self) -> None:
        audit = AuditPreview(audit_id="aud_demo", title="Auditoría demo", state="published")
        document = LocalDocumentPreview(document_id="mvp-v04", storage_path="docs/mvp-v04.md")
        self.assertEqual(resolve_docs_detail_title(audit, None), "Auditoría demo")
        self.assertEqual(resolve_docs_detail_title(None, document), "mvp v04")


if __name__ == "__main__":
    unittest.main()
