from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime.hub.data import LocalDocumentPreview, ProjectSnapshot


@dataclass(frozen=True)
class ResolvedLocalDocument:
    document: LocalDocumentPreview
    path: Path


def resolve_local_document(
    *,
    project: ProjectSnapshot,
    document_id: str,
    repo_root: Path,
) -> ResolvedLocalDocument:
    cleaned_id = document_id.strip()
    if not cleaned_id:
        raise ValueError("document_id is required")
    document = next((item for item in project.local_documents if item.document_id == cleaned_id), None)
    if document is None:
        raise ValueError("unknown local document")
    return resolve_local_document_path(document=document, repo_root=repo_root)


def resolve_local_document_path(*, document: LocalDocumentPreview, repo_root: Path) -> ResolvedLocalDocument:
    candidate = Path(document.storage_path).expanduser()
    if not candidate.is_absolute():
        candidate = (repo_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    repo_root_resolved = repo_root.resolve()
    if candidate != repo_root_resolved and repo_root_resolved not in candidate.parents:
        raise ValueError("local document path must stay within the project repository")
    if not candidate.is_file():
        raise ValueError("local document file was not found")
    return ResolvedLocalDocument(document=document, path=candidate)


def resolve_repo_markdown_path(*, repo_root: Path, doc_path: str) -> Path:
    cleaned = doc_path.strip().lstrip("/")
    if not cleaned or cleaned.endswith("/"):
        raise ValueError("invalid document path")
    candidate = (repo_root / cleaned).resolve()
    repo_root_resolved = repo_root.resolve()
    if candidate != repo_root_resolved and repo_root_resolved not in candidate.parents:
        raise ValueError("document path must stay within the project repository")
    if not candidate.is_file():
        raise ValueError("document file was not found")
    if candidate.suffix.lower() != ".md":
        raise ValueError("only markdown documents are supported")
    return candidate
