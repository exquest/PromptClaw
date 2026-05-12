# PRD: Publication and Gallery Surfaces

## Overview

Every home should expose a public gallery surface as part of its base runtime, but publication must remain private-by-default.

The defaults are:
- gallery page exists per home
- reachable on local network/Tailscale by default
- wider publication requires explicit publish action
- external publication is read-only by default

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| PGS-001 | Create a per-home gallery page backed by the home’s public artifact feed. | MUST | T1 | - Every home can render a gallery page from its local public artifacts<br/>- Page includes identity, lineage-safe summary, and curated outputs<br/>- Page generation works without federation enabled |
| PGS-002 | Make publication private-by-default. The gallery page must be reachable on local network/Tailscale by default and not internet-public until explicitly published. | MUST | T1 | - Default deployment is local/Tailscale only<br/>- No public route is opened without explicit publish action<br/>- Publication mode is visible in status/config |
| PGS-003 | Implement explicit publish controls for broader exposure. Publish must be a separate action from normal home creation or federation enrollment. | MUST | T1 | - Operator can promote a gallery from private to public intentionally<br/>- Publish action is auditable<br/>- Unpublish returns the page to private access |
| PGS-004 | Keep public publication read-only by default. External viewers must not gain interactive control unless a separate non-default interaction layer is configured. | MUST | T1 | - Public page has no mutation or control actions by default<br/>- Interaction features remain disabled unless explicitly configured<br/>- Status surfaces differentiate read-only vs interactive publication |
| PGS-005 | Define the `GalleryRenderArtifact` schema. | SHOULD | T1 | - Curated renders use one documented schema<br/>- Gallery payload omits private memory, secrets, and raw transcripts<br/>- Render payload remains consistent across homes |
| PGS-006 | Define the `GalleryCaptionArtifact` schema. | SHOULD | T1 | - Captions and artwork metadata use one documented schema<br/>- Metadata remains consistent across homes<br/>- Gallery page can render the metadata without custom per-home logic |
| PGS-007 | Define the `GalleryIdentitySummary` schema. | SHOULD | T1 | - Identity summary omits private memory and raw logs<br/>- Summary payload uses one documented schema<br/>- Gallery page can render the summary consistently |
| PGS-008 | Define the `GalleryReleaseSummary` schema. | SHOULD | T1 | - Release and roadmap snippets use one documented schema<br/>- Summary payload stays public-safe by default<br/>- Gallery page can render the summaries consistently |
| PGS-009 | Add status surfaces showing gallery reachability, publication mode, last publish event, and whether the page is federated-visible, public, or local-only. | SHOULD | T1 | - Operator can tell how a gallery is exposed<br/>- Changes in publish mode are visible quickly<br/>- Status integrates with federation summaries |
| PGS-010 | Add tests for default local/Tailscale access, explicit publish/unpublish, read-only public mode, and private-artifact exclusion from the gallery surface. | MUST | T2 | - Tests cover private default and publish transitions<br/>- Read-only public mode is enforced in tests<br/>- Private artifacts never leak into gallery output |

## Notes

- Publication and federation are related but not identical. A home can be federated and still remain publicly private.
- The public gallery page is part of the artistic identity of each home.
