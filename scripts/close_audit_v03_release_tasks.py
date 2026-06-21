#!/usr/bin/env python3
"""Close completed v0.3 release audit tasks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from runtime.node.bootstrap import NodeBootstrap
from runtime.node.current import claim_ready_task, transition_task

CLOSES = [
    ("tsk_ca7f40ad172755d2", "audit/v0.3/release/baseline-checklist", "Documented mvp-v03-baseline.md with pass/fail results."),
    ("tsk_6863264e03bc526f", "audit/v0.3/release/full-test-suite", "264 unittest tests OK outside sandbox."),
    ("tsk_11194c2c7fca5159", "audit/v0.3/release/installer-alignment", "pyproject data-files skills, capinstall verify OK."),
    ("tsk_bf3c1f7b49485482", "audit/v0.3/release/readme-alignment", "README quick-start and mvp-v03 pointers."),
    ("tsk_b488d726aa9c5006", "audit/v0.3/release/version-bump", "0.3.0 in pyproject.toml and debian/changelog."),
    ("tsk_de33554c44fa56ff", "audit/v0.3/release/fresh-install-smoke", "scripts/release_smoke.sh passes."),
    ("tsk_0b2d0a771f395f47", "audit/v0.3/release/demo-script", "docs/demo-v03.md five-minute demo."),
    ("tsk_2a49f7ab1db55709", "audit/v0.3/release/regression-gate", "Re-ran full suite green post-release changes."),
    ("tsk_736ed56585c554b2", "audit/v0.3/release/git-tag-v030", "Annotated tag v0.3.0 created."),
]

META = {
    "done_result": "MVP v0.3 release gate completed.",
    "done_artifacts": "pyproject.toml, debian/changelog, README.md, docs/mvp-v03-baseline.md, docs/demo-v03.md, scripts/release_smoke.sh",
    "done_references": "aud_365b26538f135fdb, v0.3.0",
    "done_expected_impact": "CapiForge v0.3 documentation hub MVP is release-ready from README path.",
}


def main() -> int:
    bootstrap = NodeBootstrap(repo_root=str(REPO_ROOT))
    results = []
    session = "capiforge-cli-close-v03-release"
    for task_id, lifecycle_key, summary in CLOSES:
        claim_ready_task(
            bootstrap,
            task_id=task_id,
            plan=f"Close {lifecycle_key}",
            lease_minutes=5,
            lock_timeout_seconds=30.0,
            agent_id="capiforge-cli",
            session_id=session,
            recover_stale_lock=True,
        )
        transition_task(
            bootstrap,
            task_id=task_id,
            requested_state="in_progress",
            summary=summary,
            agent_id="capiforge-cli",
            session_id=session,
            recover_stale_lock=True,
        )
        result = transition_task(
            bootstrap,
            task_id=task_id,
            requested_state="done",
            summary=summary,
            agent_id="capiforge-cli",
            session_id=session,
            recover_stale_lock=True,
            **META,
        )
        results.append({"task_id": task_id, "lifecycle_key": lifecycle_key, "state": result["state"]})
    print(json.dumps({"closed": results}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
