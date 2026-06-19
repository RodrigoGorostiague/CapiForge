from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass

from runtime.shared.contracts import JustificationPayload, validate_justification
from runtime.shared.ids import ActorIdentity, node_proof_matches


class RouteValidationError(ValueError):
    pass


class CrossProjectApprovalError(RouteValidationError):
    pass


@dataclass(frozen=True)
class RoutedMutation:
    route_id: str
    destination_project_id: str
    destination_owner_node_id: str
    source_node_id: str
    request_kind: str
    status: str
    justification_json: str
    created_at: str


class MutationRouteRegistry:
    def __init__(self, connection: sqlite3.Connection):
        self.db = connection
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")

    def submit_proposal(
        self,
        *,
        route_id: str,
        destination_project_id: str,
        actor: ActorIdentity,
        request_kind: str,
        justification: JustificationPayload,
        created_at: str,
        source_project_id: str | None = None,
    ) -> RoutedMutation:
        validate_justification(justification)
        self._require_trusted_actor(actor)
        self._require_proposal_access(
            actor=actor,
            destination_project_id=destination_project_id,
            source_project_id=source_project_id,
        )
        owner_node_id = self._require_owner_node(destination_project_id)
        if request_kind == "cross_project_request":
            self._require_cross_project_approval(
                source_project_id=source_project_id,
                destination_project_id=destination_project_id,
                owner_node_id=owner_node_id,
            )
        if actor.node_id == owner_node_id:
            raise RouteValidationError("owner node must perform canonical writes locally")
        payload = {
            "request_kind": request_kind,
            "source_project_id": source_project_id,
            **asdict(justification),
        }
        self.db.execute(
            "INSERT INTO mutation_routes (route_id, source_node_id, destination_project_id, destination_owner_node_id, request_kind, status, justification_json, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (route_id, actor.node_id, destination_project_id, owner_node_id, request_kind, "proposed", json.dumps(payload, sort_keys=True), created_at),
        )
        return self.get_route(route_id)

    def mark_routed(self, *, route_id: str) -> RoutedMutation:
        route = self.get_route(route_id)
        if route.status != "proposed":
            raise RouteValidationError("only proposed routes can be marked routed")
        self.db.execute("UPDATE mutation_routes SET status = 'routed' WHERE route_id = ?", (route_id,))
        return self.get_route(route_id)

    def owner_decision(self, *, route_id: str, owner_actor: ActorIdentity, accept: bool) -> RoutedMutation:
        self._require_trusted_actor(owner_actor)
        route = self.get_route(route_id)
        current_owner = self._require_owner_node(route.destination_project_id)
        if owner_actor.node_id != current_owner:
            raise RouteValidationError("only the current owner node may decide routed mutations")
        if route.status not in {"proposed", "routed"}:
            raise RouteValidationError("routed mutation already resolved")
        if accept and route.request_kind == "cross_project_request":
            payload = json.loads(route.justification_json)
            self._require_cross_project_approval(
                source_project_id=payload.get("source_project_id"),
                destination_project_id=route.destination_project_id,
                owner_node_id=current_owner,
            )
        status = "accepted" if accept else "rejected"
        self.db.execute(
            "UPDATE mutation_routes SET status = ?, destination_owner_node_id = ? WHERE route_id = ?",
            (status, current_owner, route_id),
        )
        return self.get_route(route_id)

    def announce_sync_status(
        self,
        *,
        announcement_id: str,
        node_id: str,
        actor: ActorIdentity,
        project_id: str,
        sync_status: str,
        summary: dict,
        announced_at: str,
    ) -> None:
        self._require_trusted_actor(actor)
        if actor.node_id != node_id:
            raise RouteValidationError("sync announcements must be reported by the enrolled node itself")
        self._require_project_access(actor.node_id, project_id)
        self.db.execute(
            "INSERT INTO sync_announcements (announcement_id, node_id, project_id, sync_status, summary_json, announced_at) VALUES (?,?,?,?,?,?)",
            (announcement_id, node_id, project_id, sync_status, json.dumps(summary, sort_keys=True), announced_at),
        )

    def project_sync_summary(self, project_id: str) -> dict:
        owner_node_id = self._require_owner_node(project_id)
        rows = self.db.execute(
            "SELECT sa.node_id, sa.sync_status, sa.summary_json, sa.announced_at FROM sync_announcements sa "
            "JOIN (SELECT node_id, MAX(announced_at) AS announced_at FROM sync_announcements WHERE project_id = ? GROUP BY node_id) latest "
            "ON latest.node_id = sa.node_id AND latest.announced_at = sa.announced_at WHERE sa.project_id = ? ORDER BY sa.node_id",
            (project_id, project_id),
        ).fetchall()
        statuses = [dict(row) | {"summary": json.loads(row["summary_json"])} for row in rows]
        degraded = any(row["sync_status"] != "healthy" for row in rows) or not rows
        pending_routes = self.db.execute(
            "SELECT COUNT(*) FROM mutation_routes WHERE destination_project_id = ? AND status IN ('proposed','routed')",
            (project_id,),
        ).fetchone()[0]
        return {
            "project_id": project_id,
            "owner_node_id": owner_node_id,
            "coordinator_authority": "non_authoritative",
            "canonical_write_path": "owner_node_local",
            "pending_routes": pending_routes,
            "degraded": degraded,
            "node_statuses": statuses,
        }

    def get_route(self, route_id: str) -> RoutedMutation:
        row = self.db.execute(
            "SELECT route_id, destination_project_id, destination_owner_node_id, source_node_id, request_kind, status, justification_json, created_at FROM mutation_routes WHERE route_id = ?",
            (route_id,),
        ).fetchone()
        if not row:
            raise RouteValidationError("unknown route")
        return RoutedMutation(**dict(row))

    def _require_owner_node(self, project_id: str) -> str:
        row = self.db.execute("SELECT owner_node_id FROM project_owners WHERE project_id = ?", (project_id,)).fetchone()
        if not row:
            raise RouteValidationError("destination project has no owner assignment")
        owner_node_id = row["owner_node_id"]
        self._require_active_node(owner_node_id)
        return owner_node_id

    def _require_active_node(self, node_id: str) -> None:
        row = self.db.execute("SELECT 1 FROM nodes WHERE node_id = ? AND status = 'active'", (node_id,)).fetchone()
        if not row:
            raise RouteValidationError("route requires an enrolled active node")

    def _require_trusted_actor(self, actor: ActorIdentity) -> None:
        self._require_active_node(actor.node_id)
        row = self.db.execute("SELECT invitation_fingerprint FROM nodes WHERE node_id = ?", (actor.node_id,)).fetchone()
        if not row or not node_proof_matches(expected_fingerprint=row["invitation_fingerprint"], actor=actor):
            raise RouteValidationError("route requires trusted enrolled node proof")

    def _require_project_access(self, node_id: str, project_id: str) -> None:
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
        if any(self.db.execute(sql, params).fetchone() for sql, params in queries):
            return
        raise RouteValidationError("sync announcements require project-scoped authorization")

    def _require_proposal_access(self, *, actor: ActorIdentity, destination_project_id: str, source_project_id: str | None) -> None:
        authorized_project_id = source_project_id or destination_project_id
        try:
            self._require_project_access(actor.node_id, authorized_project_id)
        except RouteValidationError as exc:
            raise RouteValidationError(
                f"routed mutation requires project-scoped authorization for {authorized_project_id}"
            ) from exc

    def _require_cross_project_approval(self, *, source_project_id: str | None, destination_project_id: str, owner_node_id: str) -> None:
        if not source_project_id:
            raise CrossProjectApprovalError("cross-project mutation requires a source project")
        row = self.db.execute(
            "SELECT 1 FROM notice_approvals WHERE source_project_id = ? AND target_project_id = ? AND approval_status = 'approved' AND routed_to_owner_node_id = ? LIMIT 1",
            (source_project_id, destination_project_id, owner_node_id),
        ).fetchone()
        if not row:
            raise CrossProjectApprovalError("cross-project mutation requires recorded coordinator notice and approval")

    def _require_active_or_revoked_node(self, node_id: str) -> None:
        row = self.db.execute("SELECT 1 FROM nodes WHERE node_id = ? AND status IN ('active','revoked')", (node_id,)).fetchone()
        if not row:
            raise RouteValidationError("sync announcements require a known node")
