# Task frac-0075 Specification: test_generation_cache Depth 2

## Problem Statement

`tests/test_generation_cache.py` exercises the `GenerationCache` helper on a
single LRU/eviction path and a restart round-trip, but the suite does not yet
prove the production cache works end-to-end as one deterministic path: take a
content-addressed `GenerationRequest`-shaped object, store generated audio,
look it up again, replace it with a new payload, hand a result-shaped object
to the queue/storage compatibility aliases (`get`/`set`), persist the index in
JSON-safe form, and recover the same entries after a process restart while
honoring both count and size LRU caps. The production module
(`my-claw/tools/senseweave/generation/cache.py`) already exposes the surface
needed for this end-to-end path; the gap is in the locked test surface.

The task deepens the test surface to depth 2 by adding a deterministic
one-path end-to-end test class plus a depth gate. Existing helper assertions
remain unchanged.

## Technical Approach

- Preserve all existing assertions in `tests/test_generation_cache.py`.
- Add a depth gate in `tests/test_test_generation_cache_depth.py` requiring
  `tests/test_generation_cache.py` to contain `GenerationCacheEndToEndTests`
  and classify at depth >= 2 via `sdp.fractal.classify_depth`.
- Append `GenerationCacheEndToEndTests` to the existing generation cache tests.
  The new tests will drive the existing public API through:
  - a full miss → put → hit → replace → hit cycle using a hash-bearing
    request shape and assert content-addressed file naming, suffix
    preservation, accessed-at LRU updates, and content replacement;
  - a queue/storage-style end-to-end path that mixes `put`/`lookup` with the
    `get`/`set` compatibility aliases and a result mapping that exposes
    `audio_path`, confirming both call shapes share the same on-disk entry;
  - a JSON-safe persistence round-trip that opens the on-disk
    `cache_index.json`, verifies version/entries shape, JSON-dumps it with
    sorted keys, and reads it back without losing any entry;
  - a restart-with-multi-entry cycle that recreates the cache against the
    same root, confirms every previously stored hash still resolves, and
    confirms a missing-on-disk entry is pruned on init while the index
    remains JSON-safe;
  - a combined size + count cap end-to-end where multiple entries are written
    in a deterministic touch order, an explicit lookup keeps the oldest
    entry warm, and a final `put` evicts the least-recently-used entry while
    keeping the warmed entry resident.
- No new production code is required; the existing cache module already
  exposes `lookup`, `put`, `get`, `set`, content-addressed filenames, JSON
  index persistence, and combined count/size LRU eviction.
- Treat the generated startup identity hardening checks as regression anchors.
  Existing CLI, daemon, first-boot, and narrative ASGI tests already cover
  `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence
  across standalone/federated boots, so this task re-runs those anchors
  rather than changing unrelated startup code.

## Edge Cases

- This depth-2 pass intentionally exercises one deterministic happy path
  rather than broad edge-case matrices.
- Replacement of an existing hash with a new payload must reuse the same
  content-addressed filename (suffix preserved) and overwrite bytes in place.
- Restart must rebuild entries from disk and prune entries whose payload file
  has been removed without raising.
- The JSON index must remain serializable with `sort_keys=True` so external
  tooling can diff snapshots.
- No new dependencies, migrations, provider secrets, database columns,
  runtime state directories, HTTP routes, or auth behavior are introduced.

## Acceptance Criteria

1. Existing generation cache helper assertions remain green.
   VERIFY: `pytest tests/test_generation_cache.py -q`

2. The new depth gate confirms `tests/test_generation_cache.py` reaches
   depth >= 2 and contains `GenerationCacheEndToEndTests`.
   VERIFY: `pytest tests/test_test_generation_cache_depth.py -q`

3. `GenerationCacheEndToEndTests` drives the full miss → put → hit →
   replace, queue/storage alias, JSON-safe persistence, restart, and
   combined count + size LRU cycle through the public API.
   VERIFY: `pytest tests/test_generation_cache.py::GenerationCacheEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, standalone
   and federated identity persistence, daemon bootstrap-before-announcer
   ordering, and narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing notes mention the frac-0075 generation cache depth-2 work.
   VERIFY: `grep -n "frac-0075" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
