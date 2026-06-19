from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from runtime.node.store import NodeStore
from runtime.shared.contracts import validate_justification, validate_task_state
from runtime.shared.ids import ActorIdentity


class CrossProjectGuardError(ValueError):
    pass


@dataclass(frozen=True)
class RouteDecision:
    status: str
    owner_node_id: str
    mutation_id: str
    authority_mode: str


class NodeRouter:
    def __init__(self, store: NodeStore):
        self.store = store

    def resolve_owner_node_id(self, project_id: str) -> str:
        return self.store.owner_node_id(project_id)

    def submit_task_mutation(self, project_id: str, task_id: str, mutation_id: str, actor: ActorIdentity, justification, requested_state: str, source_project_id: str | None = None) -> RouteDecision:
        if not self.store.task_belongs_to_project(task_id, project_id):
            raise ValueError("task does not belong to project")
        validate_task_state(requested_state)
        validate_justification(justification)
        if source_project_id and source_project_id != project_id and not self.store.is_cross_project_action_allowed(source_project_id, project_id):
            raise CrossProjectGuardError("cross-project mutation requires explicit links and approval")
        owner_node_id = self.resolve_owner_node_id(project_id)
        authority_mode = "canonical" if actor.node_id == owner_node_id else "proposal"
        payload = json.dumps({"request_kind": "task_transition", "requested_state": requested_state, "source_project_id": source_project_id, **asdict(justification)}, sort_keys=True)
        self.store.record_task_mutation(mutation_id, task_id, actor.node_id, actor.agent_id, actor.session_id, payload, authority_mode)
        return RouteDecision("accepted" if authority_mode == "canonical" else "proposal_emitted", owner_node_id, mutation_id, authority_mode)

    def accept_proposal(self, proposal_mutation_id: str, accepted_mutation_id: str, actor: ActorIdentity) -> RouteDecision:
        proposal = self.store.get_task_mutation(proposal_mutation_id)
        if not proposal or proposal["authority_mode"] != "proposal":
            raise ValueError("proposal mutation not found")
        owner_node_id = self.resolve_owner_node_id(proposal["project_id"])
        if actor.node_id != owner_node_id:
            raise ValueError("only owner node may accept routed proposals")
        payload = json.loads(proposal["justification_json"])
        payload["accepted_proposal_id"] = proposal_mutation_id
        self.store.record_task_mutation(accepted_mutation_id, proposal["task_id"], actor.node_id, actor.agent_id, actor.session_id, json.dumps(payload, sort_keys=True), "canonical")
        return RouteDecision("accepted", owner_node_id, accepted_mutation_id, "canonical")
