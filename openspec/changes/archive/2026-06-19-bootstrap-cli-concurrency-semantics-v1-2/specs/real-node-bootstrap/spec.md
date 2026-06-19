# Delta for Real Node Bootstrap

## ADDED Requirements

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
