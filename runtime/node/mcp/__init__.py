from __future__ import annotations

import json
import sqlite3

from runtime.coordinator.claims import ClaimConflictError, ClaimLeaseError, ClaimRegistry
from runtime.coordinator.enrollment import EnrollmentError, EnrollmentRegistry
from runtime.coordinator.mcp import CoordinatorMCPSurface
from runtime.node.index import INDEXES, NodeIndexBuilder
from runtime.node.router import CrossProjectGuardError, NodeRouter
from runtime.node.store import NodeStore
from runtime.shared.contracts import JustificationPayload, validate_justification, validate_ready_state, validate_task_state
from runtime.shared.errors import SurfaceError, unknown_resource
from runtime.shared.ids import ActorIdentity


class NodeMCPSurface:
    def __init__(
        self,
        *,
        store: NodeStore,
        router: NodeRouter,
        claims: ClaimRegistry | None = None,
        coordinator: CoordinatorMCPSurface | None = None,
        enrollment: EnrollmentRegistry | None = None,
        local_node_id: str | None = None,
    ):
        self.store = store
        self.router = router
        self.claims = claims
        self.coordinator = coordinator
        self.enrollment = enrollment
        self.local_node_id = local_node_id
        self.index = NodeIndexBuilder(store)

    def _task_not_found(self, task_id: str) -> SurfaceError:
        return unknown_resource("task", task_id)

    def _require_task(self, task_id: str) -> dict:
        task = self.store.get_task(task_id)
        if not task:
            raise self._task_not_found(task_id)
        return task

    def _require_project(self, project_id: str) -> dict:
        project = self.store.get_project(project_id)
        if not project:
            raise unknown_resource("project", project_id)
        return project

    def _require_task_for_project(self, *, task_id: str, project_id: str) -> dict:
        task = self._require_task(task_id)
        if task["project_id"] != project_id:
            raise SurfaceError("INVALID_TASK_STATE", "task does not belong to the supplied project")
        return task

    def _require_trusted_actor(self, actor: ActorIdentity | None) -> None:
        if not self.enrollment:
            return
        if actor is None:
            raise SurfaceError("AUTHORIZATION_REQUIRED", "operation requires an enrolled actor")
        if self.local_node_id and actor.node_id != self.local_node_id:
            raise SurfaceError("AUTHORIZATION_REQUIRED", "operation requires the local enrolled node actor")
        try:
            self.enrollment.require_trusted_actor(actor)
        except EnrollmentError as exc:
            raise SurfaceError("AUTHORIZATION_REQUIRED", str(exc)) from exc

    def _require_project_reader(self, *, project_id: str, actor: ActorIdentity | None) -> None:
        self._require_trusted_actor(actor)
        self._require_project(project_id)
        if actor is None:
            raise SurfaceError("AUTHORIZATION_REQUIRED", "project access requires an enrolled actor")
        if self.store.has_project_access(actor.node_id, project_id):
            return
        if self.enrollment and self.enrollment.has_project_access(actor.node_id, project_id):
            return
        raise SurfaceError("AUTHORIZATION_REQUIRED", f"node {actor.node_id} is not authorized for project {project_id}")

    def _require_local_project_reader(self, *, project_id: str) -> None:
        self._require_project(project_id)
        if not self.local_node_id:
            raise SurfaceError("AUTHORIZATION_REQUIRED", "operation requires a configured local node identity")
        if not self.store.has_project_access(self.local_node_id, project_id):
            raise SurfaceError("AUTHORIZATION_REQUIRED", f"node {self.local_node_id} is not authorized for project {project_id}")

    def _sync_active_claim_state(self, *, project_id: str, task_id: str, as_of: str | None, expected_session_id: str | None = None) -> None:
        task = self._require_task(task_id)
        if task["state"] not in {"claimed", "in_progress"}:
            return
        if not self.claims:
            raise SurfaceError("UNKNOWN_RESOURCE", "claim registry is unavailable")
        active_claim = self.claims.get_active_claim(project_id=project_id, task_id=task_id, as_of=as_of)
        if active_claim and (expected_session_id is None or active_claim.session_id == expected_session_id):
            self.store.cache_claim(task_id, active_claim.claim_id, active_claim.status, active_claim.lease_expires_at, active_claim.node_id, active_claim.agent_id, active_claim.session_id, active_claim.plan)
            return
        self.store.sync_task_with_claim(task_id, claim_status=active_claim.status if active_claim else None)

    def _require_active_claim(self, *, project_id: str, task_id: str, session_id: str, as_of: str | None) -> None:
        self._sync_active_claim_state(project_id=project_id, task_id=task_id, as_of=as_of, expected_session_id=session_id)
        active_claim = self.claims.get_active_claim(project_id=project_id, task_id=task_id, as_of=as_of) if self.claims else None
        if not active_claim or active_claim.session_id != session_id:
            raise SurfaceError("INVALID_TASK_STATE", "claimed and in_progress tasks require a matching active claim lease")

    def _route_owner_acceptance(self, *, route_id: str, project_id: str, actor: ActorIdentity, request_kind: str, justification, source_project_id: str | None = None, created_at: str | None = None) -> dict:
        if not self.coordinator:
            raise SurfaceError("UNKNOWN_RESOURCE", "coordinator surface is unavailable")
        return self.coordinator.route_request(
            route_id=route_id,
            destination_project_id=project_id,
            actor=actor,
            request_kind=request_kind,
            justification=justification,
            created_at=created_at or route_id,
            source_project_id=source_project_id,
        )

    def workspace_get(self, *, workspace_id: str, actor: ActorIdentity | None = None) -> dict:
        self._require_trusted_actor(actor)
        workspace = self.store.get_workspace(workspace_id)
        if not workspace:
            raise unknown_resource("workspace", workspace_id)
        projects = self.store.list_workspace_projects(workspace_id)
        if actor:
            projects = [
                project
                for project in projects
                if self.store.has_project_access(actor.node_id, project["project_id"])
                or (self.enrollment and self.enrollment.has_project_access(actor.node_id, project["project_id"]))
            ]
        return {"status": "ok", "data": workspace | {"projects": projects}}

    def project_entrypoint_get(self, *, project_id: str, as_of: str, actor: ActorIdentity | None = None) -> dict:
        self._require_project_reader(project_id=project_id, actor=actor)
        return {"status": "ok", "data": self.index.build_project_entrypoint(project_id, as_of)["entrypoint"]}

    def project_entrypoint_get_local(self, *, project_id: str, as_of: str) -> dict:
        self._require_local_project_reader(project_id=project_id)
        return {"status": "ok", "data": self.index.build_project_entrypoint(project_id, as_of, persist=False)["entrypoint"]}

    def tasks_list_by_index(self, *, project_id: str, index_name: str, as_of: str, limit: int = 20, actor: ActorIdentity | None = None) -> dict:
        self._require_project_reader(project_id=project_id, actor=actor)
        if index_name not in INDEXES:
            raise SurfaceError("INVALID_TASK_STATE", f"unsupported index: {index_name}")
        return {"status": "ok", "data": {"project_id": project_id, "index_name": index_name, "tasks": self.store.list_tasks_for_index(project_id, index_name, as_of)[:limit]}}

    def tasks_claim(
        self,
        *,
        claim_id: str,
        project_id: str,
        task_id: str,
        actor: ActorIdentity,
        plan: str,
        lease_started_at: str,
        lease_expires_at: str,
    ) -> dict:
        if not self.claims:
            raise SurfaceError("UNKNOWN_RESOURCE", "claim registry is unavailable")
        self._require_project_reader(project_id=project_id, actor=actor)
        task = self._require_task_for_project(task_id=task_id, project_id=project_id)
        if task["state"] != "ready":
            raise SurfaceError("INVALID_TASK_STATE", "only ready tasks can be claimed")
        try:
            claim = self.claims.claim_task(
                claim_id=claim_id,
                project_id=project_id,
                task_id=task_id,
                actor=actor,
                plan=plan,
                lease_started_at=lease_started_at,
                lease_expires_at=lease_expires_at,
            )
            self.store.cache_claim(task_id, claim.claim_id, claim.status, claim.lease_expires_at, claim.node_id, claim.agent_id, claim.session_id, claim.plan)
            self.store.update_task_state(task_id, state="claimed", active_claim_session_id=actor.session_id)
        except ClaimConflictError as exc:
            raise SurfaceError("CLAIM_CONFLICT", str(exc)) from exc
        return {"status": "claimed", "data": {"claim_id": claim.claim_id, "task_id": claim.task_id, "lease_expires_at": claim.lease_expires_at}}

    def tasks_release(
        self,
        *,
        project_id: str,
        task_id: str,
        claim_id: str,
        actor: ActorIdentity,
    ) -> dict:
        self._require_project_reader(project_id=project_id, actor=actor)
        self._require_task_for_project(task_id=task_id, project_id=project_id)
        if not self.claims:
            raise SurfaceError("UNKNOWN_RESOURCE", "claim registry is unavailable")
        try:
            existing = self.claims.get_claim(claim_id)
            if existing.project_id != project_id or existing.task_id != task_id:
                raise SurfaceError("INVALID_TASK_STATE", "claim does not match the supplied project and task")
            claim = self.claims.release_claim(claim_id=claim_id, actor=actor)
            if claim.project_id != project_id or claim.task_id != task_id:
                raise SurfaceError("INVALID_TASK_STATE", "claim does not match the supplied project and task")
        except ClaimLeaseError as exc:
            raise SurfaceError("INVALID_TASK_STATE", str(exc)) from exc
        self.store.cache_claim(task_id, claim.claim_id, claim.status, claim.lease_expires_at, claim.node_id, claim.agent_id, claim.session_id, claim.plan)
        self.store.sync_task_with_claim(task_id, claim_status=claim.status)
        return {"status": "accepted", "data": {"claim_id": claim.claim_id, "task_id": task_id, "state": self.store.get_task(task_id)["state"]}}

    def tasks_create_from_audit(
        self,
        *,
        task_id: str,
        project_id: str,
        audit_id: str,
        mutation_id: str,
        actor: ActorIdentity,
        priority: str,
        effort: str,
        risk: str,
        task_type: str,
        description: str,
        justification,
        execution_context: dict,
        initial_state: str = "proposed",
        source_project_id: str | None = None,
    ) -> dict:
        audit = self.store.get_audit(audit_id)
        self._require_project_reader(project_id=project_id, actor=actor)
        if not audit:
            raise unknown_resource("audit", audit_id)
        if audit["project_id"] != project_id:
            raise SurfaceError("INVALID_TASK_STATE", "origin audit must belong to the destination project")
        if audit["state"] != "published":
            raise SurfaceError("INVALID_TASK_STATE", "tasks must originate from a published audit")
        try:
            validate_task_state(initial_state)
            validate_justification(justification)
        except ValueError as exc:
            code = "JUSTIFICATION_REQUIRED" if "summary" in str(exc) or "evidence" in str(exc) or "impact" in str(exc) else "INVALID_TASK_STATE"
            raise SurfaceError(code, str(exc)) from exc
        if actor.node_id != self.router.resolve_owner_node_id(project_id):
            return self._route_owner_acceptance(
                route_id=mutation_id,
                project_id=project_id,
                actor=actor,
                request_kind="tasks.create_from_audit",
                justification=justification,
                source_project_id=source_project_id,
            )
        self.store.create_task(
            task_id,
            project_id,
            audit_id,
            initial_state,
            priority,
            effort,
            risk,
            task_type,
            description,
            justification_json=json.dumps({"summary": justification.summary, "evidence_refs": justification.evidence_refs, "expected_impact": justification.expected_impact}, sort_keys=True),
            execution_context_json=json.dumps(execution_context, sort_keys=True),
        )
        self.store.record_task_mutation(mutation_id, task_id, actor.node_id, actor.agent_id, actor.session_id, json.dumps({"request_kind": "tasks.create_from_audit", "audit_id": audit_id, "summary": justification.summary, "evidence_refs": justification.evidence_refs, "expected_impact": justification.expected_impact}, sort_keys=True), "canonical")
        return {"status": "accepted", "data": {"mutation_id": mutation_id, "task_id": task_id, "origin_audit_id": audit_id, "authority_mode": "canonical"}}

    def tasks_transition(
        self,
        *,
        project_id: str,
        task_id: str,
        mutation_id: str,
        actor: ActorIdentity,
        requested_state: str,
        justification,
        source_project_id: str | None = None,
        metadata: dict | None = None,
    ) -> dict:
        task = self._require_task(task_id)
        self._require_project_reader(project_id=project_id, actor=actor)
        if task["project_id"] != project_id:
            raise SurfaceError("INVALID_TASK_STATE", "task does not belong to the supplied project")
        metadata = metadata or {}
        try:
            validate_task_state(requested_state)
            validate_justification(justification)
            if requested_state == "ready":
                validate_ready_state(
                    description=task["description"],
                    justification_json=task["justification_json"],
                    execution_context_json=task["execution_context_json"],
                    conflict_status=metadata.get("conflict_status"),
                )
        except ValueError as exc:
            code = "JUSTIFICATION_REQUIRED" if "summary" in str(exc) or "evidence" in str(exc) or "impact" in str(exc) else "INVALID_TASK_STATE"
            raise SurfaceError(code, str(exc)) from exc
        if requested_state in {"claimed", "in_progress"}:
            self._require_active_claim(
                project_id=project_id,
                task_id=task_id,
                session_id=metadata.get("active_claim_session_id") or actor.session_id,
                as_of=metadata.get("as_of"),
            )
        try:
            decision = self.router.submit_task_mutation(project_id, task_id, mutation_id, actor, justification, requested_state, source_project_id=source_project_id)
            if decision.authority_mode == "canonical":
                self.store.update_task_state(
                    task_id,
                    state=requested_state,
                    active_claim_session_id=(metadata.get("active_claim_session_id") if requested_state in {"claimed", "in_progress"} else None),
                    blocked_reason=(metadata.get("blocked_reason") if requested_state == "blocked" else None),
                    blocked_evidence=(metadata.get("blocked_evidence") if requested_state == "blocked" else None),
                    blocked_next_step=(metadata.get("blocked_next_step") if requested_state == "blocked" else None),
                    done_result=(metadata.get("done_result") if requested_state == "done" else None),
                    done_artifacts=(metadata.get("done_artifacts") if requested_state == "done" else None),
                    done_references=(metadata.get("done_references") if requested_state == "done" else None),
                    done_expected_impact=(metadata.get("done_expected_impact") if requested_state == "done" else None),
                )
                return {"status": "accepted", "data": {"mutation_id": mutation_id, "authority_mode": decision.authority_mode, "owner_node_id": decision.owner_node_id}}
        except CrossProjectGuardError as exc:
            raise SurfaceError("CROSS_PROJECT_APPROVAL_REQUIRED", str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise SurfaceError("INVALID_TASK_STATE", str(exc)) from exc
        routed = self._route_owner_acceptance(
            route_id=mutation_id,
            project_id=project_id,
            actor=actor,
            request_kind="tasks.transition",
            justification=justification,
            source_project_id=source_project_id,
        )
        return {"status": "proposal_emitted", "data": {"mutation_id": mutation_id, "authority_mode": decision.authority_mode, "owner_node_id": decision.owner_node_id, **routed["data"]}}

    def tasks_override(
        self,
        *,
        project_id: str,
        task_id: str,
        mutation_id: str,
        actor: ActorIdentity,
        requested_state: str,
        metadata: dict | None = None,
    ) -> dict:
        task = self._require_task(task_id)
        self._require_trusted_actor(actor)
        self._require_project(project_id)
        if task["project_id"] != project_id:
            raise SurfaceError("INVALID_TASK_STATE", "task does not belong to the supplied project")
        if not actor.is_human_override():
            raise SurfaceError("INVALID_TASK_STATE", "tasks.override requires a human actor")
        metadata = metadata or {}
        try:
            validate_task_state(requested_state)
            if requested_state == "ready":
                validate_ready_state(
                    description=task["description"],
                    justification_json=task["justification_json"],
                    execution_context_json=task["execution_context_json"],
                    conflict_status=metadata.get("conflict_status", "clear"),
                )
        except ValueError as exc:
            raise SurfaceError("INVALID_TASK_STATE", str(exc)) from exc
        if requested_state in {"claimed", "in_progress"}:
            self._require_active_claim(
                project_id=project_id,
                task_id=task_id,
                session_id=metadata.get("active_claim_session_id") or actor.session_id,
                as_of=metadata.get("as_of"),
            )
        owner_node_id = self.router.resolve_owner_node_id(project_id)
        if actor.node_id != owner_node_id:
            human_justification = JustificationPayload(
                summary=metadata.get("reason", "human override"),
                evidence_refs=tuple(metadata.get("evidence_refs", ("human://override",))),
                expected_impact=metadata.get("expected_impact", "Apply human override"),
            )
            return self._route_owner_acceptance(
                route_id=mutation_id,
                project_id=project_id,
                actor=actor,
                request_kind="tasks.override",
                justification=human_justification,
            )
        self.store.record_task_mutation(
            mutation_id,
            task_id,
            actor.node_id,
            actor.agent_id,
            actor.session_id,
            json.dumps(
                {
                    "request_kind": "tasks.override",
                    "human_actor_id": actor.human_actor_id,
                    "requested_state": requested_state,
                    "reason": metadata.get("reason"),
                },
                sort_keys=True,
            ),
            "human_override",
        )
        self.store.update_task_state(
            task_id,
            state=requested_state,
            active_claim_session_id=(metadata.get("active_claim_session_id") if requested_state in {"claimed", "in_progress"} else None),
            blocked_reason=(metadata.get("blocked_reason") if requested_state == "blocked" else None),
            blocked_evidence=(metadata.get("blocked_evidence") if requested_state == "blocked" else None),
            blocked_next_step=(metadata.get("blocked_next_step") if requested_state == "blocked" else None),
            done_result=(metadata.get("done_result") if requested_state == "done" else None),
            done_artifacts=(metadata.get("done_artifacts") if requested_state == "done" else None),
            done_references=(metadata.get("done_references") if requested_state == "done" else None),
            done_expected_impact=(metadata.get("done_expected_impact") if requested_state == "done" else None),
        )
        return {"status": "accepted", "data": {"mutation_id": mutation_id, "task_id": task_id, "state": requested_state, "authority_mode": "human_override"}}

    def cross_project_request(
        self,
        *,
        route_id: str,
        source_project_id: str,
        destination_project_id: str,
        actor: ActorIdentity,
        justification,
        created_at: str,
    ) -> dict:
        self._require_trusted_actor(actor)
        if not self.store.is_cross_project_action_allowed(source_project_id, destination_project_id):
            raise SurfaceError("CROSS_PROJECT_APPROVAL_REQUIRED", "cross-project mutation requires explicit links and approval")
        if not self.coordinator:
            raise SurfaceError("UNKNOWN_RESOURCE", "coordinator surface is unavailable")
        return self.coordinator.cross_project_request(route_id=route_id, destination_project_id=destination_project_id, actor=actor, justification=justification, created_at=created_at, source_project_id=source_project_id)

    def sync_status(self, *, project_id: str, actor: ActorIdentity | None = None) -> dict:
        self._require_project_reader(project_id=project_id, actor=actor)
        if self.coordinator:
            return self.coordinator.sync_status(project_id=project_id, actor=actor)
        return {"status": "ok", "data": {"project_id": project_id, "degraded": True, "coordinator_authority": "non_authoritative", "canonical_write_path": "owner_node_local", "node_statuses": [], "pending_routes": 0}}

    def apply_accepted_cross_project_request(
        self,
        *,
        route_id: str,
        project_id: str,
        audit_id: str,
        task_id: str,
        mutation_id: str,
        actor: ActorIdentity,
        priority: str,
        effort: str,
        risk: str,
        task_type: str,
        description: str,
        execution_context: dict,
    ) -> dict:
        self._require_trusted_actor(actor)
        owner_node_id = self.router.resolve_owner_node_id(project_id)
        if actor.node_id != owner_node_id:
            raise SurfaceError("NON_OWNER_CANONICAL_WRITE", "only the destination owner node may apply accepted cross-project routes")
        if not self.coordinator:
            raise SurfaceError("UNKNOWN_RESOURCE", "coordinator surface is unavailable")
        route = self.coordinator.get_route(route_id=route_id, actor=actor)
        if route.status != "accepted":
            raise SurfaceError("INVALID_TASK_STATE", "cross-project route must be accepted before owner application")
        if route.destination_project_id != project_id or route.request_kind != "cross_project_request":
            raise SurfaceError("INVALID_TASK_STATE", "route does not match the supplied destination project")
        payload = json.loads(route.justification_json)
        return self.tasks_create_from_audit(
            task_id=task_id,
            project_id=project_id,
            audit_id=audit_id,
            mutation_id=mutation_id,
            actor=actor,
            priority=priority,
            effort=effort,
            risk=risk,
            task_type=task_type,
            description=description,
            justification=JustificationPayload(
                summary=payload["summary"],
                evidence_refs=tuple(payload["evidence_refs"]),
                expected_impact=payload["expected_impact"],
            ),
            execution_context=execution_context | {"cross_project_route_id": route_id, "source_project_id": payload.get("source_project_id")},
            initial_state="ready",
            source_project_id=payload.get("source_project_id"),
        )

    def audit_content_update(self, *, audit_id: str, content: str, actor: ActorIdentity) -> dict:
        audit = self.store.get_audit(audit_id)
        if not audit:
            raise unknown_resource("audit", audit_id)
        self._require_trusted_actor(actor)
        if not actor.is_human_override():
            raise SurfaceError("INVALID_TASK_STATE", "audit.content.update requires a human actor")
        owner_node_id = self.router.resolve_owner_node_id(audit["project_id"])
        if actor.node_id != owner_node_id:
            raise SurfaceError("NON_OWNER_CANONICAL_WRITE", "only the owner node may edit audit content directly")
        try:
            self.store.update_audit_content(audit_id, content)
        except sqlite3.IntegrityError as exc:
            if "closed audits are immutable" in str(exc):
                raise SurfaceError("AUDIT_CLOSED_IMMUTABLE", "closed audits require addendum or follow-up flow") from exc
            raise
        return {"status": "accepted", "data": {"audit_id": audit_id}}
