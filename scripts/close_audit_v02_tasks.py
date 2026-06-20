#!/usr/bin/env python3
"""Close in-progress v0.2 audit tasks with done metadata."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.current import transition_task

CLOSES = [
    {
        "task_id": "tsk_6703c8cfb8d459f6",
        "lifecycle_key": "audit/v0.2/mvp-acceptance-checklist",
        "done_result": "Added docs/mvp.md with operator/agent checklist, error recovery, and MVP done criteria.",
        "done_artifacts": "docs/mvp.md, docs/architecture-v01.md, AGENTS.md",
        "done_references": "audit/v0.2/mvp-acceptance-checklist",
        "done_expected_impact": "Operators and agents share one acceptance gate for MVP readiness.",
    },
    {
        "task_id": "tsk_938fced70005562f",
        "lifecycle_key": "audit/v0.2/ci-and-tests-stabilization",
        "done_result": "Full unittest suite passes (256 tests); restored origin_audit_id in tasks_reconcile_start.",
        "done_artifacts": "runtime/node/current.py, tests/node/multi_agent_claims_test.py",
        "done_references": "audit/v0.2/ci-and-tests-stabilization",
        "done_expected_impact": "CI gate can rely on python3 -m unittest discover without sandbox permission failures.",
    },
    {
        "task_id": "tsk_2862d911e4d65080",
        "lifecycle_key": "audit/v0.2/multi-agent-e2e",
        "done_result": "Added multi-agent claim integration tests and documented session/renew policy.",
        "done_artifacts": "tests/node/multi_agent_claims_test.py, docs/architecture-v01.md",
        "done_references": "audit/v0.2/multi-agent-e2e",
        "done_expected_impact": "Two sessions cannot claim the same task; renew extends lease for the holder.",
    },
    {
        "task_id": "tsk_82ce9ebbec75599b",
        "lifecycle_key": "audit/v0.2/no-ready-tasks-ux",
        "done_result": "Documented empty ready queue playbook in README and capiforge-pickup-task skill.",
        "done_artifacts": "README.md, skills/capiforge-pickup-task/SKILL.md",
        "done_references": "audit/v0.2/no-ready-tasks-ux",
        "done_expected_impact": "Agents return actionable next steps when tasks_ready_get is empty.",
    },
]


def main() -> int:
    bootstrap = NodeBootstrap(repo_root=str(REPO_ROOT))
    results = []
    for spec in CLOSES:
        result = transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="done",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id="capiforge-cli-current",
            done_result=spec["done_result"],
            done_artifacts=spec["done_artifacts"],
            done_references=spec["done_references"],
            done_expected_impact=spec["done_expected_impact"],
            recover_stale_lock=True,
        )
        results.append({"task_id": spec["task_id"], "lifecycle_key": spec["lifecycle_key"], "state": result["state"]})
    print(json.dumps({"closed": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
