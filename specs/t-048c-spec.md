# Task T-048c: Composer Morph Phrase Generation

## Problem Statement

T-048a added a validation-only composer API contract for morph phrase requests,
and T-048b added composer-side curve helpers for turning normalized phrase
positions into deterministic `morph_x` values. The FastAPI request handler still
does not generate a single-line morph phrase from a validated source/target
voice pair and phrase curve. Without that wiring, callers can validate a morph
request but cannot receive the endpoint-inclusive control frames needed by later
OSC scheduling.

## Technical Approach

- Preserve the locked T-048a behavior: requests containing only
  `source_voice`, `target_voice`, and `morph_curve_type` continue to return the
  existing validation response.
- Extend `MorphPhraseRequest` with optional phrase-generation fields:
  - `phrase_curve`: composer-side progression curve using
    `cypherclaw.instrument_morph.MorphInterpolationCurve`
    (`linear`, `exponential`, `sigmoid`).
  - `phrase_frame_count`: endpoint-inclusive frame count, defaulting to `5`
    when phrase generation is requested and requiring at least two frames.
- When `phrase_curve` is present, the `/api/v1/composer/morph-phrase` handler
  returns a generated response containing `single_line_phrase`.
- Build each phrase frame from the normalized source/target voices, the
  requested phrase curve, and the existing T-048a SuperCollider
  `morph_curve_value` (`0` for linear gain law, `1` for equal-power gain law).
- Each generated frame carries:
  - `frame_index`
  - normalized `position`
  - curved `morph_x`
  - `synthdef_name`
  - `control_args` suitable for the later OSC scheduler:
    `["morph_x", value, "morph_curve", morph_curve_value]`
- Keep the two curve layers separate:
  - `morph_curve_type` remains the `morph_voice.scd` gain-law selector.
  - `phrase_curve` is the composer-side progression curve used to compute
    `morph_x`.
- Add no database schema, migration, dependency, provider secret, runtime state
  directory, startup-flow, or SuperCollider source change.
- Mandatory hardening: keep the existing `fx_bus_id` and `sw_sampler.scd`
  routing anchors green.

## Edge Cases

- Requests without `phrase_curve` remain validation-only and do not include
  generated phrase fields.
- `phrase_curve` aliases normalize through the T-048b helper; unsupported
  curves fail with HTTP 422.
- `phrase_frame_count < 2` fails with HTTP 422.
- Phrase endpoints preserve exact `morph_x` endpoints: first frame is `0.0`,
  last frame is `1.0`.
- Generated positions are deterministic and endpoint-inclusive.
- Unknown voices, self-morphs, unsupported gain-law curve types, blank strings,
  and extra unknown fields remain rejected by the T-048a validation boundary.
- Generated frame `control_args` use the numeric SuperCollider gain-law value,
  not the phrase-curve enum.
- No new dependency or migration is required.

## Acceptance Criteria

1. The composer endpoint generates a `single_line_phrase` when a valid request
   includes `phrase_curve`, using normalized voices, requested frame count,
   requested phrase curve, exact endpoints, and the numeric `morph_curve` gain
   law in every frame's control args.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_generates_single_line_phrase_from_voice_pair_and_phrase_curve -q`

2. The composer endpoint rejects invalid phrase-generation fields clearly:
   unsupported `phrase_curve` values and `phrase_frame_count < 2` return HTTP
   422.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_rejects_invalid_phrase_generation_fields -q`

3. Existing T-048a validation-only behavior remains compatible when
   `phrase_curve` is omitted.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_accepts_valid_request -q`

4. Existing T-048b interpolation helpers remain compatible with the generated
   phrase path.
   VERIFY: `pytest tests/test_instrument_morph_curves.py -q`

5. Existing SuperCollider routing hardening remains green: all profiled voice
   SynthDefs declare `fx_bus_id`, and `sw_sampler.scd` routes through
   `fx_bus_id` with the sampler default bus.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

6. Task documentation and status mention T-048c, single-line morph phrase
   generation, no migration, no new dependencies, the two curve layers, and the
   `fx_bus_id` / `sw_sampler.scd` hardening checks.
   VERIFY: `rg -n "T-048c|single-line morph phrase|No new dependencies|No database|phrase_curve|morph_curve_type|fx_bus_id|sw_sampler" specs/t-048c-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

7. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
