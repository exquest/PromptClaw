# Task frac-0090 Specification: test_mood_mirror Depth 2

## Problem Statement

`tests/test_mood_mirror.py` exercises the mood-to-parameter mapper
`my-claw/tools/senseweave/mood_mirror.py` at the function level: face
expression rules across the seven canonical states, RGB background colour
ranges and per-mood dominant channels, music tempo/volume/key/density
parameter shaping, and art palette/complexity/theme-hint shaping.

The production module already exposes the depth-2 surface needed to run a
single end-to-end mood translation through every public helper: a single
`mood = {"energy", "valence", "arousal"}` dict can flow through
`mood_to_face_expression`, `mood_to_background_color`, `mood_to_music_params`,
and `mood_to_art_params` to produce a coherent face/audio/art payload that
downstream consumers (face daemon, gallery renderer, music engine) can
serialize for operator dashboards.

The missing work for frac-0090 is to deepen the test file itself from
function-level checks to a named end-to-end test class proving the public
mood mirror surface threads a realistic per-mood scenario into a JSON-safe
combined payload in one deterministic path, and to pin that depth with a
machine-verifiable gate.

The generated startup identity hardening bullets are already represented in
this checkout by CLI, daemon-ordering, first-boot persistence, and narrative
ASGI startup tests. This task treats those as regression anchors rather than
changing unrelated startup flow without a concrete gap.

## Technical Approach

- Add a deterministic depth gate at
  `tests/test_test_mood_mirror_depth.py` that requires
  `tests/test_mood_mirror.py` to contain `MoodMirrorEndToEndTests` and
  classify at depth >= 2 through the repo-local `sdp.fractal.classify_depth`.
- Append `MoodMirrorEndToEndTests` to `tests/test_mood_mirror.py`.
- Exercise one public end-to-end path through every helper:
  - Drive a curated set of canonical moods (sleeping, calm, happy, excited,
    anxious, sad, curious) through all four helpers in a single pass.
  - Confirm each mood produces the documented face expression.
  - Confirm each mood produces an RGB triple within `0..255` whose dominant
    channel matches the documented colour intent (deep blue for calm, near
    black for sleeping, dark red for anxious, purple for excited, warm blue
    for happy, cool blend for curious, muted for sad).
  - Confirm each mood produces music params with the expected
    `tempo_factor` / `volume_factor` ranges, `key_preference`, and
    `density`.
  - Confirm each mood produces art params with documented palette /
    complexity / theme-hint contracts.
  - Round-trip a combined `face/colour/music/art` diagnostic payload
    through `json.dumps(..., sort_keys=True)` and `json.loads(...)` so
    downstream operators can persist and replay the snapshot.
- Preserve existing assertions and production behavior unless the new
  tests expose a concrete implementation gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state files, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end sequence intentionally covers the simple happy path: one
  mood per canonical face expression, all helpers in one pass.
- Existing focused tests remain responsible for boundary moods at zero/one,
  per-channel dominance assertions, and per-helper enum membership.
- Combined diagnostic output must remain JSON-safe so the face daemon and
  gallery renderer can serialize it without custom encoders.
- Startup identity hardening remains scoped to the existing startup test
  anchors for CLI startup, daemon ordering, standalone/federated
  persistence, and ASGI import persistence.

## Acceptance Criteria

1. Existing mood-mirror assertions remain green.
   VERIFY: `pytest tests/test_mood_mirror.py -q`

2. The depth gate confirms `tests/test_mood_mirror.py` reaches depth >= 2
   and contains `MoodMirrorEndToEndTests`.
   VERIFY: `pytest tests/test_test_mood_mirror_depth.py -q`

3. `MoodMirrorEndToEndTests` drives one meaningful public path through
   face expression, background colour, music params, art params, and a
   JSON-safe combined payload round trip.
   VERIFY: `pytest tests/test_mood_mirror.py::MoodMirrorEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0090 mood-mirror test
   deepening.
   VERIFY: `grep -n "frac-0090" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
