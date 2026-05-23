# Task T-048a: Morph Phrase Request Schema

## Problem Statement

T-047 added the `morph_voice` SuperCollider SynthDef and its crossfade controls,
but callers do not yet have a typed composer API contract for asking the
composer to morph a phrase from one CypherClaw voice to another. Without a
schema, malformed requests can reach downstream composer or synthesis code with
unknown voices, self-morphs, or unsupported curve names.

T-048a is the validation/API slice only. It defines the request/response schema
for a morph phrase request with `source_voice`, `target_voice`, and
`morph_curve_type`, and adds endpoint validation. Later T-048 subtasks can wire
accepted requests into phrase rendering or live playback.

## Technical Approach

- Add a packaged `cypherclaw.composer_api` FastAPI factory following the
  existing `image_api` and `narrative_api` `create_app(...)` pattern.
- Add Pydantic schemas in `cypherclaw.composer_api.schemas`:
  - `MorphPhraseRequest`
  - `MorphPhraseResponse`
  - `MorphCurveType`
- Use `cypherclaw.space_reverb.VOICE_REVERB_PROFILES` as the canonical supported
  voice set for `source_voice` and `target_voice`.
- Normalize voice aliases by trimming, lowercasing, and accepting `sw_`-prefixed
  SynthDef names such as `sw_pluck` as their canonical profile names.
- Reject unknown voices instead of silently falling back; the composer API is a
  validation boundary, not the forgiving live-render fallback.
- Reject requests where `source_voice == target_voice`.
- Normalize curve aliases to the two curves currently supported by
  `morph_voice.scd`: `linear` and `equal-power`; accept `equal_power` and
  `equal power` as aliases for `equal-power`.
- Return a normalized response containing `accepted=True`, canonical source and
  target voices, the canonical curve type, the numeric SuperCollider
  `morph_curve` value (`0` for `linear`, `1` for `equal-power`), and the route's
  `synthdef_name` (`morph_voice`).

## Edge Cases

- Blank `source_voice`, `target_voice`, or `morph_curve_type` values fail with
  HTTP 422 through schema validation.
- Unknown voices fail with HTTP 422 and include the field name in the validation
  error path.
- Source and target voices that normalize to the same canonical voice fail with
  HTTP 422.
- Extra request fields fail because the schema forbids unknown keys.
- Curve aliases normalize to canonical values; unsupported curve names fail.
- The endpoint has no synthesis, queue, database, or runtime-state side effects.
- No database schema changes are introduced, so no migration or FK index is
  required.
- No new dependencies, provider secrets, agent commands, SuperCollider source
  changes, or startup-flow changes are required.
- Mandatory hardening: existing voice SynthDefs must continue declaring
  `fx_bus_id`, and `sw_sampler.scd` must continue using `fx_bus_id` instead of
  the legacy `fx_bus` control.

## Acceptance Criteria

1. `MorphPhraseRequest` normalizes valid voices and curve aliases while exposing
   a JSON-safe response with the numeric SuperCollider curve value.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_schema_normalizes_voice_and_curve_aliases -q`

2. The schema rejects unknown source/target voices, unsupported curve names,
   blank strings, and same-voice morph requests.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_schema_rejects_invalid_payloads -q`

3. `POST /api/v1/composer/morph-phrase` returns `202 Accepted` with canonical
   fields for a valid request and has no side effects beyond validation.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_accepts_valid_request -q`

4. The composer API endpoint returns `422` for invalid payloads, including extra
   fields and source/target voices that normalize to the same value.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_rejects_invalid_requests -q`

5. The request schema exports the canonical voice and curve vocabulary for
   diagnostics.
   VERIFY: `pytest tests/test_composer_api.py::test_morph_phrase_schema_exports_supported_vocabularies -q`

6. Existing SuperCollider routing hardening remains green: all profiled voice
   SynthDefs declare `fx_bus_id`, and `sw_sampler.scd` routes through
   `fx_bus_id` with the sampler default bus.
   VERIFY: `pytest tests/test_space_reverb_profiles.py::test_voice_synthdefs_declare_fx_bus_id_routing_contract tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_send_writes_to_fx_bus tests/test_sw_sampler.py::TestRoutingAndFxSend::test_fx_bus_default_is_sampler_bus -q`

7. Task documentation and status mention T-048a, morph phrase validation, no
   migration, no new dependencies, and the hardening checks.
   VERIFY: `rg -n "T-048a|morph phrase|No new dependencies|No database|fx_bus_id|sw_sampler" specs/t-048a-spec.md CHANGELOG.md progress.md ESCALATIONS.md`

8. Required final validation passes.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
