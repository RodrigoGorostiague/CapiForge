# Delta for real-node-bootstrap

## MODIFIED Requirements

### Requirement: Persistent owner-local initialization

The system MUST create or reopen a persistent owner-local node home with deterministic local identity and storage paths. Initialization MUST transition state from `uninitialized` to `initialized` only after the local runtime stores are durable. When reopening an existing owner-local node home, the system MUST inspect the adopted local SQLite schema before runtime use, MUST auto-apply supported owner-local upgrades such as `tasks.lifecycle_key` and its required unique partial index, MUST apply those upgrades idempotently within one transaction, and MUST fail closed with an explicit local schema-compatibility error when the existing schema state is unsafe or unsupported. Initialization MUST NOT implicitly adopt any project.
(Previously: reopening reused the persisted home without any required schema upgrade or unsafe-drift guard.)

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
