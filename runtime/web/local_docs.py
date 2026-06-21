from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from runtime.tui.data import LocalDocumentPreview, ProjectSnapshot


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
