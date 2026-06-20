import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.paths import asset_path, dev_repo_root, schema_path, share_root, skills_root


class PathsTest(unittest.TestCase):
    def test_dev_repo_root_points_at_checkout(self) -> None:
        root = dev_repo_root()
        self.assertTrue((root / "pyproject.toml").exists())
        self.assertTrue((root / "runtime").is_dir())

    def test_system_share_installed_false_without_fhs_tree(self) -> None:
        from runtime.paths import system_share_installed

        self.assertFalse(system_share_installed())

    def test_share_root_uses_capiforge_share_override(self) -> None:
        share_root.cache_clear()
        with tempfile.TemporaryDirectory() as temp_dir:
            share = Path(temp_dir) / "share"
            storage = share / "storage"
            storage.mkdir(parents=True)
            (storage / "node-schema.sql").write_text("-- test", encoding="utf-8")
            with patch.dict(os.environ, {"CAPIFORGE_SHARE": str(share)}, clear=False):
                share_root.cache_clear()
                self.assertEqual(share_root(), share.resolve())
                self.assertEqual(schema_path("node-schema.sql"), storage / "node-schema.sql")
        share_root.cache_clear()

    def test_asset_and_skills_paths_under_share_root(self) -> None:
        root = share_root()
        self.assertEqual(asset_path("assets/capiforge-icons/capiforge-ascii.txt"), root / "assets/capiforge-icons/capiforge-ascii.txt")
        self.assertEqual(skills_root(), root / "skills")

    def test_schema_path_default_exists_in_dev_checkout(self) -> None:
        path = schema_path("node-schema.sql")
        self.assertTrue(path.is_file(), msg=str(path))


if __name__ == "__main__":
    unittest.main()
