# CapiForge Runtime Bootstrap

<p align="center">
  <img src="assets/capiforge-icons/capiforge_logo_original_transparente.png" alt="CapiForge logo" width="220">
</p>

> Product / project name: **CapiForge**

## Brand Assets

- `assets/capiforge-icons/capiforge_logo_original_transparente.png` is the default README/GitHub branding asset for light surfaces.
- `assets/capiforge-icons/capiforge_logo_invertido_transparente.png` is preserved for dark-background Git and project-branding uses.
- `assets/capiforge-icons/capiforge-ascii.txt` is kept in-project for future TUI/app graphics so the terminal presentation can reuse the same brand set later.

## Module Layout

- `storage/` contains the owner-node and coordinator SQLite schemas used to bootstrap local-first state.
- `runtime/paths.py` resolves bundled share data (`/usr/share/capiforge` in apt installs, checkout fallback in dev).
- `runtime/shared/` holds canonical IDs, mutation contracts, and surface error payloads shared by nodes and the coordinator.
- `runtime/node/` contains local node persistence, deterministic entrypoint indexes, owner routing, and node MCP handlers.
- `runtime/coordinator/` contains LAN enrollment, exclusive claim leases, routed mutation visibility, and coordinator MCP handlers.
- `runtime/installer/` contains `capinstall` core logic, integration writers, and the Textual wizard.
- `debian/` and `scripts/build-deb.sh` support local `.deb` builds and Launchpad PPA packaging.
- `skills/` ships agent skills; apt installs copy them to `/usr/share/capiforge/skills/`.
- `tests/e2e/` covers the review-facing multi-node topology: two nodes plus one thin coordinator.

## Bootstrap Defaults

V1 keeps the coordinator thin and non-authoritative. Each project has exactly one owner node for canonical domain writes. Non-owner nodes may read synced metadata, request claims, and submit routed proposals that require explicit owner acceptance.

## Owner-Local Bootstrap CLI (V1.1)

Architecture and product direction (v0.3): [docs/architecture-v01.md](docs/architecture-v01.md)  
**MVP v0.3 checklist (documentation hub):** [docs/mvp-v03.md](docs/mvp-v03.md)  
Coordination MVP v0.2 checklist: [docs/mvp.md](docs/mvp.md)

### Quick start (developer checkout)

From a fresh clone:

```bash
./capinstall install --cursor --opencode --non-interactive
./capinstall verify --json
capiforge web
```

`capiforge web` opens the **project hub**: purpose, architecture, tasks, and audits. Edit pages from the home screen or `/project-page`.

After pulling changes:

```bash
./capinstall update
./capinstall verify --json
```

Agent skills installed to `<repo>/.cursor/skills/` include **`capiforge-publish-milestone`** (default: publish to CapiForge only at milestones, not per micro-task). See [AGENTS.md](AGENTS.md).

### Install the canonical `capiforge` command

Two supported install paths:

| Path | Best for | Commands |
|------|----------|----------|
| **Developer checkout** | day-to-day repo work | `./capinstall` → `uv tool install --editable` |
| **System package (PPA/apt)** | end users / stable binary | `apt install capiforge` → `capinstall` for MCP wiring |

#### Developer install (recommended from repo root)

```bash
./capinstall
```

In an interactive terminal, `./capinstall` opens a **Textual wizard** with:

- **Install** — choose Cursor and/or OpenCode, then install + bootstrap + MCP config
- **Update** — refresh the installed binary and all registered integrations
- **Uninstall** — remove the binary, MCP entries, and installer state
- **Verify** — health check without changes
- **Open CapiForge TUI** — launch `capiforge tui` when the binary is present

CLI/automation mode:

```bash
./capinstall install --cursor --opencode
./capinstall update
./capinstall uninstall
./capinstall verify --json
./capinstall --no-tui-ui verify
```

The installer verifies Python 3.11+, installs into an isolated tool environment (preferring `uv`, with `pipx` as a fallback), bootstraps the repo (`init` → `adopt`), and writes MCP integration config for the targets you select.

**Install modes** recorded in `~/.capiforge/installer-state.json`:

- `uv` / `pipx` — editable checkout install (developer path)
- `deb` — system package detected only when `/usr/share/capiforge` exists; `capinstall uninstall` removes integrations but leaves the apt package installed

Integration paths:

- **Cursor:** `~/.cursor/mcp.json`, `<repo>/.cursor/mcp.json`, and `<repo>/.cursor/skills/` (automation skill copy)
- **OpenCode:** `~/.config/opencode/opencode.json` plus a local skills tree under the config directory

Installer state is stored in `~/.capiforge/installer-state.json` so update/uninstall can refresh or remove everything that was registered.

After pulling new changes:

```bash
./capinstall update
```

If `uv` is missing, bootstrap it explicitly:

```bash
CAPIFORGE_INSTALL_UV=1 ./capinstall install --cursor
```

Manual editable install remains supported:

