from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import urlencode

from markdown_it import MarkdownIt

from runtime.hub.data import LocalDocumentPreview

_LINK_RE = re.compile(r'(<a href=")([^"]+)(")')
_DEFAULT_AUDIT_DOC_DIR = "docs/audits"


@dataclass(frozen=True)
class MarkdownRenderContext:
    project_id: str
    workspace_id: str
    local_documents: tuple[LocalDocumentPreview, ...] = ()
    base_path: str | None = None


def _normalize_posix_path(path: str) -> str:
    parts: list[str] = []
    for part in PurePosixPath(path).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def _basename_index(documents: tuple[LocalDocumentPreview, ...]) -> dict[str, str]:
    index: dict[str, str] = {}
    for document in documents:
        name = PurePosixPath(document.storage_path).name
        existing = index.get(name)
        if existing is None or document.storage_path.count("/") < existing.count("/"):
            index[name] = document.storage_path
    return index


def resolve_markdown_target_path(
    href: str,
    *,
    base_path: str | None,
    local_documents: tuple[LocalDocumentPreview, ...] = (),
) -> str | None:
    cleaned = href.strip()
    if not cleaned or cleaned.startswith("#"):
        return None
    if "://" in cleaned or cleaned.startswith("mailto:"):
        return None
    if cleaned.startswith("/"):
        target = cleaned.lstrip("/")
    elif base_path:
        base_dir = str(PurePosixPath(base_path).parent)
        target = str(PurePosixPath(base_dir) / cleaned)
    elif "/" not in cleaned and cleaned.endswith(".md"):
        by_name = _basename_index(local_documents)
        if cleaned in by_name:
            target = by_name[cleaned]
        elif cleaned.startswith("audit-"):
            target = f"{_DEFAULT_AUDIT_DOC_DIR}/{cleaned}"
        else:
            target = f"docs/{cleaned}"
    else:
        target = cleaned
    return _normalize_posix_path(target)


def _document_index(documents: tuple[LocalDocumentPreview, ...]) -> dict[str, str]:
    index: dict[str, str] = {}
    for document in documents:
        index[document.storage_path] = document.document_id
    return index


def docs_view_url(
    *,
    project_id: str,
    workspace_id: str,
    document_id: str | None = None,
    audit_id: str | None = None,
    doc_path: str | None = None,
) -> str:
    params = {
        "project_id": project_id,
        "workspace_id": workspace_id,
    }
    if document_id:
        params["document_id"] = document_id
    if audit_id:
        params["audit_id"] = audit_id
    if doc_path:
        params["doc_path"] = doc_path
    return f"/docs?{urlencode(params)}"


def rewrite_document_links(html: str, *, context: MarkdownRenderContext) -> str:
    by_path = _document_index(context.local_documents)

    def replace_link(match: re.Match[str]) -> str:
        prefix, href, suffix = match.groups()
        target_path = resolve_markdown_target_path(
            href,
            base_path=context.base_path,
            local_documents=context.local_documents,
        )
        if not target_path:
            return match.group(0)
        document_id = by_path.get(target_path)
        if document_id:
            url = docs_view_url(
                project_id=context.project_id,
                workspace_id=context.workspace_id,
                document_id=document_id,
            )
        else:
            url = docs_view_url(
                project_id=context.project_id,
                workspace_id=context.workspace_id,
                doc_path=target_path,
            )
        return f'{prefix}{url}{suffix}'

    return _LINK_RE.sub(replace_link, html)


def render_markdown(content: str, *, context: MarkdownRenderContext | None = None) -> str:
    md = MarkdownIt("commonmark", {"html": False, "linkify": True})
    html = md.render(content or "")
    if context is not None:
        html = rewrite_document_links(html, context=context)
    return html
