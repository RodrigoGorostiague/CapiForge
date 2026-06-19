# Task Audit Model Specification

## Purpose

Define audits and tasks as the authoritative operational model for AI-first, human-overridable work.

## Requirements

### Requirement: Audit lifecycle and immutability

The system MUST model audits with states `draft`, `published`, `closed`, and `superseded`. Closed audits MUST be immutable. Corrections MUST be recorded as addenda or follow-up audits instead of mutating closed content.

#### Scenario: Close an audit
- GIVEN a published audit with complete findings
- WHEN an operator closes it
- THEN the audit state becomes `closed`
- AND later corrections require an addendum or follow-up audit

### Requirement: Task-centered operations

The system MUST treat tasks as the central operational entity. Every task MUST be justified by an audit, MUST have exactly one origin audit, and MAY link additional audits later.

#### Scenario: Create a justified task
- GIVEN a published audit identifies actionable work
- WHEN a task is created from that audit
- THEN the task stores that audit as its origin audit
- AND the task MAY accept later linked audits without replacing the origin

### Requirement: Task lifecycle and readiness

The system MUST support task states `proposed`, `ready`, `claimed`, `in_progress`, `blocked`, `done`, and `cancelled`. A task MUST NOT enter `ready` unless it has sufficient description, valid justification, no unresolved conflict, and enough execution context. Humans MAY reopen `done` or `cancelled` tasks.

#### Scenario: Promote a task to ready
- GIVEN a proposed task with description, justification, conflict check, and execution context
- WHEN readiness is evaluated
- THEN the task may enter `ready`

#### Scenario: Reopen a finished task
- GIVEN a task in `done`
- WHEN a human reopens it
- THEN the task leaves `done` and returns to a human-selected active state

### Requirement: AI mutation justification

AI is the primary operator and humans override its decisions. Every AI task state mutation MUST record justification metadata sufficient to explain why the change was made and what evidence supported it.

#### Scenario: AI changes task state
- GIVEN an AI agent updates a task from `ready` to `blocked`
- WHEN the mutation is stored
- THEN the record includes justification metadata
- AND a human may later override that state

### Requirement: Task structure and closure metadata

The system MUST store task relations `depends_on`, `blocks`, `relates_to`, and `duplicates`. Task fields MUST include `priority`, `effort`, `risk`, and `type`. Priority MUST be `low|medium|high|critical`; effort and risk MUST be `low|medium|high`; type MUST be `fix|feature|audit_followup|doc|refactor|ops`. `blocked` MUST include reason, evidence or reference, and suggested next step. `done` MUST include result, affected artifacts, linked references, and expected impact. Severity MUST be represented separately from priority.

#### Scenario: Record a blocked task
- GIVEN a task cannot proceed
- WHEN it enters `blocked`
- THEN the task stores a reason, evidence or reference, and suggested next step

#### Scenario: Complete a task
- GIVEN work is finished
- WHEN the task enters `done`
- THEN it stores result, affected artifacts, linked references, and expected impact
