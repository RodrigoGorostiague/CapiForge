# Tasks: Debian `.deb` and Launchpad PPA Packaging

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 800-1200 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 → PR 2 → PR 3 |
| Delivery strategy | phased by dependency order |
| Chain strategy | paths → installer → debian/ppa |

Decision needed before apply: No
Chained PRs recommended: Yes
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Depends on |
|------|------|-----------|------------|
| 1 | Share paths + package data + path migration | PR 1 | — |
| 2 | capinstall deb mode + tests | PR 2 | PR 1 |
| 3 | debian/ + build script + PPA CI/docs | PR 3 | PR 1-2 |

## Phase 1: Installable Python package

- [x] 1.1 Add `runtime/paths.py` with `share_root()`, `schema_path()`, `asset_path()`, `skills_root()` and dev/system resolution order.
- [x] 1.2 Update `pyproject.toml`: move `textual` to main dependencies; package `storage/`, `skills/`, `assets/` into `/usr/share/capiforge`; add `capinstall` console script entry point.
- [x] 1.3 Replace hardcoded `parents[N]` paths in `runtime/node/store`, `runtime/node/mcp_stdio`, `runtime/tui/shell`, `runtime/tui/splash`, `runtime/installer/tui`.
- [x] 1.4 Add unit tests for path resolution (`CAPIFORGE_SHARE`, dev fallback) and keep existing suite green.

## Phase 2: capinstall system package mode

- [x] 2.1 Extend `runtime/installer/state.py` with `install_mode` (`deb` | `uv` | `pipx`).
- [x] 2.2 Implement `detect_system_package()` and deb branch in `scripts/installer_core.py` (`install_binary`, `update`, `uninstall`).
- [x] 2.3 Add `runtime/installer/entry.py` for `/usr/bin/capinstall`; wire TUI default repo-root to user project, not share root.
- [x] 2.4 Extend `tests/install/setup_test.py` for deb install mode.

## Phase 3: Debian metadata and build

- [x] 3.1 Add `debian/` tree (`control`, `rules`, `changelog`, `copyright`, `compat`, `source/format`, docs).
- [x] 3.2 Add `scripts/build-deb.sh` and validate `debuild -us -uc` on Ubuntu noble.
- [x] 3.3 Resolve `python3-textual` for jammy/noble (companion PPA package or documented minimum Ubuntu version).

## Phase 4: PPA publish and verification

- [x] 4.1 Document PPA install in `README.md` (`add-apt-repository`, `apt install capiforge`, `capinstall`).
- [x] 4.2 Add CI job on tag: build deb in `ubuntu:noble`, run lintian (warn-only initially).
- [x] 4.3 Add integration test: `dpkg -i` → `capiforge init/adopt` in tmpdir → `capinstall verify --json`.
- [x] 4.4 Publish staging PPA upload checklist (`dput`, GPG, Launchpad settings).

## Required vs optional

| ID | Task | Required for proposal |
|----|------|---------------------|
| 1.1–1.4 | Package paths + data | **Yes** — blocks all deb work |
| 2.1–2.4 | capinstall deb mode | **Yes** — PPA UX |
| 3.1–3.2 | debian/ + build script | **Yes** — produces `.deb` |
| 3.3 | Textual PPA dependency | **Yes** — runtime TUI on LTS |
| 4.1–4.2 | README + CI | **Yes** — public PPA |
| 4.3–4.4 | Integration test + publish checklist | Recommended before stable PPA |
