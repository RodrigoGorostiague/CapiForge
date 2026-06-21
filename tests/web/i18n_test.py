import unittest

from runtime.web.i18n import audit_count_label, pill_label, translate_ui_message


class WebI18nTest(unittest.TestCase):
    def test_pill_label_task_states(self) -> None:
        self.assertEqual(pill_label("ready"), "Lista")
        self.assertEqual(pill_label("in_progress"), "En progreso")

    def test_pill_label_priorities(self) -> None:
        self.assertEqual(pill_label("critical"), "Crítica")

    def test_translate_action_messages(self) -> None:
        self.assertEqual(translate_ui_message("Task claimed."), "Tarea reclamada.")
        self.assertEqual(
            translate_ui_message("Task 'Demo' created."),
            "Tarea «Demo» creada.",
        )
        self.assertEqual(
            translate_ui_message("Error: Task description is required."),
            "Error: La descripción de la tarea es obligatoria.",
        )

    def test_audit_count_label(self) -> None:
        self.assertEqual(audit_count_label(1), "1 auditoría")
        self.assertEqual(audit_count_label(3), "3 auditorías")


if __name__ == "__main__":
    unittest.main()