```bash
python3 -m pip install -e .
capiforge --version
capiforge mcp --help
capiforge tui
capiforge web
```

#### Install from PPA (Ubuntu/Debian)

For system-wide installation via apt:

```bash
sudo add-apt-repository ppa:capiforge/stable
sudo apt update
sudo apt install capiforge
capiforge --version
capinstall
```

The apt package installs `/usr/bin/capiforge`, `/usr/bin/capinstall`, and share data under `/usr/share/capiforge/` (SQL schemas, skills, assets). Your project repository remains the `--repo-root` for bootstrap and MCP; run `capinstall` to wire Cursor/OpenCode integrations for that repo.

Supported PPA baseline: **Ubuntu 24.04 (noble)** with `python3-textual` from Universe. Ubuntu 22.04 (jammy) may require a companion Textual package in the same PPA; see `debian/README.Debian`.

Build a local `.deb` from source:

```bash
sudo apt install devscripts debhelper dh-python pybuild-plugin-pyproject python3-textual
./scripts/build-deb.sh
```

Tag pushes (`v*`) also run the Debian build workflow in `.github/workflows/deb-build.yml`.

Example MCP stdio configuration:

```bash
capiforge mcp serve --repo-root /path/to/repo --node-home /path/to/repo/.capiforge/node
```

### Bootstrap commands

The canonical public operator path is now the installed `capiforge` command. The supported V1.1 flow remains local-only and explicit:

1. Initialize a persistent node home for this repository.
2. Explicitly adopt this repository as the owner-local project.
3. Inspect persisted status.
4. Read deterministic project data for the adopted repository.
5. Read the aggregated current adopted-project summary.
6. Read the ready task queue for the adopted project.
7. Claim a ready task for local execution.

```bash
capiforge init
capiforge adopt
capiforge status
capiforge read --as-of 2026-06-19T13:30:00Z
capiforge current
capiforge tasks ready
capiforge tasks claim --task-id tsk_123 --plan "Implement the requested change"
capiforge audit create --title "Brief title" --content-file docs/audits/audit-v01-agent-coordination.md
capiforge audit publish --audit-id aud_example
capiforge tui
capiforge web
```

#### Web UI

The web UI complements the terminal UI with a Notion-style browser experience for dashboards, task tables, audit markdown, and lifecycle actions.

Install with the optional `[web]` extra:

```bash
./capinstall update
# or manually:
uv tool install --reinstall --editable '.[web]' --directory /path/to/CapiForge
# or use the repo venv without touching ~/.local/bin/capiforge:
uv sync --extra web
uv run capiforge web --refresh 15
```

`uv sync --extra web` only updates the checkout `.venv`. The global `capiforge` in `~/.local/bin` needs `capinstall update` or `uv tool install --reinstall`.

Start the local server (opens your browser by default):

```bash
capiforge web
capiforge web --port 8741 --no-open --refresh 30
```

The server binds to `127.0.0.1` by default. Use `--host 0.0.0.0` only when you intentionally want LAN access.

### When the ready queue is empty

`capiforge tasks ready` may return **count: 0** when every task is claimed, in progress, or already done. That is normal — not a bootstrap failure.

1. Inspect state: `capiforge current` (check `queue_counts` for `blocked`, `done`, `expired_claim`).
2. If work is in flight, finish or release claims before expecting new ready items.
3. To add new work from an audit:
   - `capiforge audit create --title "..." --content-file path/to/audit.md`
   - `capiforge audit publish --audit-id aud_...`
   - Seed ready tasks (project script) or start lifecycle work: `capiforge tasks start --lifecycle-key audit/v0.2/example --plan "..."`
4. See [docs/mvp.md](docs/mvp.md) for the full agent recovery playbook.

Lifecycle wrappers (same-project, audit-backed auto-create on miss):

```bash
capiforge tasks start --lifecycle-key lifecycle://example/work --plan "Start work"
capiforge tasks finish --lifecycle-key lifecycle://example/work --outcome done --done-result "Shipped"
```

The legacy bootstrap helper remains available as a compatibility shim:

```bash
python3 scripts/capiforge_cli.py init
```

Every command prints one JSON envelope with `{status,data,error}`.

Supported process-level guarantee: sequential subprocess execution (`init` → `adopt` → `status`/`read`) is supported. Overlapping concurrent `adopt`/`read` invocations against the same `.capiforge/node` state are out of scope for V1.1.

Example `status` response:

```json
{"status":"ok","data":{"bootstrap_state":"adopted","local_node_id":"node:...","node_home":"/repo/.capiforge/node","node_db_path":"/repo/.capiforge/node/node.sqlite3","adopted_project":{"repo_root":"/repo","workspace_id":"workspace:...","project_id":"project:..."}},"error":null}
```

Example `read` response:

```json
{"status":"ok","data":{"bootstrap_state":"adopted","project":{"repo_root":"/repo","project_id":"project:..."},"entrypoint":{"project_id":"project:...","generated_at":"2026-06-19T13:30:00Z"}},"error":null}
```

