# PRD: Clone and Home Creation

## Overview

PromptClaw must be able to create a new sovereign home on a new machine without treating that machine like a hand-built snowflake.

This PRD defines three creation paths:

1. `wizard` — guided local home creation
2. `unattended` — zero-touch install on a target machine
3. `clone` — unattended install seeded from an existing PromptClaw home

The default seed source is a packaged release snapshot, not an arbitrary git branch. Development-seeded homes may still be supported as an explicit override.

## Core Decisions

1. Every home gets a new immutable `instance_id`.
2. Every home gets an auto-generated artistic `instance_name`, optionally renamed later.
3. Clone installs inherit capabilities, artistic memory, pet/personality state, and current narrative identity.
4. Clone installs always start with an empty local queue.
5. Secrets-copy policy is user-settable per install.
6. `standalone` and `federated` are install-time defaults, not permanent modes.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| HOMECLONE-001 | Define the versioned release-snapshot manifest for PromptClaw home installers. | MUST | T1 | - Manifest schema is documented<br/>- Manifest records release identity and payload entries<br/>- Same release always produces the same manifest contents |
| HOMECLONE-002 | Package the base runtime payload for release-snapshot installs so a target home can bootstrap without local git state. | MUST | T2 | - Runtime payload includes code and required templates<br/>- Payload unpacks on a clean target without reading a git checkout<br/>- Payload contents match the manifest |
| HOMECLONE-003 | Package the service bootstrap payload for release-snapshot installs. | MUST | T2 | - Bootstrap payload includes service templates for a clean target<br/>- Services can be configured from installer artifacts alone<br/>- Payload contents match the manifest |
| HOMECLONE-003a | Package the prompt-seed and migration payload for release-snapshot installs. | MUST | T2 | - Prompt seeds are available after unpack<br/>- Migration metadata is available after unpack<br/>- Payload contents match the manifest |
| HOMECLONE-004 | Add an unattended install flow that provisions PromptClaw directories, virtualenv, and authority paths on a target machine without interactive prompts. | MUST | T2 | - One command can create the base home layout on a clean target<br/>- Install is idempotent on rerun<br/>- Authority paths are recorded in the home manifest |
| HOMECLONE-005 | Add an unattended service/bootstrap step that configures the new home from the installer payload and starts the managed services. | MUST | T2 | - Managed services start from the installed payload<br/>- Bootstrap uses installer artifacts rather than local repo assumptions<br/>- Failed bootstrap leaves a readable report |
| HOMECLONE-006 | Add a clone install flow that seeds a new home from an existing PromptClaw source home while minting a new identity and an empty local queue. | MUST | T2 | - Clone path creates a new `instance_id`<br/>- Clone inherits source memory/personality/art state<br/>- Clone queue starts empty |
| HOMECLONE-007 | Implement install-time mode selection with `standalone` and `federated` as explicit initial modes. | MUST | T1 | - Install manifest stores the initial mode<br/>- Standalone homes do not announce or auto-share<br/>- Federated homes enable discovery and announcement hooks |
| HOMECLONE-008 | Implement user-settable secret policy during unattended and clone install. The operator must be able to choose between copying source secrets and provisioning fresh secrets. | MUST | T1 | - Secret policy is explicit in install config<br/>- Copying secrets is optional, not implicit<br/>- Fresh-secret installs boot without source-secret leakage |
| HOMECLONE-009 | Run the startup wizard intake for interactive installs and generate an unattended intake profile for non-interactive installs. Both paths must converge on the same home manifest structure. | MUST | T1 | - Wizard installs create the existing onboarding artifacts<br/>- Unattended installs create equivalent machine-readable intake state<br/>- Runtime reads one canonical manifest shape |
| HOMECLONE-010 | Add a post-install verification step that checks service health, authority DB locations, write permissions, and queue readiness before the new home is considered live. | MUST | T1 | - Failed verification keeps the home in a not-live state<br/>- Verification report is machine-readable and human-readable<br/>- Success records a live-home activation event |
| HOMECLONE-011 | Support promotion of a standalone home into federated mode without reinstalling. | SHOULD | T1 | - Standalone homes can later join federation from local state<br/>- Promotion does not rewrite `instance_id` or lineage<br/>- Promotion triggers federation announcement flow |
| HOMECLONE-012 | Support dev-seeded home creation from repo/branch as an explicit advanced install mode. This path must be clearly marked non-default and record source branch/revision in lineage metadata. | SHOULD | T2 | - Operator can choose repo/branch seeding explicitly<br/>- Home manifest records git source and commit<br/>- Default path remains release-snapshot install |
| HOMECLONE-013 | Add end-to-end tests covering unattended install, clone install, standalone install, federated install, and idempotent reinstall behavior. | MUST | T2 | - Test matrix covers all install modes<br/>- Clone tests verify inherited state + empty queue<br/>- Reinstall tests prove no duplicate identities or broken services |

## Notes

- Queue cloning is explicitly out of scope for clone installs.
- A cloned home is a descendant organism, not a queue replica.
- The install path should be able to target local machines first, then remote SSH/Tailscale targets.
