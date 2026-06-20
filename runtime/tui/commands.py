from __future__ import annotations

from collections.abc import Iterable

from textual.app import SystemCommand
from textual.screen import Screen

TASK_FILTER_COMMANDS = (
    ("all", "Filter: All tasks", "Show every task"),
    ("active", "Filter: Active tasks", "Ready, claimed, and in progress"),
    ("blocked", "Filter: Blocked tasks", "Blocked tasks only"),
    ("done", "Filter: Done tasks", "Completed tasks only"),
)


def iter_shell_commands(app, screen: Screen) -> Iterable[SystemCommand]:
    if getattr(screen, "id", None) == "startup-splash":
        return

    yield SystemCommand("Refresh", "Reload CapiForge state", app.action_refresh)
    yield SystemCommand("Toggle Auto Refresh", "Cycle auto-refresh interval", app.action_toggle_auto_refresh)
    yield SystemCommand("New Workspace", "Create an empty workspace", app.action_new_workspace)
    yield SystemCommand("Cycle Theme", "Switch neon, notion, or light theme", app.action_cycle_theme)

    if not app._nav.project_id:
        if app._nav.workspace_id or (app._current_snapshot and app._current_snapshot.workspaces):
            yield SystemCommand("New Project", "Add a project to the workspace", app.action_new_project)
        return

    yield SystemCommand("Home", "Open project home", app.action_open_home)
    yield SystemCommand("Tasks", "Open project tasks", app.action_open_tasks)
    yield SystemCommand("Docs", "Open project documentation", app.action_open_docs)
    yield SystemCommand("New Task", "Create a task from a published audit", app.action_new_task)

    if app._nav.view == "project_tasks":
        for filter_name, title, help_text in TASK_FILTER_COMMANDS:
            yield SystemCommand(
                title,
                help_text,
                lambda filter_name=filter_name: app.action_set_task_filter(filter_name),
            )
        yield SystemCommand("Claim Task", "Claim the selected task", app.action_claim_selected)
        yield SystemCommand("Start Task", "Move selected task to in progress", app.action_start_selected)
        yield SystemCommand("Block Task", "Block the selected task", app.action_block_selected)
        yield SystemCommand("Done Task", "Mark selected task as done", app.action_done_selected)
        yield SystemCommand("Release Task", "Release claim on selected task", app.action_release_selected)
