# Real Node Bootstrap Specification

## Purpose

Define the smallest supported V1.1 path for persistent owner-local node initialization and explicit adoption of this repository as one local seed project.

## Requirements

### Requirement: Persistent owner-local initialization

The system MUST create or reopen a persistent owner-local node home with deterministic local identity and storage paths. Initialization MUST transition state from `uninitialized` to `initialized` only after the local runtime stores are durable. Initialization MUST NOT implicitly adopt any project.

#### Scenario: Initialize a fresh local node
- GIVEN no local node home exists
- WHEN the operator runs bootstrap initialization
- THEN the system persists the local node home and records state `initialized`
- AND no project is marked as adopted

#### Scenario: Reopen an existing local node home
- GIVEN a local node home already exists
- WHEN the operator runs bootstrap initialization again
- THEN the system reuses the same persisted home and local identity

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
