from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from runtime.shared.ids import ActorIdentity, node_proof_matches


class EnrollmentError(ValueError):
    pass


@dataclass(frozen=True)
class OwnerAssignment:
    project_id: str
    owner_node_id: str
    owner_display_name: str
    owner_status: str
    assigned_by_human_actor_id: str
    assigned_at: str


class EnrollmentRegistry:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")

    def invite_node(
        self,
        *,
        node_id: str,
        display_name: str,
        invitation_fingerprint: str,
        invited_by_human_actor_id: str,
        issued_at: str,
        authority: ActorIdentity | None = None,
    ) -> None:
        if self._has_active_nodes():
            self.require_human_authority(authority)
        self.db.execute(
            "INSERT INTO nodes (node_id, display_name, invitation_fingerprint, status, last_seen_at) VALUES (?,?,?,?,NULL)",
            (node_id, display_name, invitation_fingerprint, "pending"),
        )
        self.db.execute(
            "INSERT INTO enrollment_events (event_id, node_id, event_type, actor_human_id, recorded_at) VALUES (?,?,?,?,?)",
            (f"invite:{node_id}:{issued_at}", node_id, "invited", invited_by_human_actor_id, issued_at),
        )

    def accept_invitation(self, *, node_id: str, invitation_fingerprint: str, enrolled_at: str) -> dict:
        node = self._get_node(node_id)
        if not node:
            raise EnrollmentError("unknown node invitation")
        if node["status"] == "revoked":
            raise EnrollmentError("revoked invitations cannot enroll")
        if node["invitation_fingerprint"] != invitation_fingerprint:
            raise EnrollmentError("invitation fingerprint mismatch")
        self.db.execute(
            "UPDATE nodes SET status = 'active', last_seen_at = ? WHERE node_id = ?",
            (enrolled_at, node_id),
        )
        self.db.execute(
            "INSERT INTO enrollment_events (event_id, node_id, event_type, actor_human_id, recorded_at) VALUES (?,?,?,?,?)",
            (f"enroll:{node_id}:{enrolled_at}", node_id, "enrolled", None, enrolled_at),
        )
        return self.get_node_status(node_id)

    def touch_node(self, *, node_id: str, seen_at: str) -> None:
        self._require_node(node_id, allowed_statuses={"active"})
        self.db.execute("UPDATE nodes SET last_seen_at = ? WHERE node_id = ?", (seen_at, node_id))

    def revoke_node(
        self,
        *,
        node_id: str,
        revoked_by_human_actor_id: str,
        revoked_at: str,
        authority: ActorIdentity,
    ) -> None:
        self.require_human_authority(authority, expected_human_actor_id=revoked_by_human_actor_id)
        self._require_node(node_id, allowed_statuses={"pending", "active"})
        self.db.execute("UPDATE nodes SET status = 'revoked' WHERE node_id = ?", (node_id,))
        self.db.execute(
            "INSERT INTO enrollment_events (event_id, node_id, event_type, actor_human_id, recorded_at) VALUES (?,?,?,?,?)",
            (f"revoke:{node_id}:{revoked_at}", node_id, "revoked", revoked_by_human_actor_id, revoked_at),
        )

    def assign_owner(
        self,
        *,
        project_id: str,
        owner_node_id: str,
        assigned_by_human_actor_id: str,
        assigned_at: str,
        authority: ActorIdentity,
    ) -> OwnerAssignment:
        self.require_human_authority(authority, expected_human_actor_id=assigned_by_human_actor_id)
        node = self._require_node(owner_node_id, allowed_statuses={"active"})
        self.db.execute(
            "INSERT INTO project_owners (project_id, owner_node_id, assigned_by_human_actor_id, assigned_at) VALUES (?,?,?,?) "
            "ON CONFLICT(project_id) DO UPDATE SET owner_node_id = excluded.owner_node_id, assigned_by_human_actor_id = excluded.assigned_by_human_actor_id, assigned_at = excluded.assigned_at",
            (project_id, owner_node_id, assigned_by_human_actor_id, assigned_at),
        )
        return OwnerAssignment(project_id, owner_node_id, node["display_name"], node["status"], assigned_by_human_actor_id, assigned_at)

    def get_owner_assignment(self, project_id: str) -> OwnerAssignment | None:
        row = self.db.execute(
            "SELECT po.project_id, po.owner_node_id, n.display_name AS owner_display_name, n.status AS owner_status, po.assigned_by_human_actor_id, po.assigned_at "
            "FROM project_owners po JOIN nodes n ON n.node_id = po.owner_node_id WHERE po.project_id = ?",
            (project_id,),
        ).fetchone()
        return OwnerAssignment(**dict(row)) if row else None

    def list_enrolled_nodes(self) -> list[dict]:
        rows = self.db.execute(
            "SELECT node_id, display_name, status, last_seen_at FROM nodes ORDER BY node_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_node_status(self, node_id: str) -> dict:
        row = self._require_node(node_id, allowed_statuses={"pending", "active", "revoked"})
        data = dict(row)
        data.pop("invitation_fingerprint", None)
        return data

    def require_trusted_actor(self, actor: ActorIdentity, *, allowed_statuses: set[str] | None = None) -> None:
        if not actor.node_proof:
            raise EnrollmentError("trusted node proof is required")
        node = self._require_node(actor.node_id, allowed_statuses=allowed_statuses or {"active"})
        if not node_proof_matches(expected_fingerprint=node["invitation_fingerprint"], actor=actor):
            raise EnrollmentError("node proof mismatch")

    def require_project_access(self, actor: ActorIdentity, project_id: str) -> None:
        self.require_trusted_actor(actor)
        if self.has_project_access(actor.node_id, project_id):
            return
        raise EnrollmentError(f"node {actor.node_id} is not authorized for project {project_id}")

    def has_project_access(self, node_id: str, project_id: str) -> bool:
        queries = (
            ("SELECT 1 FROM project_owners WHERE project_id = ? AND owner_node_id = ? LIMIT 1", (project_id, node_id)),
            (
                "SELECT 1 FROM claim_leases WHERE project_id = ? AND node_id = ? AND status IN ('active','renewed') LIMIT 1",
                (project_id, node_id),
            ),
            (
                "SELECT 1 FROM mutation_routes WHERE destination_project_id = ? AND source_node_id = ? AND status IN ('proposed','routed') LIMIT 1",
                (project_id, node_id),
            ),
        )
        return any(self.db.execute(sql, params).fetchone() for sql, params in queries)

    def require_human_authority(self, actor: ActorIdentity | None, *, expected_human_actor_id: str | None = None) -> None:
        if actor is None or not actor.human_actor_id:
            raise EnrollmentError("human authority is required")
        if expected_human_actor_id is not None and actor.human_actor_id != expected_human_actor_id:
            raise EnrollmentError("human authority mismatch")
        self.require_trusted_actor(actor)

    def _has_active_nodes(self) -> bool:
        row = self.db.execute("SELECT 1 FROM nodes WHERE status = 'active' LIMIT 1").fetchone()
        return row is not None

    def _get_node(self, node_id: str) -> sqlite3.Row | None:
        return self.db.execute("SELECT * FROM nodes WHERE node_id = ?", (node_id,)).fetchone()

    def _require_node(self, node_id: str, *, allowed_statuses: set[str]) -> sqlite3.Row:
        node = self._get_node(node_id)
        if not node:
            raise EnrollmentError(f"unknown node: {node_id}")
        if node["status"] not in allowed_statuses:
            raise EnrollmentError(f"node {node_id} is not in an allowed status")
        return node
