#!/usr/bin/env python3
"""Close completed v0.4 audit tasks (phases 0–3 and release docs)."""

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
        "task_id": "tsk_6fba2de8d9435026",
        "lifecycle_key": "audit/v0.4/scope-audit",
        "done_result": "Published audit-v04-expanded-hub.md and milestone aud_69b754a21df852b3.",
        "done_artifacts": "docs/audits/audit-v04-expanded-hub.md, scripts/seed_audit_v04_tasks.py",
        "done_references": "audit/v0.4/scope-audit",
        "done_expected_impact": "v0.4 roadmap is live in repo and CapiForge.",
    },
    {
        "task_id": "tsk_ac45c49ae0e95293",
        "lifecycle_key": "audit/v0.4/architecture-update",
        "done_result": "Updated architecture-v01, AGENTS.md, mvp-v04.md with 17 MCP tools and multi-project table.",
        "done_artifacts": "docs/architecture-v01.md, docs/mvp-v04.md, AGENTS.md",
        "done_references": "audit/v0.4/architecture-update",
        "done_expected_impact": "Docs reflect v0.4 expanded hub direction.",
    },
    {
        "task_id": "tsk_1c01b08ceb5856a7",
        "lifecycle_key": "audit/v0.4/supersede-future-tasks",
        "done_result": "Cancelled audit/future/* with superseded_by v0.4 RFC keys.",
        "done_artifacts": "scripts/supersede_audit_future_tasks.py",
        "done_references": "audit/v0.4/supersede-future-tasks",
        "done_expected_impact": "Ready queue has no stale future design tasks.",
    },
    {
        "task_id": "tsk_dcabf51f9286512e",
        "lifecycle_key": "audit/v0.4/multi-project-switcher",
        "done_result": "Added project switcher in page header preserving home/tasks/docs route.",
        "done_artifacts": "runtime/web/context.py, runtime/web/templates/macros/page_header.html",
        "done_references": "audit/v0.4/multi-project-switcher",
        "done_expected_impact": "Operators switch adopted projects without losing context.",
    },
    {
        "task_id": "tsk_7304754c30ff5af1",
        "lifecycle_key": "audit/v0.4/multi-project-registry-hardening",
        "done_result": "Hardened project-repos.json validation, remove_registry_entry, tests.",
        "done_artifacts": "runtime/web/project_registry.py, tests/web/project_registry_test.py",
        "done_references": "audit/v0.4/multi-project-registry-hardening",
        "done_expected_impact": "External project registry is stable and test-covered.",
    },
    {
        "task_id": "tsk_9a157bc2e36e565e",
        "lifecycle_key": "audit/v0.4/multi-project-entrypoint",
        "done_result": "Active repo path in page subtitle; MCP vs web scope documented.",
        "done_artifacts": "runtime/web/routes/pages.py, docs/architecture-v01.md",
        "done_references": "audit/v0.4/multi-project-entrypoint",
        "done_expected_impact": "Humans see which repo is active; agents know current_get scope.",
    },
    {
        "task_id": "tsk_54023a34e4ff5e5d",
        "lifecycle_key": "audit/v0.4/onboarding-hub-page",
        "done_result": "Added Primeros pasos onboarding section on web home.",
        "done_artifacts": "runtime/web/templates/home.html, runtime/web/static/notion.css",
        "done_references": "audit/v0.4/onboarding-hub-page",
        "done_expected_impact": "New developers start from hub without reading full README.",
    },
    {
        "task_id": "tsk_8483793edea15577",
        "lifecycle_key": "audit/v0.4/docs-indexer",
        "done_result": "Added scripts/index_local_docs.py and store upsert_local_document.",
        "done_artifacts": "scripts/index_local_docs.py, runtime/node/store/__init__.py, tests/scripts/index_local_docs_test.py",
        "done_references": "audit/v0.4/docs-indexer",
        "done_expected_impact": "docs/**/*.md indexable into Documentación viewer.",
    },
    {
        "task_id": "tsk_8da18c62fb625595",
        "lifecycle_key": "audit/v0.4/demo-v04",
        "done_result": "Added 5-minute demo script for multi-project hub and docs indexer.",
        "done_artifacts": "docs/demo-v04.md",
        "done_references": "audit/v0.4/demo-v04",
        "done_expected_impact": "Operators can demo v0.4 consistently.",
    },
    {
        "task_id": "tsk_1234e735ed685b19",
        "lifecycle_key": "audit/v0.4/rfc-sync-coordinator",
        "done_result": "Published RFC for v0.5 LAN sync activation with derived task list.",
        "done_artifacts": "docs/rfcs/rfc-sync-coordinator-v05.md",
        "done_references": "audit/v0.4/rfc-sync-coordinator",
        "done_expected_impact": "Sync work is scoped for v0.5 without unfreezing coordinator now.",
    },
    {
        "task_id": "tsk_ce363236ad92576b",
        "lifecycle_key": "audit/v0.4/rfc-multi-user-workspaces",
        "done_result": "Published RFC for v0.6 multi-user workspaces with derived task list.",
        "done_artifacts": "docs/rfcs/rfc-multi-user-v06.md",
        "done_references": "audit/v0.4/rfc-multi-user-workspaces",
        "done_expected_impact": "Multi-user design deferred with explicit v0.6 plan.",
    },
    {
        "task_id": "tsk_fd78e97e6e495732",
        "lifecycle_key": "audit/v0.4/rfc-admin-dashboards",
        "done_result": "Published RFC for v1.0 admin BI dashboards with derived task list.",
        "done_artifacts": "docs/rfcs/rfc-admin-bi-v10.md",
        "done_references": "audit/v0.4/rfc-admin-dashboards",
        "done_expected_impact": "BI scope documented without implementing dashboards in v0.4.",
    },
    {
        "task_id": "tsk_b695372a413b5acd",
        "lifecycle_key": "audit/v0.4/release/version-bump",
        "done_result": "Version 0.4.0 in runtime.version and debian/changelog.",
        "done_artifacts": "runtime/version.py, debian/changelog, pyproject.toml dynamic version",
        "done_references": "audit/v0.4/release/version-bump",
        "done_expected_impact": "Package reports v0.4.0.",
    },
]


def main() -> int:
    bootstrap = NodeBootstrap(repo_root=str(REPO_ROOT))
    results = []
    for spec in CLOSES:
        claim_ready_task(
            bootstrap,
            task_id=spec["task_id"],
            plan=f"Close {spec['lifecycle_key']}",
            lease_minutes=5,
            lock_timeout_seconds=30.0,
            agent_id="capiforge-cli",
            session_id="capiforge-cli-close-v04",
            recover_stale_lock=True,
        )
        transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="in_progress",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id="capiforge-cli-close-v04",
            recover_stale_lock=True,
        )
        result = transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="done",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id="capiforge-cli-close-v04",
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
