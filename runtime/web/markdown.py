from __future__ import annotations

from markdown_it import MarkdownIt


def render_markdown(content: str) -> str:
    md = MarkdownIt("commonmark", {"html": False, "linkify": True})
    return md.render(content or "")
