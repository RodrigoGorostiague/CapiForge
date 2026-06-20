# Proposal: Debian `.deb` and Launchpad PPA Packaging

## Intent

Ship CapiForge as an installable Ubuntu/Debian package (`apt install capiforge`) with FHS layout, bundled share data (`storage/`, `skills/`, `assets/`), and a system-aware `capinstall` flow that does not depend on `uv tool install --editable` from a git checkout.

## Scope

### In Scope

- Non-editable Python wheel/deb with share data under `/usr/share/capiforge/`.
- Central path resolution (`runtime/paths.py`) for schemas, assets, and skills.
- `capinstall` install mode for Debian packages (`deb` vs `uv` / `pipx`).
- Debian metadata (`debian/`) and `scripts/build-deb.sh`.
- Public PPA workflow (Launchpad) for `noble` and `jammy`.
- CI build + lintian on tag; README PPA install section.

### Out of Scope

- Debian official archive (`NEW` / `ITP`).
- RPM / Fedora COPR.
- Postinst that auto-modifies `~/.cursor/mcp.json` (integrations stay opt-in via `capinstall`).

## Capabilities

### New Capabilities

- `debian-packaging`: FHS install layout, `.deb` build, PPA publish, and system-package install mode.

### Modified Capabilities

- `real-node-bootstrap`: document system-wide binary + share-root resolution vs per-project `--repo-root`.

## Approach

Use `dh-python` + `pybuild` on `pyproject.toml`, install console scripts to `/usr/bin`, and ship static data to `/usr/share/capiforge`. Resolve runtime paths via `CAPIFORGE_SHARE`, `/usr/share/capiforge`, or dev checkout fallback. Extend installer state with `install_mode` so update/uninstall on deb installs refresh MCP integrations without removing the apt package.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `runtime/paths.py` | New | Share-root and schema/asset resolution |
| `pyproject.toml` | Modified | Dependencies, package-data, `capinstall` entry point |
| `scripts/installer_core.py` | Modified | System package detection and deb install mode |
| `debian/` | New | Debian source package metadata |
| `README.md` | Modified | PPA install instructions |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Hardcoded checkout paths break in site-packages | High | Phase 1 path module + tests before deb build |
| Ubuntu LTS lacks `python3-textual` ≥ 8 | Med | Companion PPA package or documented minimum Ubuntu version |
| Conflict with existing `uv tool install capiforge` | Med | Document mutual exclusion; installer detects deb mode |

## Rollback Plan

Remove PPA listing; users `apt remove capiforge`. Dev checkout install via `./capinstall` remains supported.
