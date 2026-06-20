# Apply Progress: Debian `.deb` and Launchpad PPA Packaging

## Status

Phase 1–4 implementation complete in tree; CapiForge lifecycle tasks closed. Ready for local `debuild` and PPA staging upload.

## Completed

- [x] Proposal, design, exploration, tasks, and spec delta authored under `openspec/changes/deb-ppa-packaging/`.
- [x] Published audit `aud_deb_ppa_packaging_20260620` and lifecycle tasks closed in SQLite.
- [x] `runtime/paths.py` plus share data packaging in `pyproject.toml`.
- [x] Path migration across store, MCP stdio, TUI, and installer.
- [x] `capinstall` deb mode, `runtime/installer/entry.py`, and installer tests.
- [x] `debian/` metadata, `scripts/build-deb.sh`, README PPA docs, and CI workflow.
- [x] Fixed deb detection to require `/usr/share/capiforge` (no dev-checkout false positives).
- [x] Deb integration test and PPA staging checklist (`tests/packaging/deb_integration_test.py`, `docs/packaging/ppa-staging-checklist.md`).

## Next

- [ ] Upload signed source to Launchpad PPA staging and validate `apt install` on noble.
