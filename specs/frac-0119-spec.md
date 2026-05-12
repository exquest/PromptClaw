# Task frac-0119 Specification: test_theramini_duet Depth 2

## Problem Statement

`tests/test_theramini_duet.py` covers the SenseWeave Theramini duet
intelligence implemented in `my-claw/tools/senseweave/theramini_duet.py` at
focused helper depth: `suggest_response_key`, `suggest_response_register`,
`suggest_response_density`, `suggest_response_phrase`, `calculate_wait_beats`,
`should_enter_duet`, `should_exit_duet`, plus a slice of conversation-protocol
behaviors via `normalize_theramini_state` and `plan_duet_response`.

Missing depth-2 coverage is a single realistic end-to-end test path that
proves the public Theramini duet surface produces meaningful operator-facing
output across the full lifecycle:

1. an active human gesture (Theramini playing with confident pitch and
   onset rate) flows through `normalize_theramini_state(...)` to expose the
   shared listening contract (`listening`, `speaking`, `silence_request`,
   `human_gesture_active`, `conversation`),
2. `plan_duet_response(...)` for that same active state yields a
   `ConversationDecision` whose phase is `"listening"`, policy is
   `"turn_taking"`, speaker is `"human"`, `may_play` is `False`,
   `lead_role` is `"theramini"`, and `max_overlap_beats` is `0`,
3. once the human stops playing past the response delay,
   `plan_duet_response(...)` flips into `phase="speaking"` with
   `may_play=True`, `speaker="cypherclaw"`, `lead_role="cypherclaw"`, the
   `_requested_response_policy(...)` mapping holds (a `requested_policy`
   like `"call/response"` is normalized to `"call_response"`), and
   `harmonic_intervals` / `accompaniment_texture` / `response_register` /
   `rhythmic_sympathy` carry meaningful non-empty values,
4. the focused helpers agree with the speaking-phase decision:
   `suggest_response_key(440.0)` returns `("A", root_freq>0)`,
   `suggest_response_register(440.0)` returns `"low"` and matches
   `decision.response_register`, `suggest_response_density(1.0)` returns
   `"dense"`, `suggest_response_phrase(...)` returns a 3-6 note phrase
   with positive frequencies and durations, and
   `calculate_wait_beats(0, 0.5)` returns `0`,
5. a long-silence state past the solo inactivity threshold flips the
   decision to `phase="solo"` with `duet_active=False` and
   `should_exit_duet(...)` returns `True`,
6. `supported_partner_behaviors()` covers the documented ensemble-space
   behaviors (`listening_first`, `complementary_register`,
   `rhythmic_sympathy`, `harmonic_response_intervals`,
   `accompaniment_textures`, `call_response`, `imitation`, `commentary`,
   `completion`, `silence`),
7. a stable operator-style diagnostic captures the listening-phase
   normalized state, the speaking-phase decision payload via
   `ConversationDecision.to_dict()`, the solo-phase decision payload, the
   focused helper outputs, and the supported partner behaviors in
   JSON-safe form and round-trips through
   `json.dumps(..., sort_keys=True)` / `json.loads(...)`.

The production surface in `my-claw/tools/senseweave/theramini_duet.py`
already implements this one-path behavior. This task therefore deepens the
test surface unless the red tests expose a concrete source gap.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering, and
narrative ASGI tests already cover `bootstrap_identity()` before
`FirstBootAnnouncer` plus standalone/federated identity persistence. This
task keeps those tests as mandatory regression anchors rather than
changing unrelated startup code.

The active ADP process is the task prompt's Explore -> Specify -> Test ->
Implement -> Verify -> Document workflow.

## Technical Approach

- Add `tests/test_test_theramini_duet_depth.py` using the recent
  depth-gate pattern. The gate requires:
  - `TheraminiDuetEndToEndTests` exists in
    `tests/test_theramini_duet.py`;
  - the named method
    `test_theramini_duet_conversation_lifecycle_round_trips_json_diagnostic`
    exists;
  - `classify_depth("tests/test_theramini_duet.py").depth >= 2`;
  - the test module declares a machine-readable depth-2 marker either in
    the module docstring (`depth: 2`) or as a top-level `DEPTH = 2`
    constant.
- Confirm the red phase by running the new depth gate before the
  end-to-end class and marker exist.
