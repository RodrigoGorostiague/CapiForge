# Multi Agent Claims Specification

## Purpose

Prevent conflicting AI execution by enforcing exclusive claims, renewable leases, and escalation-first coordination.

## Requirements

### Requirement: Exclusive active claim

The system MUST allow at most one active claim per task at a time. A claim MUST include `node_id`, `agent_id`, `session_id`, a short intention or plan, lease start, and lease expiry.

#### Scenario: Claim an available task
- GIVEN a task is `ready` and has no active claim
- WHEN an agent claims it
- THEN the system creates one active claim with all required identity and lease fields

### Requirement: Renewable lease with expiry

The system MUST model claims as renewable leases with expiry. An expired lease MUST stop blocking new claims and SHOULD be surfaced for review.

#### Scenario: Renew an active lease
- GIVEN an agent still owns an active claim
- WHEN it renews before expiry
- THEN the lease expiry is extended without creating a second claim

#### Scenario: Reclaim after expiry
- GIVEN a claim lease has expired
- WHEN another agent requests the task
- THEN the expired claim no longer prevents a new claim

### Requirement: Escalation on claimed work

Two agents MUST NOT actively work the same task. If an agent encounters a task already claimed by another active lease, it MUST escalate to a human instead of proceeding.

#### Scenario: Encounter an active claim
- GIVEN a task has an active claim from another agent
- WHEN a second agent attempts to start work
- THEN the system blocks execution
- AND requires escalation to a human

### Requirement: Claim-state coordination

The system MUST allow `claimed` and `in_progress` only while a valid active claim exists. Lifecycle start flows MUST obtain a valid claim before entering `in_progress`. Lifecycle finish flows MUST require the same valid claim for automatic `done` or `blocked` closure. If the claim is released or expires, the task MUST leave active claimed execution before another agent proceeds, and automatic finish MUST fail closed with an explicit expiry outcome.

#### Scenario: Lease expires during work
- GIVEN a task is `in_progress` under an active claim
- WHEN the lease expires without renewal
- THEN the task can no longer be treated as actively owned by that agent

#### Scenario: Reject lifecycle finish after expiry
- GIVEN a lifecycle task is still `in_progress` but its claim lease expired
- WHEN the previous claimant attempts automatic closure
- THEN the system rejects the closure and returns an explicit expiry outcome
