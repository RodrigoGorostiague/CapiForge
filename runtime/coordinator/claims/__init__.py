from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from runtime.shared.ids import ActorIdentity, node_proof_matches


class ClaimConflictError(ValueError):
    pass


class ClaimLeaseError(ValueError):
    pass


@dataclass(frozen=True)
class ClaimLease:
    claim_id: str
    project_id: str
    task_id: str
    node_id: str
    agent_id: str
    session_id: str
    plan: str
    status: str
    lease_started_at: str
    lease_expires_at: str


class ClaimRegistry:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")

    def claim_task(
        self,
        *,
        claim_id: str,
        project_id: str,
        task_id: str,
        actor: ActorIdentity,
        plan: str,
        lease_started_at: str,
        lease_expires_at: str,
    ) -> ClaimLease:
        self._require_trusted_actor(actor)
        self.expire_claims(as_of=lease_started_at)
        try:
            self.db.execute(
                "INSERT INTO claim_leases (claim_id, project_id, task_id, node_id, agent_id, session_id, plan, status, lease_started_at, lease_expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (claim_id, project_id, task_id, actor.node_id, actor.agent_id, actor.session_id, plan, "active", lease_started_at, lease_expires_at),
            )
        except sqlite3.IntegrityError as exc:
            raise ClaimConflictError("task already has an active claim") from exc
        return self.get_claim(claim_id)

    def renew_claim(self, *, claim_id: str, actor: ActorIdentity, lease_expires_at: str, renewed_at: str) -> ClaimLease:
        claim = self._require_claim_owner(claim_id, actor)
        if claim["status"] not in {"active", "renewed"}:
            raise ClaimLeaseError("only active claims can be renewed")
        self.expire_claims(as_of=renewed_at)
        claim = self._require_claim_owner(claim_id, actor)
        if claim["status"] == "expired":
            raise ClaimLeaseError("expired claims cannot be renewed")
        self.db.execute(
            "UPDATE claim_leases SET status = 'renewed', lease_expires_at = ? WHERE claim_id = ?",
            (lease_expires_at, claim_id),
        )
        return self.get_claim(claim_id)

    def release_claim(self, *, claim_id: str, actor: ActorIdentity) -> ClaimLease:
        claim = self._require_claim_owner(claim_id, actor)
        if claim["status"] not in {"active", "renewed"}:
            raise ClaimLeaseError("only active claims can be released")
        self.db.execute("UPDATE claim_leases SET status = 'released' WHERE claim_id = ?", (claim_id,))
        return self.get_claim(claim_id)

    def expire_claims(self, *, as_of: str) -> int:
        cursor = self.db.execute(
            "UPDATE claim_leases SET status = 'expired' WHERE status IN ('active','renewed') AND lease_expires_at <= ?",
            (as_of,),
        )
        return cursor.rowcount

    def list_stale_claims(self, *, as_of: str) -> list[dict]:
        self.expire_claims(as_of=as_of)
        rows = self.db.execute(
            "SELECT claim_id, project_id, task_id, node_id, agent_id, session_id, plan, status, lease_started_at, lease_expires_at FROM claim_leases WHERE status = 'expired' ORDER BY lease_expires_at, claim_id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get_claim(self, claim_id: str) -> ClaimLease:
        row = self.db.execute(
            "SELECT claim_id, project_id, task_id, node_id, agent_id, session_id, plan, status, lease_started_at, lease_expires_at FROM claim_leases WHERE claim_id = ?",
            (claim_id,),
        ).fetchone()
        if not row:
            raise ClaimLeaseError("unknown claim")
        return ClaimLease(**dict(row))

    def get_active_claim(self, *, project_id: str, task_id: str, as_of: str | None = None) -> ClaimLease | None:
        if as_of is not None:
            self.expire_claims(as_of=as_of)
        row = self.db.execute(
            "SELECT claim_id, project_id, task_id, node_id, agent_id, session_id, plan, status, lease_started_at, lease_expires_at "
            "FROM claim_leases WHERE project_id = ? AND task_id = ? AND status IN ('active','renewed') ORDER BY lease_expires_at DESC LIMIT 1",
            (project_id, task_id),
        ).fetchone()
        return ClaimLease(**dict(row)) if row else None

    def _require_active_node(self, node_id: str) -> None:
        row = self.db.execute("SELECT 1 FROM nodes WHERE node_id = ? AND status = 'active'", (node_id,)).fetchone()
        if not row:
            raise ClaimLeaseError("claims require an enrolled active node")

    def _require_trusted_actor(self, actor: ActorIdentity) -> None:
        self._require_active_node(actor.node_id)
        row = self.db.execute("SELECT invitation_fingerprint FROM nodes WHERE node_id = ?", (actor.node_id,)).fetchone()
        if not row or not node_proof_matches(expected_fingerprint=row["invitation_fingerprint"], actor=actor):
            raise ClaimLeaseError("claims require trusted enrolled node proof")

    def _require_claim_owner(self, claim_id: str, actor: ActorIdentity) -> sqlite3.Row:
        row = self.db.execute("SELECT * FROM claim_leases WHERE claim_id = ?", (claim_id,)).fetchone()
        if not row:
            raise ClaimLeaseError("unknown claim")
        if (row["node_id"], row["agent_id"], row["session_id"]) != (actor.node_id, actor.agent_id, actor.session_id):
            raise ClaimLeaseError("claim ownership mismatch")
        return row