Example `current` response:

```json
{"status":"ok","data":{"bootstrap_state":"adopted","adopted_project":{"repo_root":"/repo","project_id":"project:..."},"as_of":"2026-06-19T13:30:00Z","entrypoint":{"project_id":"project:...","generated_at":"2026-06-19T13:30:00Z"},"sync_status":{"project_id":"project:...","degraded":true,"canonical_write_path":"owner_node_local"},"ready_tasks":{"project_id":"project:...","index_name":"ready","limit":10,"tasks":[]}},"error":null}
```

Example `tasks ready` response:

```json
{"status":"ok","data":{"bootstrap_state":"adopted","adopted_project":{"repo_root":"/repo","project_id":"project:..."},"index_name":"ready","as_of":"2026-06-19T13:30:00Z","count":0,"limit":20,"tasks":[]},"error":null}
```

Example `tasks claim` response:

```json
{"status":"claimed","data":{"bootstrap_state":"adopted","adopted_project":{"repo_root":"/repo","project_id":"project:..."},"claim_id":"clm_...","task_id":"tsk_123","lease_started_at":"2026-06-19T13:30:00Z","lease_expires_at":"2026-06-19T13:35:00Z","state":"claimed","plan":"Implement the requested change"},"error":null}
```

The owner-local node home layout is:

- `.capiforge/node/bootstrap.json` — persisted bootstrap state (`uninitialized`, `initialized`, `adopted`)
- `.capiforge/node/node.sqlite3` — local node SQLite store for the adopted repository

### Explicit Non-Goals for This Flow

- No coordinator enrollment is required for the owner-local CLI.
- No implicit repository adoption happens during `init`.
- No LAN workflows, claims orchestration, cross-node routing automation, or multi-project bootstrap are included in this V1.1 path.

Shared read/sync surfaces are intended for trusted enrolled nodes only. Runtime calls now require a session-bound `node_proof` derived from the invitation fingerprint plus `node_id`, `agent_id`, and `session_id`, instead of treating a reusable shared string or raw `node_id` as sufficient authority.

For local MCP stdio usage after installation:

```bash
capiforge mcp --help
capiforge mcp serve --repo-root /path/to/repo --node-home /path/to/repo/.capiforge/node
```

The stdio MCP surface also exposes:

- `current_get`, `tasks_ready_get`, `tasks_list_by_index`, `project_entrypoint_get`, `workspace_get_current`, `sync_status`
- `tasks_claim`, `tasks_claim_renew`, `tasks_release`, `tasks_transition`
- `tasks_reconcile_start`, `tasks_reconcile_finish`
- `audit_create_brief`, `audit_publish`

`current_get` returns the same aggregate payload shape as `capiforge current`. `tasks_ready_get` matches `capiforge tasks ready`. `tasks_claim` matches `capiforge tasks claim`.

Project-scoped authorization is now enforced before local entrypoint reads, indexed task reads, claims, and routed mutation proposal creation. Enrollment alone is not enough to inspect or act on arbitrary project IDs.

Coordinator-backed project reads remain minimal in V1: the owner node, a node with coordinator claim history for that project, or a node already participating in a routed mutation for that destination project may read shared sync metadata. Node-local mirrored reads add one more narrow allowance: a trusted node may traverse a foreign project only when it owns a project that is already explicitly linked to that foreign project in local metadata. Claiming a task does not create that access retroactively.

Claimed execution remains valid only while the coordinator lease is active. Releasing or expiring a lease returns the task to a non-active state until a new valid claim exists.

Suggested lease defaults for bootstrap environments:

- Lease duration: 5 minutes
- Renewal cadence: every 2 minutes
- Clock-skew grace window: 30 seconds

These defaults come from the current V1 design and are intended to keep claim recovery predictable without making the coordinator authoritative.

## Local-Only Document Boundary

Long-form documents stay local-only in node storage. V1 sync shares structured metadata, artifact references, owner-node routing metadata, claim visibility, and canonical summaries only. If a human wants to share long-form content, that export must happen through a separate explicit mechanism outside the coordinator's default sync path.

Approved cross-project routes remain non-authoritative until the destination owner node applies them locally. Acceptance records the route decision; canonical task materialization still happens on the owner node. Sync announcements are accepted only from the enrolled reporting node itself and only for projects that node is already authorized to coordinate on.

Cross-project routing now requires coordinator-held notice/approval state for the exact source/destination pair and current destination owner. Local requester cache is not sufficient on its own, and a revoked approval blocks later owner acceptance.

Direct audit content edits are owner-local human-control actions only. AI actors and non-owner nodes must use follow-up/addendum flows instead, and closed audits still reject direct rewrites.

## Test Runner

The repository includes a stdlib `unittest` entrypoint shim at the repo root, so a naive default invocation discovers the full suite instead of silently running zero tests.

```bash
python3 -m unittest
```

Default retention keeps synced metadata and artifact references available until a human removes them or newer evidence supersedes them. Automatic expiry applies only to claim leases.
