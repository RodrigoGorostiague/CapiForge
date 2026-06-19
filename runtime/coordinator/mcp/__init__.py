from __future__ import annotations

from runtime.coordinator.enrollment import EnrollmentRegistry, EnrollmentError
from runtime.coordinator.routes import CrossProjectApprovalError, MutationRouteRegistry, RouteValidationError
from runtime.shared.errors import SurfaceError
from runtime.shared.ids import ActorIdentity


class CoordinatorMCPSurface:
    def __init__(self, routes: MutationRouteRegistry, enrollment: EnrollmentRegistry | None = None):
        self.routes = routes
        self.enrollment = enrollment

    def _require_reader(self, actor: ActorIdentity | None) -> None:
        if not self.enrollment:
            return
        if actor is None:
            raise SurfaceError("AUTHORIZATION_REQUIRED", "read access requires an enrolled actor")
        try:
            self.enrollment.require_trusted_actor(actor)
        except EnrollmentError as exc:
            raise SurfaceError("AUTHORIZATION_REQUIRED", str(exc)) from exc

    def _require_project_reader(self, actor: ActorIdentity | None, project_id: str) -> None:
        if not self.enrollment:
            return
        if actor is None:
            raise SurfaceError("AUTHORIZATION_REQUIRED", "read access requires an enrolled actor")
        try:
            self.enrollment.require_project_access(actor, project_id)
        except EnrollmentError as exc:
            raise SurfaceError("AUTHORIZATION_REQUIRED", str(exc)) from exc

    def route_request(
        self,
        *,
        route_id: str,
        destination_project_id: str,
        actor: ActorIdentity,
        request_kind: str,
        justification,
        created_at: str,
        source_project_id: str | None = None,
    ) -> dict:
        if self.enrollment:
            try:
                self.enrollment.require_trusted_actor(actor)
                self.enrollment.require_project_access(actor, source_project_id or destination_project_id)
            except EnrollmentError as exc:
                raise SurfaceError("AUTHORIZATION_REQUIRED", str(exc)) from exc
        try:
            self.routes.submit_proposal(
                route_id=route_id,
                destination_project_id=destination_project_id,
                actor=actor,
                request_kind=request_kind,
                justification=justification,
                created_at=created_at,
                source_project_id=source_project_id,
            )
            routed = self.routes.mark_routed(route_id=route_id)
        except CrossProjectApprovalError as exc:
            raise SurfaceError("CROSS_PROJECT_APPROVAL_REQUIRED", str(exc)) from exc
        except RouteValidationError as exc:
            raise SurfaceError("NON_OWNER_CANONICAL_WRITE", str(exc)) from exc
        return {
            "status": "proposal_emitted",
            "data": {
                "route_id": routed.route_id,
                "destination_owner_node_id": routed.destination_owner_node_id,
                "request_kind": routed.request_kind,
                "route_status": "owner_acceptance_required",
                "acceptance_signal": "ROUTE_OWNER_ACCEPTANCE_REQUIRED",
            },
        }

    def cross_project_request(
        self,
        *,
        route_id: str,
        destination_project_id: str,
        actor: ActorIdentity,
        justification,
        created_at: str,
        source_project_id: str,
    ) -> dict:
        response = self.route_request(
            route_id=route_id,
            destination_project_id=destination_project_id,
            actor=actor,
            request_kind="cross_project_request",
            justification=justification,
            created_at=created_at,
            source_project_id=source_project_id,
        )
        return {
            "status": "routed",
            "data": {
                "route_id": response["data"]["route_id"],
                "destination_owner_node_id": response["data"]["destination_owner_node_id"],
                "request_kind": response["data"]["request_kind"],
            },
        }

    def sync_status(self, *, project_id: str, actor: ActorIdentity | None = None) -> dict:
        self._require_project_reader(actor, project_id)
        return {"status": "ok", "data": self.routes.project_sync_summary(project_id)}

    def get_route(self, *, route_id: str, actor: ActorIdentity | None = None):
        self._require_reader(actor)
        route = self.routes.get_route(route_id)
        if self.enrollment and actor is not None:
            try:
                if actor.node_id != route.source_node_id:
                    self.enrollment.require_project_access(actor, route.destination_project_id)
            except EnrollmentError as exc:
                raise SurfaceError("AUTHORIZATION_REQUIRED", str(exc)) from exc
        return route
