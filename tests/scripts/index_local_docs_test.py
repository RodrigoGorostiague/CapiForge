import tempfile
import unittest
from pathlib import Path

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.store import NodeStore

REPO_ROOT = Path(__file__).resolve().parents[2]
import sys

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.index_local_docs import document_id_for_path, index_local_docs


class IndexLocalDocsTest(unittest.TestCase):
    def test_indexes_markdown_under_docs(self) -> None:
        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: Path(tempdir).exists() and __import__("shutil").rmtree(tempdir, ignore_errors=True))
        repo_root = Path(tempdir) / "repo"
        docs_dir = repo_root / "docs"
        docs_dir.mkdir(parents=True)
        (docs_dir / "guide.md").write_text("# Guide\n", encoding="utf-8")
        (docs_dir / "nested" / "note.md").parent.mkdir(parents=True, exist_ok=True)
        (docs_dir / "nested" / "note.md").write_text("# Note\n", encoding="utf-8")

        bootstrap = NodeBootstrap(repo_root=repo_root)
        bootstrap.open_or_init()
        adopted = bootstrap.adopt_repo()
        project_id = adopted.adopted_project["project_id"]

        result = index_local_docs(
            repo_root=repo_root,
            node_home=None,
            project_id=None,
            docs_dir=Path("docs"),
            dry_run=False,
        )
        self.assertEqual(result["indexed"], 2)
        self.assertEqual(result["created"], 2)

        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        rows = store.list_local_documents(project_id)
        paths = {row["storage_path"] for row in rows}
        self.assertIn("docs/guide.md", paths)
        self.assertIn("docs/nested/note.md", paths)

    def test_document_id_is_stable(self) -> None:
        doc_id = document_id_for_path("prj_test", "docs/readme.md")
        self.assertTrue(doc_id.startswith("doc_"))
        self.assertEqual(doc_id, document_id_for_path("prj_test", "docs/readme.md"))

    def test_dry_run_does_not_write(self) -> None:
        tempdir = tempfile.mkdtemp()
        self.addCleanup(lambda: Path(tempdir).exists() and __import__("shutil").rmtree(tempdir, ignore_errors=True))
        repo_root = Path(tempdir) / "repo"
        (repo_root / "docs").mkdir(parents=True)
        (repo_root / "docs" / "only.md").write_text("# Only\n", encoding="utf-8")
        bootstrap = NodeBootstrap(repo_root=repo_root)
        bootstrap.open_or_init()
        adopted = bootstrap.adopt_repo()

        result = index_local_docs(
            repo_root=repo_root,
            node_home=None,
            project_id=None,
            docs_dir=Path("docs"),
            dry_run=True,
        )
        self.assertEqual(result["indexed"], 1)
        self.assertTrue(result["dry_run"])

        store = NodeStore.from_file(adopted.node_db_path)
        self.addCleanup(store.close)
        self.assertEqual(store.list_local_documents(adopted.adopted_project["project_id"]), [])
