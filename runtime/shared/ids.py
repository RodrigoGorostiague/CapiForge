from __future__ import annotations

import hmac
from hashlib import sha256
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

PREFIXES = {
    "workspace": "ws",
    "project": "prj",
    "audit": "aud",
    "task": "tsk",
    "artifact": "art",
    "link": "lnk",
    "node": "node",
    "claim": "clm",
    "route": "rte",
}


def canonical_id(kind: str, *parts: str) -> str:
    if kind not in PREFIXES:
        raise ValueError(f"unsupported kind: {kind}")
    if not parts or any(not part for part in parts):
        raise ValueError("canonical IDs require non-empty parts")
    digest = uuid5(NAMESPACE_URL, ":".join((kind, *parts))).hex[:16]
    return f"{PREFIXES[kind]}_{digest}"


def derive_node_proof(*, node_id: str, agent_id: str, session_id: str, invitation_fingerprint: str) -> str:
    payload = f"{node_id}:{agent_id}:{session_id}".encode("utf-8")
    secret = invitation_fingerprint.encode("utf-8")
    return hmac.new(secret, payload, sha256).hexdigest()


def node_proof_matches(*, expected_fingerprint: str, actor: "ActorIdentity") -> bool:
    if not actor.node_proof:
        return False
    expected = derive_node_proof(
        node_id=actor.node_id,
        agent_id=actor.agent_id,
        session_id=actor.session_id,
        invitation_fingerprint=expected_fingerprint,
    )
    return hmac.compare_digest(actor.node_proof, expected)


@dataclass(frozen=True)
class ActorIdentity:
    node_id: str
    agent_id: str
    session_id: str
    human_actor_id: str | None = None
    node_proof: str | None = None

    def is_human_override(self) -> bool:
        return self.human_actor_id is not None
