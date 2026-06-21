import unittest

from runtime.hub.data import LocalDocumentPreview
from runtime.web.markdown import (
    MarkdownRenderContext,
    docs_view_url,
    render_markdown,
    resolve_markdown_target_path,
    rewrite_document_links,
)


class MarkdownLinkRewriteTest(unittest.TestCase):
    def test_resolves_audit_relative_filename(self) -> None:
        target = resolve_markdown_target_path("audit-v04-expanded-hub.md", base_path=None)
        self.assertEqual(target, "docs/audits/audit-v04-expanded-hub.md")

    def test_resolves_docs_root_relative_filename(self) -> None:
        target = resolve_markdown_target_path("mvp-v03.md", base_path=None)
        self.assertEqual(target, "docs/mvp-v03.md")

    def test_resolves_sibling_from_docs_base_path(self) -> None:
        target = resolve_markdown_target_path(
            "mvp-v03.md",
            base_path="docs/mvp.md",
        )
        self.assertEqual(target, "docs/mvp-v03.md")

    def test_rewrites_mvp_link_from_docs_page(self) -> None:
        html = render_markdown(
            "> see [mvp-v03.md](mvp-v03.md)",
            context=MarkdownRenderContext(
                project_id="prj_test",
                workspace_id="ws_test",
                base_path="docs/mvp.md",
            ),
        )
        self.assertIn(
            docs_view_url(
                project_id="prj_test",
                workspace_id="ws_test",
                doc_path="docs/mvp-v03.md",
            ),
            html,
        )
        self.assertNotIn('href="mvp-v03.md"', html)

    def test_rewrites_relative_link_to_doc_path_viewer(self) -> None:
        html = render_markdown(
            "[Parent audit](audit-v04-expanded-hub.md)",
            context=MarkdownRenderContext(
                project_id="prj_test",
                workspace_id="ws_test",
            ),
        )
        self.assertIn(
            docs_view_url(
                project_id="prj_test",
                workspace_id="ws_test",
                doc_path="docs/audits/audit-v04-expanded-hub.md",
            ),
            html,
        )
        self.assertNotIn('href="audit-v04-expanded-hub.md"', html)

    def test_rewrites_to_document_id_when_indexed(self) -> None:
        html = rewrite_document_links(
            '<p><a href="../mvp-v04.md">MVP</a></p>',
            context=MarkdownRenderContext(
                project_id="prj_test",
                workspace_id="ws_test",
                local_documents=(
                    LocalDocumentPreview(document_id="doc_mvp", storage_path="docs/mvp-v04.md"),
                ),
                base_path="docs/audits/current.md",
            ),
        )
        self.assertIn(
            docs_view_url(
                project_id="prj_test",
                workspace_id="ws_test",
                document_id="doc_mvp",
            ),
            html,
        )

    def test_leaves_external_links_untouched(self) -> None:
        html = render_markdown(
            "[GitHub](https://example.com)",
            context=MarkdownRenderContext(project_id="prj_test", workspace_id="ws_test"),
        )
        self.assertIn('href="https://example.com"', html)


if __name__ == "__main__":
    unittest.main()
