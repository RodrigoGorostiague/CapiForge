# Design: V1.2 — Concurrency Semantics for Bootstrap CLI

## Technical Approach

Add a repo-local bootstrap lock inside `NodeBootstrap` so `init`, `adopt`, `status`, and `read` all enter one serialized execution path before touching `bootstrap.json` or `node.sqlite3`. The lock uses stdlib file locking plus a small metadata payload for owner identity, PID, timestamps, and last-known command, then maps outcomes to the CLI contract in the `real-node-bootstrap` and `mcp-cli-surface` delta specs.

## Architecture Decisions

| Decision | Options / tradeoff | Choice + rationale |
|---|---|---|
| Lock scope | Per-command locks would still race manifest/SQLite reads; broader runtime locking would exceed proposal scope | Use one repo-local lock at `.capiforge/node/bootstrap.lock` for all bootstrap CLI commands. It matches the spec boundary and keeps shared-MCP/coordinator flows out of scope. |
| Ownership model | File lock alone prevents overlap but cannot explain stale/suspect cases; lock file without OS lock is unsafe | Use OS-backed exclusive file lock plus JSON metadata in the same file. The OS lock gives exclusivity; metadata supports timeout, diagnostics, and recovery hints. |
| Stale handling | Auto-clear is convenient but unsafe around partial writes; immediate hard-fail hurts recoverability | Never auto-recover. If PID/liveness, owner identity, or age cannot confirm a healthy owner, raise a suspect-lock error with recovery guidance. Interactive mode may confirm a manual clear step; non-interactive mode always fails. |
| CLI progress surface | Writing wait events to stdout would break the current JSON envelope tests; hiding waits hurts operators | Keep stdout for the final JSON envelope and send wait/recovery prompts to stderr. Add structured error details so machine callers still receive deterministic data. |

## Data Flow

`capiforge_cli.py` parses command/flags → builds `NodeBootstrap` → enters `bootstrap_session(command, timeout, interactive, verbose)` → acquires lock or emits wait status → validates owner health metadata → runs existing state transition (`status`, `open_or_init`, `adopt_repo`, `require_adopted`) → releases lock → prints one final JSON envelope.

    CLI command
        │
        ├─ stderr: waiting / prompt / hint
        ▼
    NodeBootstrap session ──→ bootstrap.lock metadata + OS lock
        │                                │
        └──────────────→ bootstrap.json / node.sqlite3

Trust boundary: recovery applies only to the local repo's `.capiforge/node` lock file. No distributed ownership claim is inferred from this lock.

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `runtime/node/bootstrap/__init__.py` | Modify | Add lock acquisition/release, owner metadata model, suspect-owner detection, timeout handling, and manual recovery boundary around all bootstrap entry methods. |
| `scripts/capiforge_cli.py` | Modify | Add lock-related flags, stderr wait/progress output, interactive vs non-interactive recovery behavior, and explicit timeout/suspect error mapping in the JSON envelope. |
| `tests/node/bootstrap_cli_test.py` | Modify | Add real-process contention, timeout, suspect-lock, stderr visibility, and non-interactive failure coverage while preserving current deterministic stdout envelope assertions. |

## Interfaces / Contracts

```python
@dataclass(frozen=True)
class BootstrapLockInfo:
    owner_node_id: str
    pid: int | None
    command: str
    acquired_at: str
    last_seen_at: str

@dataclass(frozen=True)
class BootstrapLockOutcome:
    status: Literal["acquired", "timeout", "suspect"]
    info: BootstrapLockInfo | None
```

CLI additions in `scripts/capiforge_cli.py`:
- `--lock-timeout-seconds` (defaulted in CLI, used by all bootstrap commands)
- `--non-interactive` (disable recovery prompts)
- `--verbose` (include PID/liveness/age/recovery hints in stderr and error details)

Error contracts remain `SurfaceError` envelopes, with new codes for `BOOTSTRAP_LOCK_TIMEOUT` and `BOOTSTRAP_LOCK_SUSPECT`. `error.details` carries `owner_node_id`, `pid`, `lock_age_seconds`, `liveness`, and `recovery_hint` when known.

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | Lock outcome classification and metadata validation | Add focused `NodeBootstrap` tests with temporary lock files and synthetic metadata states. |
| Integration | Real-process wait, timeout, release, and suspect-owner failure | Extend `bootstrap_cli_test.py` subprocess coverage to hold the lock in one process and assert the second process waits or fails deterministically. |
| E2E | CLI envelope + stderr behavior across bootstrap lifecycle | Reuse subprocess CLI flow tests to confirm stdout stays machine-readable while stderr shows wait/recovery messages. |

## Migration / Rollout

No migration required. The lock file is ephemeral local state; bootstrap manifest and SQLite schema remain unchanged.

## Open Questions

- [ ] Manual recovery can be interactive, but the exact confirmation UX (`prompt` text vs dedicated `--recover-stale-lock`) is not yet specified.
