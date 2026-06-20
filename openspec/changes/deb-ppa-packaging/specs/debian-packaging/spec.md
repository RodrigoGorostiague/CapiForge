# Debian Packaging

## Purpose

Define how CapiForge is installed as a system package on Debian/Ubuntu with FHS-compliant paths and an apt/PPA distribution path.

## Requirements

### Requirement: FHS system install layout

The system MUST install `capiforge` and `capinstall` executables under `/usr/bin`, Python modules under the active Python site-packages path, and static share data under `/usr/share/capiforge/`.

#### Scenario: apt install on Ubuntu noble

- WHEN a user runs `apt install capiforge` from the project PPA
- THEN `capiforge --version` succeeds
- AND SQL schemas are readable from `/usr/share/capiforge/storage/` without a git checkout

### Requirement: Share-root path resolution

Runtime code MUST resolve bundled schemas, skills, and assets through a single share-root helper that supports `CAPIFORGE_SHARE`, `/usr/share/capiforge`, and developer checkout fallback.

#### Scenario: Schema load from deb install

- WHEN the node store opens without an explicit schema path
- THEN it loads `node-schema.sql` from the resolved share root

### Requirement: capinstall deb mode

When a system package is detected, capinstall MUST NOT run `uv tool install --editable`. It MUST record `install_mode: deb` and limit uninstall to MCP integration cleanup.

#### Scenario: capinstall after apt install

- WHEN capinstall install runs on a host with the deb package
- THEN it configures Cursor/OpenCode MCP entries using `/usr/bin/capiforge`
- AND it does not mutate the apt package itself

### Requirement: PPA build reproducibility

The repository MUST include Debian metadata sufficient to build a source package with `debuild` and publish to Launchpad.

#### Scenario: Maintainer build

- WHEN a maintainer runs the documented build script on a clean noble container
- THEN a `.deb` artifact is produced and passes basic lintian review
