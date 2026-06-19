# Tasks: V1.2 — Concurrency Semantics for Bootstrap CLI

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 450-650 |
| 400-line budget risk | High |
| Chained PRs recommended | Yes |
| Suggested split | PR 1 lock core → PR 2 CLI surface → PR 3 contention tests |
| Delivery strategy | ask-always |
| Chain strategy | feature-branch-chain |

Decision needed before apply: No
Chained PRs recommended: Yes
Chain strategy: feature-branch-chain
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Notes |
|------|------|-----------|-------|
| 1 | Add lock model, acquisition loop, timeout, suspect classification | PR 1 | `runtime/node/bootstrap/__init__.py`; verify wait/timeout paths |
| 2 | Wire CLI flags, stderr wait/prompt UX, and explicit lock errors | PR 2 | `scripts/capiforge_cli.py`; depends on PR 1 |
| 3 | Add subprocess contention, suspect-lock, and recovery tests | PR 3 | `tests/node/bootstrap_cli_test.py`; depends on PR 2 |

## Phase 1: Foundation / Lock Core

- [x] 1.1 Add lock metadata dataclasses, `.capiforge/node/bootstrap.lock`, and file-lock helpers in `runtime/node/bootstrap/__init__.py`.
- [x] 1.2 Add `bootstrap_session(command, timeout, interactive, verbose, recover_stale_lock)` to classify `acquired`, `timeout`, and `suspect` outcomes before state access.
- [x] 1.3 Wrap `status()`, `open_or_init()`, `adopt_repo()`, and `require_adopted()` in the shared session path so manifest/SQLite reads and writes serialize.

## Phase 2: Recovery Rules / CLI Wiring

- [x] 2.1 Add `--lock-timeout-seconds`, `--non-interactive`, `--verbose`, and `--recover-stale-lock` to `scripts/capiforge_cli.py` for `init|adopt|status|read`.
- [x] 2.2 Send wait updates and stale-lock confirmation prompts to stderr while keeping stdout limited to the final JSON envelope in `scripts/capiforge_cli.py`.
- [x] 2.3 Map suspect and timeout outcomes to `BOOTSTRAP_LOCK_SUSPECT` and `BOOTSTRAP_LOCK_TIMEOUT`, including owner, PID, age, liveness, and recovery hints.
- [x] 2.4 Enforce the resolved UX: interactive stale-lock recovery requires confirmation, non-interactive mode never prompts, unattended recovery only works with `--recover-stale-lock`.

## Phase 3: Verification

- [x] 3.1 Extend `tests/node/bootstrap_cli_test.py` to cover “wait and continue after the active owner finishes” for concurrent bootstrap commands.
- [x] 3.2 Extend `tests/node/bootstrap_cli_test.py` to cover “fail after contention timeout” with no state mutation and explicit timeout error details.
- [x] 3.3 Extend `tests/node/bootstrap_cli_test.py` to cover “stop on suspect ownership”, interactive confirmation, and non-interactive failure without auto-recovery.
- [x] 3.4 Verify subprocess CLI flows keep stdout machine-readable and surface wait/recovery messaging only on stderr.

## Phase 4: Cleanup / Reviewability

- [x] 4.1 Tighten helper names and inline comments in `runtime/node/bootstrap/__init__.py` and `scripts/capiforge_cli.py` so the lock boundary is easy to review.
- [x] 4.2 Re-run `python3 -m unittest tests.node.bootstrap_cli_test` and record any fixture cleanup needed for lock-file isolation.
