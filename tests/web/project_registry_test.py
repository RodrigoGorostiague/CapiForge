import tempfile
import unittest
from pathlib import Path

from runtime.web.project_registry import (
    load_registry,
    registry_path,
    remove_registry_entry,
    resolve_project_repo,
    save_registry_entry,
)


class ProjectRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: Path(self.tempdir).exists() and __import__("shutil").rmtree(self.tempdir, ignore_errors=True))
        self.hub_root = Path(self.tempdir) / "hub"
        self.hub_root.mkdir()

    def test_save_and_load_registry_entry(self) -> None:
        repo = self.hub_root.parent / "other"
        repo.mkdir()
        save_registry_entry(
            self.hub_root,
            project_id="prj_other",
            repo_root=repo,
            node_home=repo / ".capiforge" / "node",
            project_name="Other",
        )
        loaded = load_registry(self.hub_root)
        self.assertIn("prj_other", loaded)
        self.assertEqual(loaded["prj_other"].project_name, "Other")
        self.assertEqual(loaded["prj_other"].repo_root, repo.resolve())

    def test_load_registry_skips_invalid_entries(self) -> None:
        path = registry_path(self.hub_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"projects": {"bad": {"repo_root": "/does/not/exist"}, "good": {"repo_root": "' + str(self.hub_root).replace("\\", "\\\\") + '"}}}',
            encoding="utf-8",
        )
        loaded = load_registry(self.hub_root)
        self.assertNotIn("bad", loaded)
        self.assertIn("good", loaded)

    def test_prune_invalid_entries(self) -> None:
        path = registry_path(self.hub_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            '{"projects": {"bad": {"repo_root": "/does/not/exist"}, "good": {"repo_root": "' + str(self.hub_root).replace("\\", "\\\\") + '"}}}',
            encoding="utf-8",
        )
        loaded = load_registry(self.hub_root, prune_invalid=True)
        self.assertEqual(set(loaded.keys()), {"good"})
        reloaded = load_registry(self.hub_root)
        self.assertEqual(set(reloaded.keys()), {"good"})

    def test_remove_registry_entry(self) -> None:
        repo = self.hub_root.parent / "other"
        repo.mkdir()
        save_registry_entry(
            self.hub_root,
            project_id="prj_remove",
            repo_root=repo,
            node_home=repo / ".capiforge" / "node",
            project_name="Remove me",
        )
        self.assertTrue(remove_registry_entry(self.hub_root, "prj_remove"))
        self.assertIsNone(resolve_project_repo(self.hub_root, "prj_remove"))
        self.assertFalse(remove_registry_entry(self.hub_root, "prj_remove"))
