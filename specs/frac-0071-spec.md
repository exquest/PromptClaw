# Task frac-0071 Specification: test_federation_discovery Depth 2

## Problem Statement

`tests/test_federation_discovery.py` covers the federation peer-discovery
surface with seven function-level tests (Tailscale probing, self-IP exclusion,
malformed-identity tolerance, save/load round-trip, and merge online/offline
flagging), but the depth-2 task requires end-to-end coverage that drives the
full discover → save → load → re-scan → merge → save cycle through the public
API and proves the registry produces meaningful, JSON-safe output.

Exploration confirmed `promptclaw/federation/discovery.py` already implements
the simplest working production path for `discover_peers`,
`save_peer_registry`, `load_peer_registry`, `merge_peer_registry`, and the
`PeerInfo` dataclass; no production gap blocks the end-to-end path. This task
therefore adds a depth gate plus an end-to-end test class that exercises the
existing public surface against fakes for `tailscale status` and the
`/federation/v1/identity` endpoint.

## Technical Approach

- Preserve the existing assertions in `tests/test_federation_discovery.py`.
- Add a depth gate at `tests/test_test_federation_discovery_depth.py` that
  loads `sdp/fractal.classify_depth` via `importlib.util` (matching the
  pattern from `tests/test_test_dashboard_generator_depth.py`) and requires
  `tests/test_federation_discovery.py` to classify at depth >= 2 and to
  contain the `FederationDiscoveryEndToEndTests` class.
- Append a `FederationDiscoveryEndToEndTests` class to
  `tests/test_federation_discovery.py`. The class drives the public
  `discover_peers`, `save_peer_registry`, `load_peer_registry`, and
  `merge_peer_registry` API end-to-end through:
  - a fake `subprocess.run` returning `tailscale status --json`,
  - a fake `urlopen` returning canned identity payloads keyed by IP,
  - a temporary registry file that is written, reloaded, merged with a
    second scan, and rewritten.
- Verify the resulting registry is JSON-safe, that `PeerInfo` dataclasses
  round-trip via `to_dict`/`from_dict`, that `merge_peer_registry` flips
  the `online` flag for previously seen peers that disappear from a fresh
  scan, that newly discovered peers are appended, and that returning peers
  retain their original `first_seen` timestamp while updating `last_seen`.
- Treat the generated startup identity hardening bullets as regression
  anchors. Existing `bootstrap_identity()` wiring already runs before
  `FirstBootAnnouncer` in CLI startup, the daemon poll loops, and narrative
  ASGI imports; this task re-runs those tests instead of changing unrelated
  startup code.
- No new dependencies, migrations, provider secrets, database columns,
  runtime state files, HTTP routes, or auth behavior are introduced.

## Edge Cases

- A fresh scan that returns no peers leaves an existing registry intact but
  marks every previously seen peer as `online=False`.
- Malformed or incomplete identity payloads cause that peer to be skipped
  during discovery (covered by an existing function-level test; the
  end-to-end test re-asserts the same behavior is observable through the
  full pipeline).
- Multi-IP peers with the first IP unreachable still resolve when a later
  IP responds with a valid identity payload.
- Returning peers preserve `first_seen`; new peers receive a `first_seen`
  equal to `last_seen`.

## Acceptance Criteria

1. Existing federation discovery tests remain green.
   VERIFY: `pytest tests/test_federation_discovery.py -q`

2. The new depth gate confirms `tests/test_federation_discovery.py` reaches
   depth >= 2 and contains `FederationDiscoveryEndToEndTests`.
   VERIFY: `pytest tests/test_test_federation_discovery_depth.py -q`

3. `FederationDiscoveryEndToEndTests` drives the full discover → save →
   load → re-scan → merge → save cycle and verifies the registry contains
   meaningful, JSON-safe peer data.
   VERIFY: `pytest tests/test_federation_discovery.py::FederationDiscoveryEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone
   and federated identity persistence, daemon bootstrap-before-announcer
   ordering, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0071 federation discovery depth-2
   work.
   VERIFY: `grep -n "frac-0071" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
