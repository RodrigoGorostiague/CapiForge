# Design: Debian `.deb` and Launchpad PPA Packaging

## FHS layout

| Path | Content |
|------|---------|
| `/usr/bin/capiforge` | `runtime.cli:main` |
| `/usr/bin/capinstall` | `runtime.installer.entry:main` |
| `/usr/lib/python3/dist-packages/runtime/...` | Python package |
| `/usr/share/capiforge/storage/*.sql` | SQLite schemas |
| `/usr/share/capiforge/skills/**` | Agent skills |
| `/usr/share/capiforge/assets/**` | Brand / TUI ASCII assets |
| `/usr/share/doc/capiforge/` | README, copyright, changelog |

User project data stays under `<repo-root>/.capiforge/node`; the system package only provides binaries and shared static files.

## Path resolution (`runtime/paths.py`)

Resolution order:

1. `CAPIFORGE_SHARE` environment override
2. `/usr/share/capiforge` when present
3. Dev fallback: git root or `runtime/` parent chain

API: `share_root()`, `schema_path(name)`, `asset_path(relative)`, `skills_root()`.

## Installer deb mode

- `detect_system_package()`: `/usr/bin/capiforge --version` + share root exists
- `install_binary()`: skip `uv tool install --editable`; record `install_mode: deb`
- `update` / `uninstall`: refresh MCP configs only; do not `apt remove` from capinstall

## Debian build

- `debian/control`: `Architecture: all`, `Depends: python3 (>= 3.11), python3-textual, ${python3:Depends}`
- `debian/rules`: `%: dh $@ --with python3 --buildsystem=pybuild`
- `scripts/build-deb.sh`: wrapper around `debuild -us -uc` with lintian

## PPA publish

1. Signed source upload via `dput ppa:USER/capiforge`
2. Build matrix: `jammy`, `noble`
3. User install: `add-apt-repository` → `apt install capiforge`

## Textual dependency strategy

Prefer shipping `python3-textual` in the same PPA when Ubuntu archive version is insufficient for `textual>=8`.
