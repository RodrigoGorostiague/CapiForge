# Apply Progress: Bootstrap CLI Concurrency Semantics V1.2

## Mode

Standard

## Completed Tasks

- [x] 1.1 Add lock metadata dataclasses, `.capiforge/node/bootstrap.lock`, and file-lock helpers in `runtime/node/bootstrap/__init__.py`.
- [x] 1.2 Add `bootstrap_session(command, timeout, interactive, verbose, recover_stale_lock)` to classify `acquired`, `timeout`, and `suspect` outcomes before state access.
- [x] 1.3 Wrap `status()`, `open_or_init()`, `adopt_repo()`, and `require_adopted()` in the shared session path so manifest/SQLite reads and writes serialize.
- [x] 2.1 Add `--lock-timeout-seconds`, `--non-interactive`, `--verbose`, and `--recover-stale-lock` to `scripts/capiforge_cli.py` for `init|adopt|status|read`.
- [x] 2.2 Send wait updates and stale-lock confirmation prompts to stderr while keeping stdout limited to the final JSON envelope in `scripts/capiforge_cli.py`.
- [x] 2.3 Map suspect and timeout outcomes to `BOOTSTRAP_LOCK_SUSPECT` and `BOOTSTRAP_LOCK_TIMEOUT`, including owner, PID, age, liveness, and recovery hints.
- [x] 2.4 Enforce the resolved UX: interactive stale-lock recovery requires confirmation, non-interactive mode never prompts, unattended recovery only works with `--recover-stale-lock`.
- [x] 3.1 Extend `tests/node/bootstrap_cli_test.py` to cover “wait and continue after the active owner finishes” for concurrent bootstrap commands.
- [x] 3.2 Extend `tests/node/bootstrap_cli_test.py` to cover “fail after contention timeout” with no state mutation and explicit timeout error details.
- [x] 3.3 Extend `tests/node/bootstrap_cli_test.py` to cover “stop on suspect ownership”, interactive confirmation, and non-interactive failure without auto-recovery.
- [x] 3.4 Verify subprocess CLI flows keep stdout machine-readable and surface wait/recovery messaging only on stderr.
- [x] 4.1 Tighten helper names and inline comments in `runtime/node/bootstrap/__init__.py` and `scripts/capiforge_cli.py` so the lock boundary is easy to review.
- [x] 4.2 Re-run `python3 -m unittest tests.node.bootstrap_cli_test` and record any fixture cleanup needed for lock-file isolation.

## Verification

- Ran `python3 -m unittest tests.node.bootstrap_cli_test`
- Result: pass (22 tests)
- Re-ran `python3 -m unittest tests.node.bootstrap_cli_test -v` after verify warning remediation
- Result: pass (24 tests)

## Post-Verify Remediation

- Added an explicit active-owner suspect-age policy in `runtime/node/bootstrap/__init__.py` so lock age can independently force `BOOTSTRAP_LOCK_SUSPECT` even while another process still holds the OS lock.
- Kept the existing safety boundary intact: the system still never auto-recovers, and operators must use interactive confirmation or `--recover-stale-lock`.
- Added runtime and CLI coverage for an old-but-still-locked owner so the age-based suspect path is now deterministic and verified.

## Workload / PR Boundary

- Mode: chained PR slice
- Chain strategy: feature-branch-chain
- Current work unit: post-verify remediation slice — active-owner suspect-age handling
- Boundary: updates only the bootstrap lock classifier plus focused bootstrap CLI/runtime tests to close the verify warning without widening recovery scope
- Review budget impact: the remediation slice stays focused to the lock classifier and its covering tests, so reviewer load remains well below the 400-line budget for this follow-up

## Remaining Tasks

- None.

## Notes

- CLI wait status is emitted once per contention event on stderr so stdout remains a single final JSON envelope.
- Interactive stale-lock recovery now requires operator confirmation; `--non-interactive` preserves explicit failure and `--recover-stale-lock` is the only unattended recovery path.
- Current lock-file isolation remains covered by temporary directories plus explicit holder-process termination; no extra fixture cleanup was required after rerunning the focused CLI suite.
- Reviewability cleanup renamed the lock-diagnostics helpers to make the “contended owner” vs “abandoned stale metadata” paths easier to follow without changing behavior.
- Active lock ownership is now treated as suspect when its metadata age reaches the explicit threshold (`max(30s, requested timeout)`), which fixes the verify warning without widening recovery authority.