- Extend `tests/test_theramini_duet.py` without modifying existing locked
  assertions:
  - add a `depth: 2` marker to the module docstring;
  - import `json` and `ConversationDecision`, `normalize_theramini_state`,
    and `plan_duet_response` (already imported);
  - append `TheraminiDuetEndToEndTests` with one deterministic
    conversation lifecycle test driving the listening, speaking, and solo
    phases plus the focused helper agreement and a JSON-safe diagnostic.
- The end-to-end test will:
  - build a deterministic listening-phase Theramini state (active human
    gesture, fresh timestamp, confident pitch at 440 Hz, onset rate 1.0)
    and assert `normalize_theramini_state(...)` exposes the shared
    listening contract and the listening `ConversationDecision`;
  - assert `plan_duet_response(...)` for that state produces
    `phase="listening"`, `policy="turn_taking"`, `speaker="human"`,
    `may_play=False`, `lead_role="theramini"`,
    `support_role="cypherclaw"`, and `max_overlap_beats=0`;
  - build a speaking-phase state (silence past the response delay, fresh
    timestamp, requested policy `"call/response"`) and assert
    `plan_duet_response(...)` produces `phase="speaking"`,
    `policy="call_response"`, `may_play=True`, `speaker="cypherclaw"`,
    `lead_role="cypherclaw"`, `support_role="theramini"`, a non-empty
    `harmonic_intervals`, an `accompaniment_texture` of
    `"answering_phrase"`, a non-empty `response_register`, and a
    non-empty `rhythmic_sympathy`;
  - assert the focused helpers agree with the speaking-phase decision:
    `suggest_response_key(440.0)` returns `("A", root>0)`,
    `suggest_response_register(440.0)` matches
    `decision.response_register`, `suggest_response_density(1.0)` returns
    `"dense"`, `suggest_response_phrase(...)` returns a 3-6 note phrase
    with positive frequencies and durations, and
    `calculate_wait_beats(0, 0.5)` returns `0`;
  - build a solo-phase state (long silence past the solo inactivity
    threshold, no pitch, fresh timestamp) and assert
    `plan_duet_response(...)` produces `phase="solo"`, `policy="solo"`,
    `may_play=False`, `duet_active=False`, and `should_exit_duet(...)`
    returns `True`;
  - assert `supported_partner_behaviors()` covers the documented
    ensemble-space behaviors;
  - build a primitive diagnostic of the listening-phase normalized state
    keys, the speaking-phase decision payload via
    `ConversationDecision.to_dict()`, the solo-phase decision payload,
    the focused helper outputs, and the supported partner behaviors and
    verify `json.loads(json.dumps(..., sort_keys=True))` round-trips it.
- Preserve production behavior unless the red tests reveal a runtime gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or auth behavior.

## Edge Cases

- This is intentionally one simple happy path for depth-2 coverage.
  Existing focused tests remain responsible for the malformed-state
  rejection paths, key/register/density boundary classes, custom-threshold
  exits, MIDI CC silence-request matrix, and per-policy explicit-policy
  enumeration.
- `suggest_response_phrase(...)` uses `random` internally. The end-to-end
  test asserts only structural invariants (length 3-6, positive
  frequencies and durations) so it remains hermetic without seeding
  global random state.
- The diagnostic payload only stores strings, booleans, ints, floats,
  lists, and nested dicts, so JSON serialization stays deterministic and
  hermetic.
- No database schema changes are introduced, so no migration or index
  work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the Theramini duet tests.

## Acceptance Criteria

1. Existing Theramini duet assertions remain green.
   VERIFY: `pytest tests/test_theramini_duet.py -q`

2. The depth gate confirms `tests/test_theramini_duet.py` reaches
   depth >= 2 and contains the named end-to-end class/method plus the
   machine-readable depth-2 marker.
   VERIFY: `pytest tests/test_test_theramini_duet_depth.py -q`

3. `TheraminiDuetEndToEndTests` drives the listening-phase
   normalization, listening / speaking / solo `plan_duet_response(...)`
   transitions, focused helper agreement, supported partner behaviors,
   and JSON-safe diagnostic round-trip.
   VERIFY: `pytest tests/test_theramini_duet.py::TheraminiDuetEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0119 Theramini duet test
   deepening with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0119" CHANGELOG.md progress.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
