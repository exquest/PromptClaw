# PRD: Instance Identity and Lineage

## Overview

PromptClaw homes must be distinguishable, traceable, and durable across clone, rename, publish, and federation operations.

Identity is not just a keypair. It includes:
- immutable machine identity
- mutable artistic naming
- lineage history
- mode and trust metadata
- inherited mind/personality continuity for clones

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| IDLINE-001 | Define a canonical home identity record containing `instance_id`, `instance_name`, creation timestamp, mode, version/release, and capability summary. | MUST | T1 | - Identity record has a documented schema<br/>- Runtime reads and writes one canonical identity file<br/>- Identity survives reboot and upgrade |
| IDLINE-002 | Mint an immutable globally unique `instance_id` for every home at creation time. | MUST | T1 | - No two installed homes share an `instance_id`<br/>- Clone installs always mint a new id<br/>- Rename does not change `instance_id` |
| IDLINE-003 | Auto-generate an artistic `instance_name` during install/clone and support optional later rename with rename-history retention. | MUST | T1 | - New homes receive an auto-generated name<br/>- Operators can rename later<br/>- Prior names remain visible in audit/lineage history |
| IDLINE-004 | Record lineage metadata for clones: parent id, origin release, clone timestamp, initial mode, and secret policy used. | MUST | T1 | - Clone metadata is stored locally<br/>- Lineage survives promotion from standalone to federated<br/>- Lineage skeleton is available for announcement/public status |
| IDLINE-005 | Define clone inheritance rules for artistic memory, style libraries, pet/personality state, and current narrative identity. | MUST | T1 | - Clone tests prove inherited state is present on first boot<br/>- Clone queue remains empty<br/>- Inherited state is distinguishable from new local state |
| IDLINE-006 | Ensure clones diverge immediately after creation unless explicit sharing occurs later. No automatic post-clone private-memory sync is allowed. | MUST | T1 | - Parent changes after clone do not auto-appear on child<br/>- Child changes after clone do not auto-appear on parent<br/>- Explicit share/import remains possible |
| IDLINE-007 | Keep lineage metadata even for standalone homes. Standalone must mean “not participating in federation by default,” not “no provenance.” | MUST | T1 | - Standalone homes store lineage locally<br/>- Standalone promotion to federation reuses existing lineage<br/>- No reinstall is required to recover lineage |
| IDLINE-008 | Add identity and lineage summaries to status/public-artifact surfaces without exposing raw private memory or secrets. | SHOULD | T1 | - Public status includes instance name/id, release, and lineage skeleton<br/>- Raw private state is excluded<br/>- Summary format is consistent across homes |
| IDLINE-009 | Add tests covering new home identity creation, clone lineage creation, rename history, standalone promotion, and divergence-after-clone behavior. | MUST | T2 | - Test suite covers identity lifecycle end to end<br/>- Clone tests assert inherited state + divergence semantics<br/>- Promotion tests preserve ids and lineage |

## Notes

- Identity continuity and personality continuity are separate: the clone inherits mind-state continuity but not the same immutable identity.
- Lineage should support later public gallery provenance and bundle provenance.
