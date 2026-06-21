#!/usr/bin/env python3
"""Close completed v0.4 release gate tasks."""

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
    {
        "task_id": "tsk_65f30dc411d35c59",
        "lifecycle_key": "audit/v0.4/release/baseline-checklist",
        "done_result": "Documented mvp-v04-baseline.md; capinstall verify ok, automated checks green.",
        "done_artifacts": "docs/mvp-v04-baseline.md, docs/mvp-v04.md",
        "done_references": "audit/v0.4/release/baseline-checklist",
        "done_expected_impact": "v0.4 release baseline is recorded for operators.",
    },
    {
        "task_id": "tsk_cad22ba9c25f59f7",
        "lifecycle_key": "audit/v0.4/release/full-test-suite",
        "done_result": "189 unittest tests OK; fixed expired-claim finish commit in runtime/node/current.py.",
        "done_artifacts": "runtime/node/current.py, tests/node/bootstrap_cli_test.py, tests/node/current_runtime_test.py",
        "done_references": "audit/v0.4/release/full-test-suite",
        "done_expected_impact": "R1 release gate green outside sandbox.",
    },
    {
        "task_id": "tsk_93c6d552e4895e58",
        "lifecycle_key": "audit/v0.4/release/git-tag-v040",
        "done_result": "Annotated tag v0.4.0 after release gate.",
        "done_artifacts": "runtime/version.py, debian/changelog",
        "done_references": "audit/v0.4/release/git-tag-v040, v0.4.0",
        "done_expected_impact": "v0.4.0 marks expanded hub MVP release.",
    },
]

# Pass --include-tag only after `git tag -a v0.4.0` on a commit that includes the R1 fix.


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Close v0.4 release gate tasks.")
    parser.add_argument("--include-tag", action="store_true", help="Also close audit/v0.4/release/git-tag-v040")
    args = parser.parse_args()

    closes = CLOSES if args.include_tag else [spec for spec in CLOSES if spec["lifecycle_key"] != "audit/v0.4/release/git-tag-v040"]
    bootstrap = NodeBootstrap(repo_root=str(REPO_ROOT))
    results = []
    session = "capiforge-cli-close-v04-release"
    for spec in closes:
        claim_ready_task(
            bootstrap,
            task_id=spec["task_id"],
            plan=f"Close {spec['lifecycle_key']}",
            lease_minutes=5,
            lock_timeout_seconds=30.0,
            agent_id="capiforge-cli",
            session_id=session,
            recover_stale_lock=True,
        )
        transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="in_progress",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id=session,
            recover_stale_lock=True,
        )
        result = transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="done",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id=session,
            recover_stale_lock=True,
            done_result=spec["done_result"],
            done_artifacts=spec["done_artifacts"],
            done_references=spec["done_references"],
            done_expected_impact=spec["done_expected_impact"],
        )
        results.append({"task_id": spec["task_id"], "lifecycle_key": spec["lifecycle_key"], "state": result["state"]})
    print(json.dumps({"closed": results}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
