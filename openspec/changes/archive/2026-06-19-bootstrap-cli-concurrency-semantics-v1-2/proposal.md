# Proposal: V1.2 — Concurrency Semantics for Bootstrap CLI

## Intent

Define safe multi-process semantics for bootstrap CLI commands. V1.1 proved sequential subprocess use only; overlapping `init`/`adopt`/`status`/`read` can race and leave operators with unclear wait, timeout, and stale-lock behavior.

## Scope

### In Scope
- Serialize bootstrap execution with one exclusive local lock.
- Make contenders wait with configurable timeout, visible wait status, and explicit timeout errors.
- Detect suspect/stale ownership using PID, owner identity, lock age, and liveness when possible; suggest recovery without auto-recovering.
- Define interactive vs non-interactive stale-lock handling and verbose/error output rules.

### Out of Scope
- Automatic stale-lock recovery, distributed/coordinator locking, or shared-MCP mutation locking.
- Reworking bootstrap state model, adding new bootstrap commands, or changing canonical owner-write boundaries.

## Capabilities

### New Capabilities
- None.

### Modified Capabilities
- `real-node-bootstrap`: Add exclusive lock, contention wait, suspect-owner detection, timeout, and recovery-decision rules around local bootstrap operations.
- `mcp-cli-surface`: Add waiting/status/error semantics, non-interactive failure rules, and verbose escalation for locked bootstrap commands.

## Approach

Wrap mutating bootstrap CLI execution in a repo-local exclusive lock around manifest/SQLite-sensitive operations. Keep `wait` as the default contention policy, fail explicitly on timeout, and treat stale/suspect locks as operator decisions instead of automatic recovery. Local-first tradeoff: simpler and safer than cross-process races; shared-MCP/coordinator flows remain outside this lock contract.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `runtime/node/bootstrap/__init__.py` | Modified | Lock lifecycle, suspect detection, timeout, recovery hints |
| `scripts/capiforge_cli.py` | Modified | Wait UX, verbose/error envelopes, non-interactive behavior |
| `tests/node/bootstrap_cli_test.py` | Modified | Concurrent-process, timeout, stale-lock, and UX assertions |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Lock rules hide real owner health | Med | Surface owner/PID/age/liveness and escalate detail on timeout/error |
| Stale-lock recovery causes unsafe writes | Low | No automatic recovery; require explicit operator action |
| Scope expands into broader runtime locking | Med | Limit contract to bootstrap CLI only |

## Rollback Plan

Revert lock/wait handling to the current sequential-only contract, remove new CLI lock messaging, and keep existing bootstrap state files untouched. No schema migration or irreversible data rewrite is allowed in this slice.

## Dependencies

- Existing `real-node-bootstrap` and `mcp-cli-surface` specs, current bootstrap manifest/SQLite paths, and platform file-lock primitives available from Python stdlib.

## Success Criteria

- [ ] Concurrent bootstrap command attempts never race state mutation; one owner runs while contenders wait or fail deterministically.
- [ ] Timeout, suspect/stale lock, interactive approval, and non-interactive failure behavior are explicit and testable.
