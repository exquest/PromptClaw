# PRD: Bundle Exchange

## Overview

Federated homes should be able to offer each other installable gifts:
- style libraries
- memory packs
- scene packs
- plugins/tools
- prompt packs
- calibration/rehearsal bundles

But bundle import must preserve sovereignty and provenance.

## Core Decisions

1. Bundle import always requires explicit target-home approval.
2. Bundles mount as removable external libraries first.
3. Adoption is a later explicit action.
4. Adopted bundles remain source-linked by default for provenance and update offers.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| BUNDLE-001 | Define bundle artifact types and manifests for style, memory, scene, plugin, prompt, and calibration bundles. | MUST | T1 | - Bundle manifest contains type, source home, version, compatibility, and contents summary<br/>- Bundle types are validated on import<br/>- Unknown bundle types are rejected cleanly |
| BUNDLE-002 | Implement bundle offer/receive flow across federation. Homes must be able to advertise available bundles and send signed bundle offers to peers. | MUST | T1 | - Bundle offers are discoverable<br/>- Offers include provenance and compatibility info<br/>- Receiving home can inspect without importing |
| BUNDLE-003 | Require explicit target-home review and approval before any bundle import. | MUST | T1 | - No bundle mutates a target home without approval<br/>- Approval flow records bundle source and contents summary<br/>- Rejected bundles remain unmounted |
| BUNDLE-004 | Mount approved bundles as removable external libraries first, without merging them into core local memory/config by default. | MUST | T1 | - Mounted bundles are usable without full adoption<br/>- Mounted bundles can be removed cleanly<br/>- Base home identity/state remains intact after mount |
| BUNDLE-005 | Support granular adoption from mounted bundles. Target homes must be able to adopt all, adopt selected items, or keep a bundle mounted as external reference only. | SHOULD | T2 | - Adoption can be selective<br/>- Adopted material becomes locally available<br/>- External-only mode remains possible |
| BUNDLE-006 | Preserve source linkage for adopted bundles by default so future update offers and provenance remain visible. | SHOULD | T1 | - Adopted bundles retain source metadata<br/>- Future update offers can target the adopted bundle<br/>- Operators can later detach if they want a fully local fork |
| BUNDLE-007 | Distinguish safer data bundles from riskier code/plugin bundles in review UI and policy. | MUST | T1 | - Plugin/code bundles are clearly marked higher risk<br/>- Review output shows bundle risk class<br/>- Policy hooks can require stricter approval for risky bundles |
| BUNDLE-008 | Add tests for bundle offer, approval, mount, remove, adopt, provenance retention, update offer linkage, and risky-bundle classification. | MUST | T2 | - Test suite covers bundle lifecycle end to end<br/>- Mounted bundles can be removed without residue<br/>- Adopted bundles retain provenance metadata |

## Notes

- Mounted-first is the right default for artistic exchange. A home should be able to try an influence without rewriting itself.
- Bundle exchange is a better abstraction than raw cross-home memory mutation.
