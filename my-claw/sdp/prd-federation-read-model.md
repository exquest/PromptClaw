# PRD: Federation Read Model

## Overview

Federation read access should be easy, safe, and useful by default.

Federated homes should automatically see each other’s:
- status
- memory summaries
- public artifacts
- public gallery surfaces

They should not automatically gain write power, raw memory access, or secret access.

## Core Decisions

1. Read trust is inherited automatically for known descendants in federated mode.
2. Trust is revocable.
3. Standalone homes do not announce or auto-share until promoted.
4. Newly federated homes announce identity and lineage skeleton first, not full history dumps.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| FEDREAD-001 | Define the canonical default-readable status and capability summary classes for federated homes. | MUST | T1 | - Status/capability classes are enumerated in one schema/config file<br/>- Runtime defaults match the documented list<br/>- Private classes are excluded by default |
| FEDREAD-002 | Define the `FederationGallerySummary` readable class. | MUST | T1 | - Gallery summary is enumerated in one schema/config file<br/>- Gallery metadata has one documented shape<br/>- Raw private memory and secrets are excluded |
| FEDREAD-002a | Define the `FederationReleaseSummary` readable class. | MUST | T1 | - Release and roadmap summaries are enumerated in one schema/config file<br/>- Summary payloads have one documented shape<br/>- Raw private memory and secrets are excluded |
| FEDREAD-003 | Implement descendant/peer read trust for federated homes, with revocation support. | MUST | T1 | - Federated descendants can read default-readable classes on first announcement<br/>- Revocation removes that access cleanly<br/>- Revocation is audited |
| FEDREAD-004 | Implement first-boot federation announcement for cloned federated homes. The announcement must include identity, lineage skeleton, release, mode, capability summary, and publication status. | MUST | T1 | - Federated clones announce on first boot<br/>- Standalone clones do not announce<br/>- Announcement payload excludes raw private memory and secrets |
| FEDREAD-005 | Implement promotion announcement for standalone homes entering federated mode later. Promotion must announce minimal identity plus lineage skeleton, not full stored history. | MUST | T1 | - Promotion emits an announcement event<br/>- Minimal payload is used<br/>- Richer history sharing remains explicit later |
| FEDREAD-006 | Add a federation registry/read-cache model that tracks known homes, lineage relationships, trust status, and last-seen summaries without requiring write permission. | MUST | T1 | - Registry stores peers and read-trust state<br/>- Last-seen/read summaries update on announcements and heartbeats<br/>- Cache remains usable if a peer goes offline |
| FEDREAD-007 | Add a read-only federation CLI/status surface for inspecting known homes, their mode, lineage skeleton, availability, and public artifact summaries. | SHOULD | T1 | - Operator can list known homes and status from CLI<br/>- Output distinguishes local, descendant, and peer homes<br/>- Read-only inspection requires no mutation permissions |
| FEDREAD-008 | Add tests for descendant auto-trust, revocation, first-boot announcement, standalone promotion, and minimal-history announcement behavior. | MUST | T2 | - All read-trust flows are covered by tests<br/>- Promotion tests prove no full private-history dump occurs<br/>- Revocation tests prove access is removed promptly |

## Notes

- “Memory summaries” are allowed here; raw private memory is not.
- Read federation should make the network feel alive without weakening sovereignty.
