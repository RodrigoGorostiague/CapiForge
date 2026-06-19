from __future__ import annotations

from dataclasses import dataclass
import json

from runtime.shared.ids import ActorIdentity

TASK_STATES = {"proposed", "ready", "claimed", "in_progress", "blocked", "done", "cancelled"}


class AuthorityError(ValueError):
    pass


@dataclass(frozen=True)
class JustificationPayload:
    summary: str
    evidence_refs: tuple[str, ...]
    expected_impact: str


def validate_justification(payload: JustificationPayload) -> None:
    if not payload.summary.strip():
        raise ValueError("summary is required")
    if not payload.evidence_refs:
        raise ValueError("at least one evidence reference is required")
    if not payload.expected_impact.strip():
        raise ValueError("expected impact is required")


def validate_owner_write(*, owner_node_id: str, actor: ActorIdentity, canonical_write: bool) -> None:
    if canonical_write and actor.node_id != owner_node_id:
        raise AuthorityError("canonical writes require the owner node")


def validate_task_state(state: str) -> None:
    if state not in TASK_STATES:
        raise ValueError(f"unsupported task state: {state}")


def has_meaningful_json_content(raw: str) -> bool:
    if not raw or not raw.strip():
        return False
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return bool(raw.strip())
    if parsed in ({}, [], None, ""):
        return False
    return True


def validate_ready_state(*, description: str, justification_json: str, execution_context_json: str, conflict_status: str | None) -> None:
    if not description.strip():
        raise ValueError("ready tasks require a description")
    if not has_meaningful_json_content(justification_json):
        raise ValueError("ready tasks require valid justification")
    if conflict_status != "clear":
        raise ValueError("ready tasks require resolved conflict status")
    if not has_meaningful_json_content(execution_context_json):
        raise ValueError("ready tasks require execution context")
