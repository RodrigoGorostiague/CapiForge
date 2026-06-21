#!/usr/bin/env python3
"""Close completed v0.3 audit tasks (claim → in_progress → done)."""

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
        "task_id": "tsk_9efbbbcdc55f5c64",
        "lifecycle_key": "audit/v0.3/scope-pivot-audit",
        "done_result": "Published audit v0.3 in docs/ and CapiForge; seeded 18 derived tasks.",
        "done_artifacts": "docs/audits/audit-v03-scope-pivot.md, scripts/seed_audit_v03_tasks.py, aud_520ca02978e35b95",
        "done_references": "audit/v0.3/scope-pivot-audit",
        "done_expected_impact": "Scope pivot audit is live for dogfooding.",
    },
    {
        "task_id": "tsk_84f3015e4e735263",
        "lifecycle_key": "audit/v0.3/vision-docs",
        "done_result": "Rewrote architecture-v01.md, AGENTS.md, mvp.md pointer, and added mvp-v03.md.",
        "done_artifacts": "docs/architecture-v01.md, docs/mvp-v03.md, AGENTS.md",
        "done_references": "audit/v0.3/vision-docs",
        "done_expected_impact": "Product vision reflects documentation-hub pivot.",
    },
    {
        "task_id": "tsk_398b49fdd1d25e27",
        "lifecycle_key": "audit/v0.3/engram-boundary",
        "done_result": "Documented CapiForge vs Engram vs OpenSpec hybrid truth model.",
        "done_artifacts": "docs/architecture-v01.md, skills/capiforge-data-layer/SKILL.md",
        "done_references": "audit/v0.3/engram-boundary",
        "done_expected_impact": "Agents know what not to duplicate in CapiForge.",
    },
    {
        "task_id": "tsk_574147b4948c5b4e",
        "lifecycle_key": "audit/v0.3/skill-publish-milestone",
        "done_result": "Created capiforge-publish-milestone skill with milestone contract.",
        "done_artifacts": "skills/capiforge-publish-milestone/SKILL.md, runtime/installer/integration_config.py",
        "done_references": "audit/v0.3/skill-publish-milestone",
        "done_expected_impact": "Default agent path is milestone-only publication.",
    },
    {
        "task_id": "tsk_da8c11a04859593f",
        "lifecycle_key": "audit/v0.3/skills-realign",
        "done_result": "Updated pickup/start/close skills as optional; extended data-layer.",
        "done_artifacts": "skills/capiforge-pickup-task/SKILL.md, skills/capiforge-start-task/SKILL.md, skills/capiforge-close-task/SKILL.md, skills/capiforge-data-layer/SKILL.md",
        "done_references": "audit/v0.3/skills-realign",
        "done_expected_impact": "Skills no longer imply per-micro-task MCP cycles.",
    },
    {
        "task_id": "tsk_739c906ff126575a",
        "lifecycle_key": "audit/v0.3/agents-decision-tree",
        "done_result": "Updated AGENTS.md with milestone-first decision tree.",
        "done_artifacts": "AGENTS.md",
        "done_references": "audit/v0.3/agents-decision-tree",
        "done_expected_impact": "Orchestrators route agents to publish-milestone by default.",
    },
    {
        "task_id": "tsk_87b1c8ff9ac25c1f",
        "lifecycle_key": "audit/v0.3/schema-project-pages",
        "done_result": "Added project_pages table, schema v2 migration, and store CRUD.",
        "done_artifacts": "storage/node-schema.sql, runtime/node/store/__init__.py, runtime/shared/ids.py",
        "done_references": "audit/v0.3/schema-project-pages",
        "done_expected_impact": "Purpose and architecture are first-class persisted pages.",
    },
    {
        "task_id": "tsk_c35c50eda99a517e",
        "lifecycle_key": "audit/v0.3/ui-project-home",
        "done_result": "Web home shows purpose and architecture sections with edit links.",
        "done_artifacts": "runtime/web/templates/home.html, runtime/web/routes/pages.py",
        "done_references": "audit/v0.3/ui-project-home",
        "done_expected_impact": "Humans see project hub on capiforge web home.",
    },
    {
        "task_id": "tsk_c3ee014e787a5faa",
        "lifecycle_key": "audit/v0.3/ui-doc-editor",
        "done_result": "Added /project-page markdown editor and save API.",
        "done_artifacts": "runtime/web/templates/project_page_edit.html, runtime/web/routes/api.py, runtime/tui/actions.py",
        "done_references": "audit/v0.3/ui-doc-editor",
        "done_expected_impact": "Humans can edit purpose and architecture in the browser.",
    },
    {
        "task_id": "tsk_03920d3df8135ca5",
        "lifecycle_key": "audit/v0.3/seed-project-docs",
        "done_result": "Seeded default purpose and architecture pages for CapiForge.",
        "done_artifacts": "scripts/seed_project_pages.py",
        "done_references": "audit/v0.3/seed-project-docs",
        "done_expected_impact": "Adopted project has starter hub content.",
    },
    {
        "task_id": "tsk_dab4f9d34b865e67",
        "lifecycle_key": "audit/v0.3/mvp-checklist-v03",
        "done_result": "Added docs/mvp-v03.md acceptance checklist.",
        "done_artifacts": "docs/mvp-v03.md",
        "done_references": "audit/v0.3/mvp-checklist-v03",
        "done_expected_impact": "MVP v0.3 has explicit done criteria.",
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
            session_id="capiforge-cli-close-v03",
            recover_stale_lock=True,
        )
        transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="in_progress",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id="capiforge-cli-close-v03",
            recover_stale_lock=True,
        )
        result = transition_task(
            bootstrap,
            task_id=spec["task_id"],
            requested_state="done",
            summary=f"Close {spec['lifecycle_key']}",
            agent_id="capiforge-cli",
            session_id="capiforge-cli-close-v03",
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
