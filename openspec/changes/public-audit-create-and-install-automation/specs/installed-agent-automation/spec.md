# Installed Agent Automation Specification

## Purpose

Define the installer-managed automation contract that makes completed-work recording available in installed CapiForge sessions.

## Requirements

### Requirement: Installer-managed completed-work contract

The installer MUST deliver one versioned, repo-managed automation artifact that teaches installed agent sessions how to record completed same-project work. Installed sessions MUST inherit this contract after installation or configuration without manual prompt editing.

#### Scenario: Install exposes the automation artifact
- GIVEN an operator completes installation or config refresh
- WHEN an installed session starts in an adopted project
- THEN the completed-work automation contract is available from the installed artifact

#### Scenario: Missing artifact stays visible
- GIVEN installation cannot place or register the artifact
- WHEN the session attempts completed-work automation
- THEN the system returns an explicit unavailable outcome and does not fall back to hidden behavior

### Requirement: Public-surface lifecycle execution

The automation MUST execute completed-work recording only through public product-facing operations. It MUST create and publish the brief audit before lifecycle start when no published origin audit exists, MUST require explicit finish metadata before lifecycle finish, and MUST NOT use direct DB seeding or hidden mutation shortcuts.

#### Scenario: Record completed work through installed automation
- GIVEN an adopted owner-local project has no preseeded audit for the work
- WHEN installed automation records completed work
- THEN it uses public audit create or publish and lifecycle start or finish operations to close the task as `done`

#### Scenario: Stop after a public-surface failure
- GIVEN audit publish or lifecycle start fails validation
- WHEN installed automation runs the sequence
- THEN it reports the failure explicitly and does not attempt later closure steps
