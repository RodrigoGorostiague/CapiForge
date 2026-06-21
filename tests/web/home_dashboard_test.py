import unittest

from runtime.hub.data import ProjectSnapshot, TaskPreview, WorkspaceSnapshot
from runtime.web.home_dashboard import build_home_dashboard


class HomeDashboardTest(unittest.TestCase):
    def _project(self, **overrides) -> ProjectSnapshot:
        defaults = {
            "project_id": "prj_test",
            "workspace_id": "ws_test",
            "name": "CapiForge",
            "owner_node_id": "node_owner",
            "queue_counts": {"ready": 2, "done": 1},
            "ready_tasks": (
                TaskPreview(
                    "tsk_1",
                    "Primera lista",
                    "ready",
                    "high",
                    "medium",
                    "low",
                    "feature",
                ),
            ),
            "all_tasks": (
                TaskPreview("tsk_1", "Primera lista", "ready", "high", "medium", "low", "feature"),
                TaskPreview("tsk_2", "Hecha", "done", "medium", "low", "low", "doc"),
            ),
            "audits": (),
            "local_documents": (),
        }
        defaults.update(overrides)
        return ProjectSnapshot(**defaults)

    def test_builds_summary_without_raw_owner_prominence(self) -> None:
        from runtime.hub.data import AppSnapshot

        project = self._project()
        dashboard = build_home_dashboard(
            project=project,
            snapshot=AppSnapshot(local_node_id="node_other"),
            workspace_name="Workspace",
        )
        owner = next(item for item in dashboard.summary_items if item.label == "Propietario")
        self.assertEqual(owner.value, "Otro nodo")
        self.assertTrue(owner.hint.startswith("node_owner"))

    def test_queue_chips_link_to_task_filters(self) -> None:
        from runtime.hub.data import AppSnapshot

        dashboard = build_home_dashboard(
            project=self._project(),
            snapshot=AppSnapshot(local_node_id="node_owner"),
            workspace_name="Workspace",
        )
        ready_chip = next(chip for chip in dashboard.queue_chips if chip.state == "ready")
        self.assertIn("filter=active", ready_chip.url)
        self.assertIn("Lista 2", ready_chip.label)

    def test_next_task_has_detail_url(self) -> None:
        from runtime.hub.data import AppSnapshot

        dashboard = build_home_dashboard(
            project=self._project(),
            snapshot=AppSnapshot(local_node_id="node_owner"),
            workspace_name="Workspace",
        )
        self.assertIsNotNone(dashboard.next_task)
        assert dashboard.next_task is not None
        self.assertIn("task_id=tsk_1", dashboard.next_task.url)
        self.assertEqual(dashboard.next_task.task.description, "Primera lista")


if __name__ == "__main__":
    unittest.main()
