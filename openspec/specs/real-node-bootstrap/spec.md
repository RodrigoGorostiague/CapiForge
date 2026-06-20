# Real Node Bootstrap Specification

## Purpose

Define the smallest supported V1.1 path for persistent owner-local node initialization and explicit adoption of this repository as one local seed project.

## Requirements

### Requirement: Persistent owner-local initialization

The system MUST create or reopen a persistent owner-local node home with deterministic local identity and storage paths. Initialization MUST transition state from `uninitialized` to `initialized` only after the local runtime stores are durable. When reopening an existing owner-local node home, the system MUST inspect the adopted local SQLite schema before runtime use, MUST auto-apply supported owner-local upgrades such as `tasks.lifecycle_key` and its required unique partial index, MUST apply those upgrades idempotently within one transaction, and MUST fail closed with an explicit local schema-compatibility error when the existing schema state is unsafe or unsupported. Initialization MUST NOT implicitly adopt any project.

#### Scenario: Initialize a fresh local node
- GIVEN no local node home exists
- WHEN the operator runs bootstrap initialization
- THEN the system persists the local node home and records state `initialized`
- AND no project is marked as adopted

#### Scenario: Reopen an existing local node home
- GIVEN a local node home already exists with supported current schema
- WHEN the operator runs bootstrap initialization again
- THEN the system reuses the same persisted home and local identity
- AND no schema changes are required

#### Scenario: Upgrade a stale adopted local node on reopen
- GIVEN an adopted local node DB is missing `tasks.lifecycle_key` or its required unique partial index
- WHEN an owner-local open path reopens the node home
- THEN the system upgrades the DB before runtime use
- AND later lifecycle-capable operations see a compatible schema without manual SQL

#### Scenario: Fail closed on unsafe schema drift
- GIVEN an adopted local node DB has partial or unsupported schema state
- WHEN an owner-local open path attempts to reopen it
- THEN the system returns an explicit local schema-compatibility error
- AND no partial upgrade is committed

### Requirement: Explicit seed project adoption

The system MUST allow project adoption only after initialization. Adoption MUST persist the adopted project metadata for this repository, MUST transition state from `initialized` to `adopted`, and MUST keep the local node as the only canonical writer for that adopted project in this V1.1 slice. The system MUST reject adoption attempts before initialization or attempts to replace the adopted project with a different local project.

#### Scenario: Adopt this repository after initialization
- GIVEN the local node state is `initialized`
- WHEN the operator explicitly adopts this repository
- THEN the system persists the repository metadata and records state `adopted`

#### Scenario: Reject invalid adoption transition
- GIVEN the local node state is `uninitialized` or already bound to a different local project
- WHEN the operator requests adoption
- THEN the system rejects the request with an explicit state or trust-boundary error

### Requirement: Deterministic local state visibility

The system MUST expose the current bootstrap state as `uninitialized`, `initialized`, or `adopted`. State inspection MUST report the local identity, storage location, and adopted-project metadata that are actually persisted. Read access MAY return deterministic project data only for the adopted repository and MUST NOT mutate bootstrap or project state.

#### Scenario: Inspect adopted local state
- GIVEN the local node state is `adopted`
- WHEN the operator inspects bootstrap state
- THEN the system returns persisted local identity, storage paths, and adopted-project metadata

#### Scenario: Read without mutation
- GIVEN the local node state is `adopted`
- WHEN the operator requests deterministic project data
- THEN the system returns read-only data for the adopted repository without changing persisted state

### Requirement: Exclusive local bootstrap execution

The system MUST serialize local bootstrap operations behind one repo-local exclusive lock before reading or mutating bootstrap manifest or SQLite-backed state. A contending operation SHALL wait by default until the configured timeout expires. When ownership is suspect because owner identity, PID/liveness, or lock age cannot confirm a healthy owner, the system MUST report those details and MUST require explicit operator recovery instead of auto-clearing the lock.

#### Scenario: Wait and continue after the active owner finishes
- GIVEN one bootstrap command already owns the local lock
- WHEN another bootstrap command starts before its timeout expires
- THEN the contender waits until the lock is released
- AND it resumes against the durable state left by the prior owner

#### Scenario: Fail after contention timeout
- GIVEN one bootstrap command still owns the local lock
- WHEN another bootstrap command reaches its configured timeout while waiting
- THEN the system fails with an explicit timeout outcome and performs no state mutation

#### Scenario: Stop on suspect ownership
- GIVEN the local lock exists but healthy ownership cannot be confirmed
- WHEN a bootstrap command attempts to acquire that lock
- THEN the system reports the known owner details and requires explicit recovery action
