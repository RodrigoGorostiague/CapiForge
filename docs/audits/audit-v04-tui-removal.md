# Audit: CapiForge v0.4 — Product TUI removal

**Date:** 2026-06-21  
**Related:** [audit-v04-expanded-hub.md](audit-v04-expanded-hub.md)  
**Scope:** remove `capiforge tui`; web hub as sole human surface  
**Goal:** reduce maintenance and align product with operator workflow (web-first)

## Summary

The Textual terminal UI (`capiforge tui`, `runtime/tui/`) was removed. Shared snapshot/action/nav logic moved to `runtime/hub/`. The web UI (`capiforge web`) is now the **only** product human surface. Textual remains only for the `capinstall` wizard.

## Scope

### Removed

- `runtime/tui/` (shell, widgets, Rich themes, command palette)
- CLI subcommand `capiforge tui`
- `tests/tui/home_test.py`
- Installer menu **Open CapiForge TUI** and install-step “TUI extra”

### Added / moved

| Path | Role |
| --- | --- |
| `runtime/hub/data.py` | Snapshots, nav state, loaders |
| `runtime/hub/actions.py` | Task/project mutations (web + adopt) |
| `runtime/hub/nav.py` | Sidebar nav tree |
| `runtime/hub/pages.py` | Page headers, audit selection helpers |
| `runtime/hub/tasks.py` | Task sort/filter constants |
| `runtime/hub/sync.py` | Sync indicator state |
| `runtime/shared/splash.py` | ASCII splash (installer only) |

### Updated

- All `runtime/web/*` imports → `runtime/hub.*`
- `capinstall` launches **Open CapiForge Web** → `capiforge web`
- `README.md`, `debian/control`, `docs/architecture-v01.md`

## Evidence

- Web + hub tests: `python3 -m unittest tests.web.web_test tests.cli.test_cli tests.shared.splash_test tests.web.project_registry_test`
- CLI: `capiforge tui` no longer in parser; `capiforge web` unchanged
- Architecture note: shared logic in `runtime/hub/`; no product TUI

## Follow-ups

- Optional: remove dead `install_tui_extra` from installer state (backward compatible read)
- v0.4 release gate tasks remain open (`audit/v0.4/release/*`)

## Lifecycle

| lifecycle_key | Outcome |
| --- | --- |
| `audit/v0.4/remove-product-tui` | Product TUI removed; hub package extracted |
