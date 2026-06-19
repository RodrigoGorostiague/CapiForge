# Archive Report: Real Node Bootstrap and Minimal CLI

## Summary

- Change: `real-node-bootstrap-minimal-cli`
- Archived on: `2026-06-19`
- Archive mode: `openspec`
- Archive status: `completed`
- Source archive path: `openspec/changes/real-node-bootstrap-minimal-cli/`
- Destination archive path: `openspec/changes/archive/2026-06-19-real-node-bootstrap-minimal-cli/`

## Artifact Check

| Artifact | Status | Path |
|---|---|---|
| Proposal | Present | `openspec/changes/real-node-bootstrap-minimal-cli/proposal.md` |
| Specs | Present | `openspec/changes/real-node-bootstrap-minimal-cli/specs/` |
| Design | Present | `openspec/changes/real-node-bootstrap-minimal-cli/design.md` |
| Tasks | Present | `openspec/changes/real-node-bootstrap-minimal-cli/tasks.md` |
| Apply Progress | Present | `openspec/changes/real-node-bootstrap-minimal-cli/apply-progress.md` |
| Verify Report | Present | `openspec/changes/real-node-bootstrap-minimal-cli/verify-report.md` |

## Task Completion Gate

- Persisted task artifact checked before archive: `openspec/changes/real-node-bootstrap-minimal-cli/tasks.md`
- Implementation tasks complete: `12/12`
- Unchecked implementation tasks remaining: `0`
- Archive-time checkbox reconciliation performed: `No`

## Verification Gate

- Verify verdict: `PASS WITH WARNINGS`
- CRITICAL issues: `None`
- WARNING count: `1`
- Blocking verification issues: `No`

### Verification Warning Recorded

1. Overlapping out-of-process `adopt` and `read` invocations remain out of scope for this slice; sequential subprocess behavior is verified, but concurrent adoption/read synchronization is not guaranteed.

## Spec Sync

| Domain | Action | Details |
|---|---|---|
| `real-node-bootstrap` | Created | Promoted full change spec to new main spec with 3 requirements and 6 scenarios. |
| `mcp-cli-surface` | Updated | Replaced `Deterministic operational surface` requirement to add owner-local `init`/`adopt`/`status`/`read` behavior and 2 new scenarios while preserving other requirements. |

## Config Rules Applied

1. Reviewed `openspec/config.yaml` archive rule: warn before merging destructive deltas.
2. Merge was non-destructive: one new main spec created and one existing requirement updated without removals.

## Archive Verification Checklist

- [x] Main specs updated before archive move
- [x] Change folder contains proposal, specs, design, tasks, apply-progress, verify-report, and archive-report
- [x] Archived `tasks.md` contains no unchecked implementation tasks
- [x] Active changes directory no longer contains `real-node-bootstrap-minimal-cli` after move

## Final Source of Truth

- `openspec/specs/real-node-bootstrap/spec.md`
- `openspec/specs/mcp-cli-surface/spec.md`

## Notes

This archive closes the SDD cycle for the owner-local bootstrap and minimal CLI change. No intentional partial archive override was used.
