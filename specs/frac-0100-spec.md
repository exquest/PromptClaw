# Task frac-0100 Specification: test_pareidolia_characters Depth 2

## Problem Statement

`tests/test_pareidolia_characters.py` covers the PARE-003 organism character
draw functions at focused level: each of the 21 character draw functions
renders without error on a fresh RGBA canvas, produces non-empty image data,
the `CHARACTER_REGISTRY` exposes every primary name and the documented `the …`
aliases, and `render_panel`/`render_scene` dispatch registered characters and
fall back to `draw_character` for unknown names.

The missing frac-0100 work is to make the depth-2 contract explicit for this
test module. The production module
`my-claw/tools/senseweave/pareidolia.py` already exposes the simple one-path
implementation the task asks for: each public character draw function is
typed, deterministic, produces meaningful image output, and the panel/scene
renderers dispatch them end-to-end. This task therefore deepens the test
surface with a deterministic depth gate plus one end-to-end class that drives
the existing public pareidolia character surface through a complete
sensors → voices → outputs → bridges scene composition flow that exercises
the registry, palette selection, panel rendering, scene rendering, and
JSON-safe diagnostics.

The generated startup identity hardening bullets target the existing identity
startup subsystem. This checkout already wires `bootstrap_identity()` into
the CLI/narrative startup paths and both daemon startup order checks, with
standalone/federated persistence covered by regression tests. This task keeps
those tests as mandatory hardening anchors rather than changing unrelated
startup code without a discovered gap.

## Technical Approach

- Add `tests/test_test_pareidolia_characters_depth.py` with a deterministic
  depth gate requiring `tests/test_pareidolia_characters.py` to contain
  `PareidoliaCharactersEndToEndTests` and classify at depth >= 2 through the
  repo-local `sdp.fractal.classify_depth`.
- Confirm the red phase by running the new depth gate before
  `PareidoliaCharactersEndToEndTests` exists.
- Append `PareidoliaCharactersEndToEndTests` to
  `tests/test_pareidolia_characters.py` without modifying existing locked
  assertions.
- Drive one meaningful pareidolia character lifecycle inside the class:
  - select a palette via `select_palette(hour=10, mood="happy")` so the test
    exercises the public palette selector and pins a known palette
    (`PALETTES["day_happy"]`);
  - render a `PanelSpec` whose `characters` list covers one character from
    each of the four organism groups (sensors / voices / outputs / bridges)
    with distinct expressions, plus a `the …` alias name to confirm registry
    aliasing flows through `render_panel`;
  - render a full `render_scene(...)` with one `SceneCharacter` per group
    plus an unknown name to confirm the registry-miss fallback path and a
    `WeatherEffects` configuration that activates clouds, sun, and stars;
  - call each of the four chosen character draw functions directly on a fresh
    canvas to confirm the registry maps each name to the expected drawer;
  - serialize a combined diagnostic payload (palette key, registry-resolved
    drawer names per group, panel and scene image sizes/modes, character
    counts, alias verifications) through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve existing production behavior unless the red tests expose a concrete
  gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- The end-to-end path intentionally covers one happy multi-group scene
  composition flow. Existing focused tests continue to own per-character
  fresh-canvas rendering, expression coverage, small/large size rendering,
  visual distinctness, alias coverage, and the registry-miss fallback per
  character.
- Diagnostics convert PIL image objects to primitive JSON-safe values (size
  tuple, mode string) and use registry-resolved function names so operator
  surfaces can persist the summary without custom encoders.
- Startup identity hardening remains covered by the existing CLI, first-boot,
  daemon-ordering, and narrative ASGI tests; this task does not change identity
  startup wiring.

## Acceptance Criteria

1. Existing pareidolia-character regression assertions remain green.
   VERIFY: `pytest tests/test_pareidolia_characters.py -q`

2. The depth gate confirms `tests/test_pareidolia_characters.py` reaches
   depth >= 2 and contains `PareidoliaCharactersEndToEndTests`.
   VERIFY: `pytest tests/test_test_pareidolia_characters_depth.py -q`

3. `PareidoliaCharactersEndToEndTests` drives one meaningful pareidolia
   character flow through palette selection, registry-driven panel
   rendering, scene rendering with an unknown-name fallback, direct draw
   function calls per organism group, and JSON-safe diagnostics.
   VERIFY: `pytest tests/test_pareidolia_characters.py::PareidoliaCharactersEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon startup
   ordering, standalone/federated identity persistence, and narrative ASGI
   import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Full validation gate is green.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
