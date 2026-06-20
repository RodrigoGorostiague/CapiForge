# Delta for Multi Agent Claims

## MODIFIED Requirements

### Requirement: Claim-state coordination

The system MUST allow `claimed` and `in_progress` only while a valid active claim exists. Lifecycle start flows MUST obtain a valid claim before entering `in_progress`. Lifecycle finish flows MUST require the same valid claim for automatic `done` or `blocked` closure. If the claim is released or expires, the task MUST leave active claimed execution before another agent proceeds, and automatic finish MUST fail closed with an explicit expiry outcome.
(Previously: Claim coordination required active ownership for `claimed` and `in_progress` but did not define lifecycle finish behavior after claim expiry.)

#### Scenario: Lease expires during work
- GIVEN a task is `in_progress` under an active claim
- WHEN the lease expires without renewal
- THEN the task can no longer be treated as actively owned by that agent

#### Scenario: Reject lifecycle finish after expiry
- GIVEN a lifecycle task is still `in_progress` but its claim lease expired
- WHEN the previous claimant attempts automatic closure
- THEN the system rejects the closure and returns an explicit expiry outcome
