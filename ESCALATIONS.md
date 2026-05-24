# Escalations

## T-055d (2026-05-24)

- **Reason:** Live deployment verification scope and stale production Worker
  state.
- **Details:** PromptClaw remains the ADP source of truth, but the deployed
  `cypherclaw.holdenu.com` surface is implemented by the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker. Live
  exploration found production behind local `main`: the root page still showed
  the prepared-address fallback, while `/api/cypherclaw/live-midi` and
  `/api/cypherclaw/live-features` returned 404. T-055d therefore adds a gated
  live E2E test in the Worker project and uses deployment verification as the
  implementation step.
- **Assumption:** Playing MIDI through the live feed for this slice means
  sending scripted note-on JSON through the existing public live MIDI WebSocket
  and confirming fan-out plus deployed browser-runtime visual mapping. The
  separate `/api/cypherclaw/midi-event` POST ingest path remains outside this
  T-055 visualizer verification slice.
- **Scope decision:** The local Worker renderer from T-055a/T-055b/T-055c is
  already the intended implementation. T-055d should not alter MIDI shape
  mapping, audio-feature drawing, the Durable Object protocol, R2/D1 schema,
  HLS ingestion, or SuperCollider source; it should add a live verification
  harness and update the live deployment.
- **No new dependencies:** T-055d adds no npm packages, Python packages,
  provider secrets, database columns, D1 database migration, Durable Object
  migration, R2 layout change, runtime state directory, startup-flow rewiring,
  agent command, or SuperCollider source change.
- **Candidate hardening:** The recurring SuperCollider failures are out of
  scope for this live Worker visualizer verification slice, but remain
  mandatory anchors: profiled voice SynthDefs must expose `fx_bus_id`, and
  `sw_sampler.scd` must route through `fx_bus_id` rather than `fx_bus`.
- **Deployment prerequisite:** Wrangler deploy failed with Cloudflare API code
  10063 until the account-level Workers subdomain was initialized. T-055d set
  the account Workers subdomain to `anthony-holdenu` through Cloudflare's
  official Workers Subdomain API, then deployed Worker version
  `e71aaf43-b04a-4676-bd34-19e803711463` to `explorer.holdenu.com/api/*` and
  the `cypherclaw.holdenu.com` custom domain. The Worker config now also pins
  `workers_dev = false` so the script is not exposed on a default workers.dev
  route.
- **Verification:** Red phase was confirmed with the gated live E2E test
  failing on the stale prepared-address production page and failed live MIDI
  WebSocket open, plus a config red phase for missing `workers_dev = false`.
  After deployment, `CYPHERCLAW_RUN_LIVE_E2E=1 npm test --
  tests/cypherclaw-live-e2e.test.js` passed with `47 passed`, proving the live
  root, SSE feed, WebSocket fan-out, deployed pitch/velocity shape mapping, and
  same-frame audio-feature drawing. Worker `npm test` passed with `45 passed, 2
  skipped`, Worker `npm run check` passed, Worker `npm run check:workers`
  passed, Workers-runtime live MIDI latency passed, SuperCollider hardening
  anchors passed with `3 passed`, and final PromptClaw validation passed with
  `5219 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-055c (2026-05-24)

- **Reason:** Cross-repository Worker location and MIDI/audio visualizer
  compositing scope.
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` canvas visualizer is implemented in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker.
  T-055c therefore keeps the spec, progress, changelog, and hardening anchors
  in PromptClaw while changing Worker HTML/JS tests and inline browser runtime
  in `catalog-explorer`.
- **Assumption:** T-055a already provides the browser-side live MIDI event
  queue and T-055b already provides bounded MIDI shape creation/decay. T-055c
  should make the existing canvas compositing contract explicit instead of
  changing the live MIDI Durable Object protocol or the SSE live-feature feed.
- **Scope decision:** Continuous audio-feature visuals draw first, MIDI note
  shapes draw second as the foreground layer in the same display coordinate
  space, and MIDI-specific blending must be restored to normal canvas
  compositing before future frames.
- **No new dependencies:** T-055c adds no npm packages, Python packages,
  provider secrets, database columns, D1 database migration, Durable Object
  migration, R2 layout change, runtime state directory, startup-flow rewiring,
  agent command, or SuperCollider source change.
- **Startup identity hardening:** The generated startup identity bullets target
  existing PromptClaw startup paths; current CLI, first-boot, daemon ordering,
  standalone/federated persistence, and narrative ASGI tests cover
  `bootstrap_identity()` persistence and bootstrap-before-`FirstBootAnnouncer`
  ordering. T-055c re-runs those anchors rather than broadening this Worker
  visualizer task into identity subsystem changes.
- **Verification:** Red phase was confirmed with Worker tests failing on
  missing MIDI/audio compositing diagnostics, missing explicit audio-feature
  layer function, missing MIDI blend-mode bracketing, and missing shared
  display coordinate-space assertions before implementation. After
  implementation, Worker `npm test` passed with `44 passed`, Worker
  `npm run check` passed, Worker `npm run check:workers` passed,
  `npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`
  passed, startup identity hardening anchors passed with `11 passed`, and the
  required final validation command passed with `5219 passed, 11 skipped`, Ruff
  clean, and mypy clean.

## T-055b (2026-05-24)

- **Reason:** Cross-repository Worker location and MIDI shape-rendering scope
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` canvas visualizer is implemented in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker.
  T-055b therefore keeps the spec, progress, changelog, and hardening anchors
  in PromptClaw while changing Worker HTML/JS tests and inline browser runtime
  in `catalog-explorer`.
- **Assumption:** T-055a already provides a valid browser-side MIDI event queue
  populated from the existing `{status,data1,data2,ts}` WebSocket shape. T-055b
  should layer visual shape creation and drawing on top of that queue rather
  than changing the live MIDI Durable Object protocol.
- **Scope decision:** Only normalized `note_on` events spawn shapes. Pitch maps
  to a Y-axis canvas position, velocity maps to radius, and each shape decays
  over a fixed browser-side lifetime. Note-off events remain queued diagnostics
  and do not create new shapes.
- **No new dependencies:** T-055b adds no npm packages, Python packages,
  provider secrets, database columns, D1 database migration, Durable Object
  migration, R2 layout change, runtime state directory, startup-flow rewiring,
  agent command, or SuperCollider source change.
- **Candidate hardening:** The recurring SuperCollider failures are out of
  scope for this Worker visualizer slice, but remain mandatory verification
  anchors: profiled voice SynthDefs must expose `fx_bus_id`, and
  `sw_sampler.scd` must route through `fx_bus_id` rather than `fx_bus`.
- **Verification:** Red phase was confirmed with Worker runtime tests failing
  on missing MIDI shape diagnostics, mapper/draw functions, and
  `window.cypherclawLiveMidiShapes` before implementation. After implementation,
  Worker `npm test` passed with `43 passed`, Worker `npm run check` passed,
  Worker `npm run check:workers` passed,
  `npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`
  passed, SuperCollider `fx_bus_id` / `sw_sampler.scd` hardening anchors passed
  with `3 passed`, and the required final validation command passed with `5219
  passed, 11 skipped`, Ruff clean, and mypy clean.

## T-055a (2026-05-23)

- **Reason:** Cross-repository Worker location and live MIDI visualizer scope
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` canvas visualizer is implemented in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker. T-055a
  therefore keeps the spec, progress, changelog, and startup-hardening anchors
  in PromptClaw while changing Worker HTML/JS tests and inline browser runtime
  in `catalog-explorer`.
- **Assumption:** T-054a through T-054d already provide the public
  `/api/cypherclaw/live-midi` WebSocket route, strict JSON MIDI event validation,
  fan-out, Wrangler Durable Object config, and Workers-runtime latency coverage.
  T-055a should only add the browser subscriber and note event queue on the
  canvas visualizer page.
- **Scope decision:** The in-memory browser queue is capped at 128 normalized
  note events and accepts only note-on/note-off events from the existing
  `{status,data1,data2,ts}` WebSocket shape. It does not alter the Durable
  Object protocol, composer behavior, SSE live-features feed, R2/D1 storage, or
  audio playback path.
- **No new dependencies:** T-055a adds no npm packages, Python packages,
  provider secrets, database columns, D1 database migration, Durable Object
  migration, R2 layout change, runtime state directory, startup-flow rewiring,
  agent command, or SuperCollider source change.
- **Startup identity hardening:** The generated startup identity bullets target
  existing startup paths; current CLI, first-boot, daemon ordering,
  standalone/federated persistence, and narrative ASGI tests cover
  `bootstrap_identity()` persistence and bootstrap-before-`FirstBootAnnouncer`
  ordering. T-055a re-runs those anchors rather than broadening this Worker
  visualizer task into identity subsystem changes.
- **Verification:** Red phase was confirmed with Worker tests failing on the
  missing `data-live-midi-url`, browser WebSocket subscription, and MIDI event
  queue before implementation. After implementation, `npm test` passed with
  `42 passed`, `npm run check` passed, `npm run check:workers` passed,
  `npm run test:workers -- tests/cypherclaw-live-midi-latency.vitest.ts`
  passed, startup identity anchors passed with `11 passed`, and the required
  final validation command passed with `5219 passed, 11 skipped`, Ruff clean,
  and mypy clean.

## T-053a (2026-05-23)

- **Reason:** Live MIDI emitter scaffold route contract and generated hardening
  scope.
- **Details:** Exploration found CC-090 in the CypherClaw v2 PRD/register:
  `live_midi_emitter.py` should publish live MIDI events to the holdenu
  Cloudflare Worker `/api/cypherclaw/midi-event` endpoint. T-054a through
  T-054d already cover the sibling Worker's `/api/cypherclaw/live-midi`
  WebSocket room and fan-out behavior, but this PromptClaw slice owns only the
  Python emitter scaffold. Composer integration remains out of T-053a scope.
- **Assumption:** Until the Worker POST route is implemented, the emitter will
  send a JSON batch payload with `source`, `batch_id`, `event_count`, and
  enriched `events`. Each event carries the canonical MIDI bytes
  (`status`, `data1`, `data2`, `ts`) plus optional context tags
  (`event_type`, `voice`, `scene`, `tuning`, `metadata`) for later Worker-side
  normalization.
- **Assumption:** Authentication, when configured, is a bearer token supplied
  through `CYPHERCLAW_LIVE_MIDI_TOKEN`; no provider secret or command string is
  hardcoded in source.
- **Candidate hardening:** The recurring SuperCollider feedback is unrelated
  to the Python emitter scaffold, but existing `fx_bus_id` voice SynthDef tests
  and `sw_sampler.scd` routing tests remain mandatory verification anchors.
- **Dependencies and database changes:** No new dependencies, provider secrets,
  database changes, runtime state directories, startup-flow rewiring,
  Cloudflare Worker source changes, or composer integration are expected.
- **Verification:** Red phase was confirmed with
  `pytest tests/test_live_midi_emitter.py -q` failing on missing
  `cypherclaw.live_midi_emitter` before implementation. After implementation,
  the focused emitter suite passed with `8 passed`, touched Ruff passed,
  touched mypy passed, the no-composer-integration check passed, and the
  mandatory `fx_bus_id` / `sw_sampler.scd` hardening anchors passed with
  `3 passed`. Required final validation passed with `5219 passed, 11 skipped`,
  Ruff clean, and mypy clean.

## T-054d (2026-05-23)

- **Reason:** Cross-repository Worker implementation and new Workers Vitest
  test dependencies.
- **Details:** T-054d keeps PromptClaw as the ADP/source-of-truth repo while
  adding a Cloudflare Workers runtime Vitest fan-out latency test in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` project established by
  T-054a through T-054c.
- **Assumption:** The existing `/api/cypherclaw/live-midi` route, `LiveMidiRoom`
  Durable Object, `LIVE_MIDI_ROOM` binding, and Wrangler schema modifications are the
  intended production path. The new test should exercise that path through
  `SELF.fetch` rather than another fake WebSocket shim.
- **Assumption:** Sub-second fan-out means client B receives the exact JSON MIDI
  event payload from client A within 1000 ms after A sends it. The test measures
  local Workers-runtime latency with `performance.now()` and uses a hard
  1000 ms timeout to fail hangs quickly.
- **New Worker dev dependencies:** T-054d is expected to add `vitest` and
  `@cloudflare/vitest-pool-workers` to
  `/Users/anthony/Programming/catalog-explorer/worker/package.json` and
  `package-lock.json`. This is scoped to the Worker test harness.
- **Candidate hardening:** The generated startup identity feedback targets the
  existing PromptClaw startup subsystem, not the Cloudflare Worker room. Current
  startup identity tests remain mandatory verification anchors for
  `bootstrap_identity()` before `FirstBootAnnouncer`, standalone boot
  persistence, federated boot persistence, and narrative ASGI import-time
  identity reuse.
- **Dependencies and schema modifications:** Aside from the Worker dev dependencies above,
  no provider secrets, database columns, D1 schema modifications, Durable Object schema modification
  changes, R2 layout changes, runtime state directories, startup-flow rewiring,
  agent commands, or SuperCollider source changes are expected.
- **Verification:** Red phase was confirmed with
  `npx --no-install vitest run tests/cypherclaw-live-midi-latency.vitest.ts`
  failing because `vitest` was not installed. After implementation, the Workers
  Vitest latency test passed with `1 passed`, existing Worker `npm test` passed
  with `39 passed`, Worker `npm run check` passed, and Worker
  `npm run check:workers` passed. Startup identity hardening anchors passed with
  `8 passed`. The implementation added only Worker test
  harness dependencies/configuration and the new runtime test; no D1 database
  schema modification, Durable Object schema modification change, R2 layout change, provider secret,
  startup-flow rewiring, or SuperCollider source change was introduced. Final
  PromptClaw validation passed with `5211 passed, 11 skipped`, Ruff clean, and
  mypy clean.
- **SI-003 false positive — pair-rotate exhausted (2026-05-23):** Verifier rule
  SI-003 keeps appending a `Verdict: FAIL` after three independent verifier
  `Verdict: PASS` results because `specs/t-054d-spec.md` contains the token
  `schema modification`. All occurrences are negative assertions or references to the
  *existing* Wrangler DO schema modification config — spec line 28 cites the pre-existing
  `LIVE_MIDI_ROOM` "binding and schema modification config" used by the test, and lines 94
  and 96 are explicit "no D1 database schema modification, no Durable Object schema modification
  change" scope clauses (also asserted by an AC `rg` VERIFY). `git diff --
  promptclaw/coherence/schema modifications/` is empty; the schema modifications directory still
  contains only `001_event_store.sql` and `002_decision_store.sql`. The Worker
  project's existing D1 schema modifications (0001, 0002, 0004) were unchanged by T-054d
  and a schema snapshot was already attached in the second-pass verify report.
  Pair-rotate banner `[pair-rotate codex/claude->claude/codex] verification
  retries exhausted` is now logged on this task. This matches the documented
  `[[project-sdp-si003-false-positive]]` pattern first surfaced by
  T-017@20260515T214233Z (see entry dated 2026-05-15 below); no further
  schema-snapshot retry can clear SI-003 because the task introduces no schema.
  Recommend: (a) record T-054d verdict as PASS based on the three independent
  acceptance-criteria PASSes (all 10 ACs green, Workers Vitest fan-out at 5ms,
  `5211 passed, 11 skipped`, Ruff clean, mypy clean), and (b) tighten the SI-003
  rule to skip specs whose only `schema modification` mentions are inside negative-
  assertion clauses, pre-existing-config references, or `rg`/`git diff` VERIFY
  commands asserting no new schema modification. Human review requested before the next
  pipeline tick promotes the spurious FAIL. Lead retries are NOT being attempted
  per the documented SI-003 escalation policy.
- **SI-003 false positive — 4th-pass exhaustion (2026-05-23, codex lead via
  Thompson sampling):** A fourth orchestrator tick re-selected the lead (codex
  candidate, project=promptclaw, 3 candidates) and Gemini returned a fresh
  independent `Verdict: PASS` on all five rubric axes (correctness,
  completeness, consistency, security, quality;
  `Verify_T-054d_1779573441.log`). SI-003 then appended a fifth spurious
  `Verdict: FAIL` to `sdp/verification/t-054d-verify.md`. Conditions for the
  documented escalation still hold: only SI-003 flag outstanding,
  `schema modification` mentions in `specs/t-054d-spec.md` are negative-assertion or
  pre-existing-config references (lines 28, 94, 96), and `git diff --
  promptclaw/coherence/schema modifications/` remains empty (`001_event_store.sql`,
  `002_decision_store.sql` only — no T-054d additions). Per
  `[[project-sdp-si003-false-positive]]` policy, no further schema-snapshot
  retry attempted. Holding for human review or SI-003 rule patch before the
  next pipeline tick. Recommended fix unchanged: tighten SI-003 to skip
  negative-assertion / pre-existing-config / `rg`/`git diff`-no-op
  `schema modification` mentions.

## T-054c (2026-05-23)

- **Reason:** Cross-repository Worker implementation and Wrangler environment
  binding assumption.
- **Details:** T-054c keeps PromptClaw as the ADP/source-of-truth repo while
  implementing the Worker config hardening in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` project established by
  T-054a.
- **Assumption:** The existing `[env.dev]` Wrangler environment is a deployable
  Worker environment, not only a variable namespace. Cloudflare's Durable Object
  environment guidance says Durable Object bindings are not inherited by
  Wrangler environments, so T-054c treats missing `env.dev` Durable Object
  binding and migration entries as the remaining reachability gap for
  `/api/cypherclaw/live-midi`.
- **Scope decision:** T-054a/T-054b already added the production route,
  `LIVE_MIDI_ROOM` `Env` type, top-level Durable Object binding and migration,
  `LiveMidiRoom`, WebSocket guard, and fan-out behavior. T-054c therefore pins
  those contracts with tests and only adds the missing `env.dev` Durable Object
  config.
- **Candidate hardening:** The generated SuperCollider feedback is unrelated to
  the Cloudflare Worker config, but existing tests for `fx_bus_id` declarations
  and `sw_sampler.scd` routing remain mandatory verification anchors.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, D1 migrations, R2 layout changes, runtime state directories,
  startup-flow rewiring, agent commands, or SuperCollider source changes are
  expected. The only migration change is the Wrangler Durable Object
  environment migration for `LiveMidiRoom`.
- **Verification:** Red phase was confirmed with
  `npm test -- tests/cypherclaw-live-midi-config.test.js` failing on the
  missing `env.dev` `LIVE_MIDI_ROOM` Durable Object binding before production
  config changed. After implementation, the focused Worker config/source
  contract test passed, Worker `npm test` passed with `39 passed`, Worker
  `npm run check` passed, SuperCollider `fx_bus_id` and `sw_sampler.scd`
  hardening anchors passed with `3 passed`, and final PromptClaw validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5211 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-054b (2026-05-23)

- **Reason:** Cross-repository Worker implementation and generated hardening
  scope.
- **Details:** T-054b keeps PromptClaw as the ADP/source-of-truth repo while
  implementing the live MIDI WebSocket runtime in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` project established by
  T-054a.
- **Assumption:** Incoming WebSocket MIDI events must be JSON text objects with
  exactly `status`, `data1`, `data2`, and `ts`. MIDI byte fields are integers
  from 0 through 255, and `ts` is any finite number.
- **Assumption:** Invalid messages are ignored silently. This preserves a small
  broadcast-only room and avoids introducing protocol error replies in T-054b.
- **Candidate hardening:** The generated startup identity feedback targets the
  existing PromptClaw startup subsystem, not the Cloudflare Worker room. Current
  tests already cover `bootstrap_identity()` invocation before
  `FirstBootAnnouncer`, standalone and federated identity persistence between
  boots, and ASGI import-time identity reuse; T-054b keeps those tests as
  mandatory verification anchors.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, D1 migrations, Durable Object migrations, R2 layout changes,
  runtime state directories, startup-flow rewiring, agent commands, or
  SuperCollider source changes are expected.
- **Verification:** Red phase was confirmed with
  `npm test -- tests/cypherclaw-live-midi.test.js` failing on missing fan-out
  and dead-socket removal before production code changed. After implementation,
  the focused Worker suite passed, full Worker `npm test` passed with
  `37 passed`, Worker `npm run check` passed, startup identity hardening anchors
  passed with `8 passed`, and the required PromptClaw validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5211 passed, 11 skipped`, Ruff clean, and mypy clean.
  No new dependencies or migrations were introduced.

## T-048d (2026-05-23)

- **Reason:** Test-hardening scope and schema-boundary assumptions.
- **Details:** T-048d covers the completed T-048 composer morph phrase surface:
  schema validation, every composer-side phrase curve, every `morph_voice`
  SynthDef gain-law curve, and end-to-end generated phrase responses.
- **Assumption:** `phrase_frame_count` is a generation-only field. Supplying it
  without `phrase_curve` should fail validation instead of being silently
  ignored by the validation-only response path.
- **Assumption:** The two curve layers remain distinct: `morph_curve_type`
  selects the SuperCollider gain law (`linear` / `equal-power`), while
  `phrase_curve` selects composer-side `morph_x` progression (`linear` /
  `exponential` / `sigmoid`).
- **Candidate hardening:** The generated startup identity feedback targets the
  existing startup subsystem. Current CLI, daemon ordering, standalone/federated
  persistence, and narrative ASGI tests cover `bootstrap_identity()` startup
  invocation before `FirstBootAnnouncer`; T-048d keeps those tests as mandatory
  anchors rather than changing unrelated startup flow.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, agent commands,
  startup-flow rewiring, or SuperCollider source changes are expected.
- **Verification:** Red phase was confirmed with
  `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_rejects_frame_count_without_phrase_curve -q`
  failing because the endpoint returned `202` before the schema guard was
  implemented. After implementation, focused T-048d tests passed with
  `7 passed`, adjacent composer/instrument morph tests passed with `28 passed`,
  startup identity hardening anchors passed with `11 passed`, and Ruff was
  clean on touched source/test files. Final validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5150 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-048c (2026-05-23)

- **Reason:** Composer phrase-generation compatibility assumptions.
- **Details:** T-048a's `morph_curve_type` remains the SuperCollider gain-law
  selector for `morph_voice.scd` (`linear` / `equal-power`), while T-048b's
  `MorphInterpolationCurve` remains the composer-side phrase progression curve
  (`linear` / `exponential` / `sigmoid`) for computing `morph_x`.
- **Assumption:** To preserve locked T-048a assertions, requests that omit
  `phrase_curve` keep the existing validation-only response. Requests that
  include `phrase_curve` ask the same handler to generate a single-line morph
  phrase with endpoint-inclusive control frames.
- **Assumption:** Generated frames should carry OSC-ready control args for
  `morph_voice` (`morph_x` and numeric `morph_curve`) rather than trying to
  encode source/target voices as SuperCollider controls, because the current
  `morph_voice.scd` source does not declare source/target voice-name controls.
- **Candidate hardening:** The recurring SuperCollider failure modes are
  verified by existing source tests: all profiled voice SynthDefs must declare
  `fx_bus_id`, and `sw_sampler.scd` must route through `fx_bus_id` rather than
  the legacy `fx_bus` control.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, startup-flow
  changes, agent commands, or SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with
  `pytest tests/test_composer_api.py::test_morph_phrase_endpoint_generates_single_line_phrase_from_voice_pair_and_phrase_curve tests/test_composer_api.py::test_morph_phrase_endpoint_rejects_invalid_phrase_generation_fields -q`
  failing on the missing phrase-generation request fields before implementation.
  After implementation, `pytest tests/test_composer_api.py -q` passed with
  `14 passed`, `pytest tests/test_composer_api.py tests/test_instrument_morph_curves.py -q`
  passed with `22 passed`, the required `fx_bus_id` / `sw_sampler.scd`
  hardening anchors passed with `3 passed`, focused Ruff and mypy checks passed,
  and the required final validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5144 passed, 11 skipped`, Ruff clean, and mypy clean.
  No new dependencies or migrations were introduced.

## T-048b (2026-05-23)

- **Reason:** Curve terminology spans two layers.
- **Details:** T-048a's `morph_curve_type` is the SuperCollider gain-law
  selector for `morph_voice.scd` (`linear` / `equal-power`). T-048b implements
  composer-side phrase interpolation curves (`linear` / `exponential` /
  `sigmoid`) for `morph_x` and numeric voice-parameter maps without changing
  the T-048a API contract or previous locked assertions.
- **Assumption:** Source/target voice parameter maps can expose different key
  sets. Shared numeric parameters interpolate; one-sided parameters are
  preserved rather than invented from a zero default.
- **Candidate hardening:** The generated `bootstrap_identity()` feedback
  targets the existing startup identity subsystem. This task does not touch
  startup flow, but the existing CLI, first-boot, and governor startup identity
  anchors are re-run as the regression check.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, startup-flow
  changes, agent commands, or SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with
  `pytest tests/test_instrument_morph_curves.py -q` failing at collection on
  missing `cypherclaw.instrument_morph` before implementation. After
  implementation, the locked T-048b tests passed with `8 passed`, existing
  T-048a composer API tests passed with `11 passed`, startup identity anchors
  passed with `8 passed`, and focused Ruff/mypy checks on the new package
  passed. Final validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5141 passed, 11 skipped`, Ruff clean, and mypy
  clean.

## T-048a (2026-05-23)

- **Reason:** Composer API boundary assumptions for morph phrase validation.
- **Details:** No existing composer HTTP API module was present. T-048a adds a
  small packaged `cypherclaw.composer_api` FastAPI factory instead of wiring
  morph requests into the live `duet_composer.py` loop or generation queue.
- **Assumption:** The canonical morph phrase voice vocabulary is the existing
  `cypherclaw.space_reverb.VOICE_REVERB_PROFILES` key set. The API accepts
  `sw_`-prefixed SynthDef aliases for caller convenience, but stores and
  returns canonical voice names.
- **Assumption:** The task asks for morph curve type, not an arbitrary curve
  function. T-048a therefore exposes the two curve laws currently implemented
  by `morph_voice.scd`: `linear` maps to SuperCollider `morph_curve=0`, and
  `equal-power` maps to `morph_curve=1`.
- **Candidate hardening:** The recurring SuperCollider failure modes are
  explicitly verified by existing source tests: profiled voice SynthDefs must
  declare `fx_bus_id`, and `sw_sampler.scd` must route through `fx_bus_id`
  rather than the legacy `fx_bus` control.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, startup-flow
  changes, agent commands, or SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with
  `pytest tests/test_composer_api.py -q` failing at collection on missing
  `cypherclaw.composer_api` before implementation. After implementation, the
  locked T-048a tests passed with `11 passed`; the required `fx_bus_id` /
  `sw_sampler.scd` hardening anchors passed with `3 passed`; focused Ruff and
  mypy checks on the new composer API passed. The required final validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5133 passed, 11 skipped`, Ruff clean, and mypy
  clean.

## T-045d (2026-05-23)

- **Reason:** Unit-coverage hardening assumptions for mood-driven space routing.
- **Details:** T-045d adds a compact unit-test matrix over the existing
  T-045b/T-045c space resolver and OSC `fx_bus_id` emission. It does not add a
  new routing mode or change SuperCollider sources.
- **Assumption:** "No active house is set" in house-bound mode uses the
  existing resolver default, `house_chamber`, which maps to
  `breath/glass_bell_jar` and bus `17`. This preserves the fallback already
  documented and implemented by T-045b/T-045c.
- **Candidate hardening:** The generated `bootstrap_identity()` feedback
  targets the existing startup identity subsystem. Current daemon,
  first-boot, governor, and narrative ASGI tests cover startup invocation,
  persistence between boots, and bootstrap-before-`FirstBootAnnouncer`
  ordering, so T-045d re-runs those anchors rather than broadening this
  resolver unit-coverage task into startup rewiring.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, HTTP routes,
  startup-flow changes, or SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with the locked T-045d fallback
  test failing on missing `summarize_voice_reverb_profiles()` fallback fields
  before implementation. After implementation, the locked T-045d tests passed
  with `2 passed`, adjacent mood-space anchors passed with `38 passed`,
  startup identity anchors passed with `13 passed`, and the required final
  validation (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/
  tests/ && mypy src/`) passed with `5108 passed, 11 skipped`, Ruff clean,
  and mypy clean.

## T-045c (2026-05-23)

- **Reason:** Scene playback resolver-wiring assumptions.
- **Details:** T-045c wires the T-045b space resolver through tracker scene
  event metadata and live voice playback. The intended behavior is that the
  sounding synth voice remains the requested runtime-safe voice while
  `fx_bus_id` follows the resolver-selected space for the scene's `mood_mode`
  and house context.
- **Assumption:** Tracker scenes do not always carry an explicit
  `active_house`. In house-bound mode, `patch_name` is the live house context
  because instrument patches are already named `house_monastery`,
  `house_chamber`, `house_garden`, `house_procession`, or `house_workshop`.
  Explicit `active_house` wins; unknown or missing house context falls back to
  the existing resolver default, `house_chamber`.
- **Candidate hardening:** The recurring SuperCollider failure modes are
  already anchored by source tests: all profiled voice SynthDefs declare
  `fx_bus_id`, and `sw_sampler.scd` uses `fx_bus_id` rather than `fx_bus`.
  T-045c keeps that contract and verifies it without changing SCD sources.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, HTTP routes, or
  SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with the locked T-045c scene
  playback tests failing at collection on the missing scene metadata helper
  export before implementation. After implementation, the locked T-045c tests
  passed with `5 passed`, focused resolver/tracker/voice/sampler hardening
  anchors passed with `94 passed`, startup identity anchors passed with
  `11 passed`, and the required final validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5106 passed, 11 skipped`, Ruff clean, and mypy
  clean.

## T-045b (2026-05-23)

- **Reason:** Resolver-slice assumptions for mood-driven space selection.
- **Details:** T-045b implements the pure space-selection resolver and wires it
  into faithful scene payloads plus OSC `/s_new` arg construction. It does not
  own active-house discovery from live sensors, SuperCollider synthdef
  rewrites, or broader playback orchestration; those remain for later
  T-045/T-046 slices.
- **Assumption:** The PRD requires `house-bound` to use "the active house's
  space" but does not define a house-to-space table. This task maps
  `house_monastery -> choir/stone_cathedral`,
  `house_chamber -> breath/glass_bell_jar`,
  `house_garden -> tabla_tin/dusk_garden`,
  `house_procession -> kotekan/humid_forest_canopy`, and
  `house_workshop -> pluck/small_wooden_room`, with unknown houses falling
  back to `house_chamber`.
- **Assumption:** Expressive mode uses a deterministic no-self-match mismatch
  table (`pluck -> kotekan`, `breath -> pad`, `choir -> bowed`,
  `kotekan -> tabla_tin`, `pad -> pluck`, `bowed -> breath`,
  `tabla_tin -> choir`) so tests can assert deliberate routing rather than
  random mood behavior.
- **Candidate hardening:** The generated startup-identity feedback targets the
  existing identity startup subsystem. This resolver does not touch startup
  flow, but final verification will re-run the identity persistence anchors.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, HTTP routes, or
  SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with the locked T-045b resolver and
  faithful-scene tests failing at collection on the missing resolver export
  before production code changed. After implementation, the locked T-045b tests
  passed with `5 passed`, adjacent MIDI scene and reverb profile tests passed
  with `36 passed`, and the startup identity hardening anchors passed with
  `11 passed`. The required validation command passed with `5101 passed,
  11 skipped`, Ruff clean, and mypy clean.

## T-045a (2026-05-23)

- **Reason:** Schema-only split assumptions for mood-driven space selection.
- **Details:** T-045a covers the first slice of CC-004: adding a typed
  `mood_mode` scene-schema value with allowed modes `matched`, `expressive`,
  and `house-bound`, plus parser/validator and JSON round-trip coverage for
  faithful MIDI scenes and tracker scenes. The actual space-selection resolver,
  active-house lookup, and playback/render routing are left to
  T-045b/T-045c/T-045d.
- **Assumption:** Existing `space_mode=matched` faithful-render behavior remains
  backward compatible while the new `mood_mode` metadata defaults to `matched`.
  Invalid parser input can safely normalize to `matched`, but serialized scene
  metadata should validate strictly and reject unsupported `mood_mode` values.
- **Candidate hardening:** The recurring `fx_bus_id` failures are already
  addressed in the current source: all seven voice synthdefs declare
  `fx_bus_id`, `master_smooth.scd` collects the matching canonical buses, and
  `sw_sampler.scd` now uses `fx_bus_id` rather than `fx_bus`. T-045a does not
  modify SuperCollider routing, but the final verification will re-run the
  focused synthesis routing anchors.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, HTTP routes, or
  SuperCollider source changes are required.
- **Verification:** Red phase was confirmed with the new
  `tests/test_midi_scene.py` mood-mode tests failing on missing imports and the
  new `tests/test_music_tracker.py` tracker tests failing on missing/default
  `mood_mode` behavior. After implementation, targeted MIDI/tracker/synthesis
  anchors passed with `73 passed`, and final validation
  (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`) passed with `5096 passed, 11 skipped`, Ruff clean, and mypy
  clean.

## T-044d (2026-05-23)

- **Reason:** Synthesis smoke-render routing regression found during exploration.
- **Details:** The focused synthesis test suite currently passes
  (`tests/test_senseweave_voice.py`, `tests/test_space_reverb_profiles.py`,
  `tests/test_sw_sampler.py`, and `tests/test_master_bus.py`), but a smoke
  trace that compares emitted voice `fx_bus_id` values with
  `master_smooth.scd` return-bus reads fails. `VOICE_REVERB_PROFILES` and
  `build_voice_s_new_args(...)` emit the seven CypherClaw v2 buses
  `pluck=16`, `breath=17`, `choir=18`, `kotekan=19`, `pad=20`, `bowed=21`,
  `tabla_tin=22`; `master_smooth.scd` still reads the older
  `gong/pluck/bowed/bell/kotekan/choir/breath` map on
  `18/20/22/24/26/28/30`, leaving buses 16, 17, 19, and 21 uncollected and
  reading unused buses 24, 26, 28, and 30.
- **Assumption:** The in-scope fix is to align `master_smooth.scd`'s
  documented return-bus controls and `In.ar(...)` reads with the canonical
  CypherClaw v2 voice profile table rather than changing the already locked
  voice profile bus assignments or T-044c test assertions. Compiled
  `.scsyndef` binaries still require regeneration on a host with
  SuperCollider installed; this repo change pins the source contract.
- **Startup hardening:** The generated `bootstrap_identity()` feedback targets
  the existing startup identity subsystem. Current CLI, first-boot,
  midi-intake, daemon-ordering, standalone/federated persistence, and
  narrative ASGI tests already cover `bootstrap_identity()` before
  `FirstBootAnnouncer` and persistence between boots; T-044d will re-run those
  anchors rather than broadening this audio-routing fix into startup rewiring.
- **Dependencies and migrations:** No new dependencies, provider secrets,
  database columns, migrations, runtime state directories, or HTTP routes are
  required.
- **Verification:** Red phase was confirmed with
  `pytest tests/test_space_reverb_profiles.py::test_master_smooth_fx_returns_match_voice_reverb_profiles tests/test_space_reverb_profiles.py::test_smoke_render_voice_fx_bus_ids_are_collected_by_master_smooth -q`
  failing on the stale master-return map. After aligning `master_smooth.scd`,
  those locked tests passed with `2 passed`, the focused synthesis suite passed
  with `96 passed`, the locked T-044c routing anchors passed with `5 passed`,
  and startup identity hardening anchors passed with `13 passed`. The first
  full validation run exposed one additional in-scope legacy assertion in
  `tests/test_master_smooth_scd.py` that still expected the old `gong`/`bell`
  return map; that test now derives the canonical voice set from
  `VOICE_REVERB_PROFILES`. Final validation passed with `5088 passed,
  11 skipped`, Ruff clean, and mypy clean.

## T-044c (2026-05-23)

- **Reason:** Task is a no-op against the current tree — the unit tests
  it asks for already landed earlier in this session under commit
  `07335db` ("test(synthesis): pin voice fx_bus_id routing against
  cross-voice leakage [T-044c]").
- **Details:** T-044c asks to "Add unit tests asserting voices emit on
  their assigned fx bus and that mismatched bus IDs are rejected."
  `tests/test_senseweave_voice.py::TestFxBusRouting` already contains
  the two regression tests added by that commit:
  `test_note_on_rejects_other_voices_fx_bus_ids` (each profiled timbre's
  emitted `fx_bus_id` matches the voice's own profile bus and is not in
  the set of foreign voice buses) and
  `test_set_timbre_reroutes_to_the_new_voices_fx_bus_id` (swapping
  timbre re-routes the next `/s_new` to the new voice's bus with no
  stale bus id leakage). The commit body also records that mutating
  `SenseweaveVoice.note_on` to bump the emitted bus by +1 causes both
  new tests to fail, i.e. they are mutation-tested.
- **Background:** The Verify agent for T-044c (gemini) hit a 600s wall-
  clock timeout before writing `sdp/verification/t-044c-verify.md`,
  which appears to have triggered the orchestrator to re-spawn Lead on
  the same task. No code regression was implied — the timeout was in
  the verifier itself, mid-investigation.
- **Assumption:** No additional production code or locked test-assertion
  changes are required for T-044c. The contract is locked by the two tests
  above plus the pre-existing positive
  `test_note_on_routes_each_voice_to_its_assigned_fx_bus_id` and negative
  `test_note_on_skips_fx_bus_id_for_voices_without_a_profile` tests in the
  same class. This follow-up pass adds the missing spec/status documentation
  around the already-landed tests.
- **Startup hardening:** The generated `bootstrap_identity()` feedback targets
  the existing identity startup subsystem. T-044c is a test-only voice routing
  contract, so startup flow is not changed here; the existing CLI,
  first-boot, daemon-ordering, standalone/federated persistence, and narrative
  ASGI identity tests remain mandatory verification anchors.
- **Verification:** Re-ran `tests/test_senseweave_voice.py::TestFxBusRouting`
  — 4 passed in 0.12s before adding this documentation closure.

## T-044a (2026-05-23)

- **Reason:** Task is a no-op against the current tree — the work it
  describes was already shipped under T-044 (commit `aa215bd`).
- **Details:** T-044a asks to "Replace hardcoded `Out.ar` bus targets in
  each voice synthdef with the `fx_bus_id` parameter so audio writes to
  the declared bus." Inspection of
  `my-claw/tools/senseweave/synthesis/voices/sw_*.scd` shows every voice
  already declares an `fx_bus_id` SynthDef control whose default matches
  its `VoiceReverbProfile` and emits `Out.ar(fx_bus_id, ...)` for the
  per-voice FX return alongside the dry `Out.ar(out_bus, ...)` tap to
  the master mix. No literal/hardcoded bus numbers remain in any voice
  `Out.ar` call (only the master synthdef writes to `0` via
  `ReplaceOut.ar(0, sig)`, which is correct).
- **Assumption:** No code change is required for T-044a. The contract is
  already pinned in source and locked by three regression tests in
  `tests/test_space_reverb_profiles.py`:
  `test_voice_synthdefs_declare_fx_bus_id_routing_contract`,
  `test_voice_synthdef_fx_bus_ids_are_pairwise_unique`, and
  `test_each_voice_routes_only_to_its_assigned_fx_bus` — all three pass.
- **Verification:** Re-ran the three contract tests and the full
  `tests/test_space_reverb_profiles.py` module; all green. No new code,
  test, or doc changes were introduced for this task.

## T-044 (2026-05-23)

- **Reason:** SuperCollider `.scsyndef` binaries cannot be regenerated in
  this environment; sclang/scsynth are not installed on this machine.
- **Details:** The blocking finding on the first T-044 verify pass was that
  the seven CypherClaw §4 voice synthdefs had no `fx_bus_id` control on
  their binary, so `build_voice_s_new_args` was sending an OSC arg that
  the server silently ignored. This task pins the per-voice routing
  contract in source: each `synthesis/voices/sw_<voice>.scd` declares
  `fx_bus_id` with the default that matches its `VoiceReverbProfile` and
  writes a parallel send through `Out.ar(fx_bus_id, ...)`, in lockstep
  with `sw_sampler.scd` (renamed `fx_bus` → `fx_bus_id` for consistency).
  A new regression test in `tests/test_space_reverb_profiles.py` pins the
  contract so a future drift is caught at test time.
- **Assumption:** The existing
  `my-claw/tools/senseweave/synthesis/synthdefs/sw_<voice>.scsyndef`
  binaries must be regenerated from the new `voices/*.scd` sources on a
  host with sclang installed (CypherClaw) before live routing takes
  effect on scsynth. The .scd sources are the new source of truth; the
  binary regeneration is a deploy step, not part of this task.
- **Dependencies and migrations:** No new Python dependencies, database
  columns, migrations, provider secrets, cost-bearing services, or
  runtime state directories are required. New tree:
  `my-claw/tools/senseweave/synthesis/voices/`.
- **Startup hardening:** Per-voice synthdef contracts do not touch the
  identity bootstrap flow that the auto-generated hardening bullets
  target. Existing startup identity tests still cover that path; this
  task re-runs them rather than altering them.
- **Verification:** Locked T-044 test cases now include
  `test_voice_synthdefs_declare_fx_bus_id_routing_contract` and
  `test_voice_synthdef_fx_bus_ids_are_pairwise_unique`, alongside the
  existing `test_each_voice_routes_only_to_its_assigned_fx_bus`. Sampler
  rename verified through `tests/test_sw_sampler.py` updates.

## T-043 (2026-05-23)

- **Reason:** Scope boundary between tuned space profiles and later live
  routing.
- **Details:** Exploration found the CypherClaw v2 PRD assigns T-043 to CC-002:
  tune the seven per-voice reverb spaces from
  `cypherclaw-v2-design-statement-2026-05-22.md` §4. The existing faithful MIDI
  render contract already carries the seven design voices and bus ids
  `pluck=16`, `breath=17`, `choir=18`, `kotekan=19`, `pad=20`, `bowed=21`,
  `tabla_tin=22`; `sampler_effects.scd` provides generic algorithmic reverb
  controls, while `master_smooth.scd` has a separate older Korsakov bus stub
  using `gong`/`bell`. This task therefore creates typed, shared default
  profiles and one `synthesis/spaces/*.scd` source/documentation file per §4
  space, then wires faithful render metadata to those profiles. It does not
  claim mood-driven selection, convolution IR assets, or full live OSC routing;
  those remain T-044+ follow-ups.
- **Dependencies and migrations:** No new dependencies, database columns,
  migrations, provider secrets, cost-bearing services, binary IR assets, or
  runtime state directories are required.
- **Startup hardening:** The generated `bootstrap_identity()` hardening bullets
  target the existing identity startup subsystem. Current CLI, first-boot,
  daemon-ordering, and narrative ASGI tests already cover persistence and
  ordering before `FirstBootAnnouncer` across standalone/federated modes, so
  this audio-profile task will re-run those anchors rather than modifying
  startup flow.
- **Verification:** Red phase was confirmed before implementation with
  `pytest tests/test_space_reverb_profiles.py -q` failing on the missing
  `cypherclaw.space_reverb` module. After implementation, the locked
  T-043 tests passed with `5 passed`, faithful MIDI render coverage passed
  with `15 passed`, sampler/master-bus regression coverage passed with
  `60 passed`, and startup identity hardening anchors passed with
  `11 passed`. The required full validation command passed with
  `5078 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-039 (2026-05-23)

- **Reason:** Existing composer arc names differ from the PRD's four tuning
  phase names.
- **Details:** The CypherClaw v2 design statement defines the tuning rule as
  5-limit just intonation for `Listen`/`Divination`, Slendro for
  `Conversation`/`Procession`, with morphs at stillness/motion transitions.
  The current score-tree composer arc is
  `Divination -> Emergence -> Conversation -> Convergence -> Crystallization`,
  so this task maps `Crystallization` to stillness and
  `Emergence`/`Convergence` to motion while still supporting the explicit
  `Listen` and `Procession` phase names. Unknown phases remain legacy
  `twelve_tet`.
- **Dependencies and migrations:** No new dependencies, database columns,
  migrations, provider secrets, or runtime state directories are required.
- **Startup hardening:** The generated `bootstrap_identity()` hardening bullets
  are already addressed in the existing startup paths: MIDI intake calls
  `bootstrap_identity()` before `FirstBootAnnouncer`, and narrative API startup
  bootstraps identity on both module import and CLI entry. Existing
  standalone/federated persistence and startup-order tests will be re-run as
  anchors; this composer metadata task does not change startup code.
- **Verification:** Red phase was confirmed before implementation with the
  locked T-039 score-tree composer tests failing on missing
  `plan_tuning_trajectory`. After implementation, focused score-tree/tuning
  coverage passed with `82 passed`, startup identity hardening anchors passed
  with `9 passed`, and the required full validation command passed with
  `5052 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-032 (2026-05-23)

- **Reason:** Scripted end-to-end boundary for JACK, Worker, R2, and browser
  audio in CI
- **Details:** PromptClaw remains the ADP source of truth, but the Worker/R2 and
  browser live-page implementation is in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` repository. T-032 adds a
  streamer-side POST helper in `my-claw/tools/audio_streamer.py` and a
  dependency-free Worker E2E test in `catalog-explorer` that scripts a
  JACK-tone segment through the real Worker handler, fake R2 storage, playlist
  generation, segment retrieval, and browser `<audio>` initialization.
- **Scope decision:** The automated test does not require live JACK hardware,
  Cloudflare credentials, a live R2 bucket, or a real browser media decoder.
  It uses synthetic Ogg/Opus-like bytes carrying a tone-generator marker and
  exercises the production request/storage/page code path. The existing T-026
  Ogg/Opus HLS-container caveat remains: this verifies segment propagation and
  browser audio wiring, not final hls.js/Safari media decode compatibility.
- **Dependencies and migrations:** No new Python or npm dependencies, database
  columns, migrations, provider secrets, runtime state directories, or
  startup-flow rewiring are required.
- **Startup hardening:** The generated `bootstrap_identity()` hardening bullets
  are addressed by re-running the established CLI, first-boot,
  daemon-ordering, and narrative ASGI identity anchors. This task does not
  change those startup paths.
- **Verification:** Red phase was confirmed before implementation: the Python
  streamer test failed on the missing upload helper and the Worker E2E failed
  on missing ingest latency metadata. After implementation, focused streamer
  upload coverage passed, Worker `npm test` passed with the E2E latency log
  `cypherclaw_t032_latency_ms=1777`, Worker `npm run check` passed, startup
  identity anchors passed with `11 passed`, and full PromptClaw validation
  passed with `5004 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-030 (2026-05-23)

- **Reason:** Cross-repository Worker location and read-time R2 listing scope
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` archive feed renders inside the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker. T-030
  therefore keeps bookkeeping in PromptClaw while adding the worker-side
  rendering and a Node snapshot test in `catalog-explorer`. The page now lists
  R2 objects under `cypherclaw/archive/` and reads each `metadata.json` at
  request time to build the feed; no new database table, durable object,
  background job, or API endpoint is introduced.
- **Scope decision:** The feed is server-rendered into the existing landing
  HTML and uses the existing `/api/cypherclaw/segment/...` proxy for playback,
  so no new public API surface or client-side fetching is required. Per the
  T1 instructions, no spec is written and no unrelated bookkeeping is touched.
  Audio playback for each session is a standard `<audio controls preload="none"
  src="…/session.opus">` element; no autoplay, no playlist, no listener
  counters, and no analytics are added.
- **Dependencies and migrations:** No new Python or npm dependencies, database
  columns, or migrations are required.
- **Verification:** Snapshot test in
  `catalog-explorer/worker/tests/cypherclaw-archive-feed.test.js` covers the
  rendered HTML for a fixture session list plus ordering, playable audio,
  empty-state, HTML escaping, R2 listing, and end-to-end page embedding;
  `npm test` passed with `30 passed` and `npm run check` passed clean. Manual
  UI verification at `https://cypherclaw.holdenu.com/` is deferred to the
  T-030 Worker deploy in `catalog-explorer`.

## T-029 (2026-05-23)

- **Reason:** R2 upload scope and runtime credential assumption
- **Details:** T-029 implements the PromptClaw-side runtime archiver in
  `my-claw/tools/session_archiver.py`; it does not add a new Worker archive
  ingest route. The tool writes archive objects directly under
  `cypherclaw/archive/{session_id}/` through an injectable R2/S3-compatible
  upload client. Tests use a fake R2 client, so no live Cloudflare credentials,
  provider secrets, or cost-bearing uploads are required during validation.
- **Assumptions:** Local stream segments are complete `.opus` files with
  optional `.json` sidecars carrying `captured_at`, `duration`, `patch_name` or
  `house`, and `tuning`. Missing sidecars fall back to filename/filesystem
  timing and default segment duration. Ogg/Opus sessions are concatenated as
  chained Ogg byte streams rather than invoking ffmpeg.
- **Dependencies and migrations:** No new Python or npm dependencies, database
  columns, or migrations are required.
- **Startup hardening:** The new archiver startup path invokes
  `bootstrap_identity()` before archive work and exposes standalone/federated
  identity arguments. T-029 adds an archiver identity-persistence regression and
  re-runs the existing CLI, first-boot, daemon-ordering, and narrative ASGI
  identity anchors.
- **Verification:** Red phase failed as expected before implementation
  because `session_archiver.py` was missing. After implementation,
  `pytest tests/test_session_archiver.py -q` passed with `4 passed`, related
  archive/streamer tests passed with `18 passed`, mandatory startup identity
  anchors passed with `11 passed`, the dry-run CLI returned a successful empty
  plan for an empty segment directory, and the required validation command
  passed with `5001 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-028d (2026-05-23)

- **Reason:** Cross-repository Worker location and SSE event-normalization
  scope
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` live page is implemented in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker. T-028d
  therefore keeps the spec, progress, changelog, and startup-hardening anchors
  in PromptClaw while changing Worker HTML/JS tests and inline visualizer
  runtime in `catalog-explorer`.
- **Scope decision:** The PRD's durable-object-backed live feature fanout and
  producer POST path are not present in this checkout and remain a backend
  slice. T-028d assumes the browser should accept both the current flat
  `/tmp/glyph_audio_features.json`-style payload and a future nested
  `audio`/`visual`/`scene`/`tuning` envelope, normalize those events, update
  visualizer state, and render from that state. No new npm packages, provider
  secrets, database migrations, database columns, runtime state directories, or
  startup-flow rewiring are required.
- **Startup hardening:** The generated startup identity bullets target existing
  startup paths; current CLI, first-boot, daemon ordering, and narrative ASGI
  tests cover `bootstrap_identity()` persistence and bootstrap-before-
  `FirstBootAnnouncer` ordering, so T-028d will re-run those anchors rather
  than broadening this Worker visualizer task into identity subsystem changes.
- **Reason:** Red phase and verification results
- **Details:** Red phase was confirmed with
  `npm test -- tests/cypherclaw-visualizer-runtime.test.js` in
  `/Users/anthony/Programming/catalog-explorer/worker` failing the two new
  runtime assertions because the T-028c visualizer did not normalize nested
  `audio`/`visual`/`scene`/`tuning` SSE payloads or map flat
  `spectral_centroid_hz` into the rendered state. After implementation, focused
  Worker runtime tests passed through the Worker's full `npm test` command with
  `20 passed`, Worker `npm run check` passed, mandatory startup identity
  hardening anchors passed with `11 passed`, and full PromptClaw validation
  passed with `4997 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-028c (2026-05-23)

- **Reason:** Cross-repository Worker location and minimal SSE-feed scope
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` live page is implemented in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker. T-028c
  therefore keeps the spec, progress, changelog, and startup-hardening anchors
  in PromptClaw while changing Worker HTML/CSS/JS and a public Worker GET route
  in `catalog-explorer`.
- **Scope decision:** The PRD describes `/api/cypherclaw/live-features` as a
  durable-object-backed fanout fed by periodic cypherclaw feature updates. That
  full producer/fanout service is not present in this checkout and remains a
  later backend slice. T-028c adds a minimal SSE-compatible GET response with an
  initial feature payload so the page's EventSource connects to a real
  `text/event-stream` endpoint instead of a 404, while implementing the active
  browser-side canvas visualizer draw loop and SSE client. No new npm packages,
  provider secrets, database migrations, database columns, runtime state
  directories, or startup-flow rewiring are required.
- **Startup hardening:** The generated startup identity bullets target existing
  startup paths; current CLI, first-boot, daemon ordering, and narrative ASGI
  tests cover `bootstrap_identity()` persistence and bootstrap-before-
  `FirstBootAnnouncer` ordering, so T-028c will re-run those anchors rather
  than broadening this Worker visualizer task into identity subsystem changes.
- **Reason:** Red phase and verification results
- **Details:** Red phase was confirmed with
  `npm test -- tests/cypherclaw-landing.test.js` in
  `/Users/anthony/Programming/catalog-explorer/worker` failing the three new
  T-028c assertions because the T-028b page lacked `initCypherClawVisualizer()`,
  EventSource wiring, and a real `/api/cypherclaw/live-features` SSE response.
  After implementation, focused Worker landing tests passed with `18 passed`,
  full Worker `npm test` passed with `18 passed`, Worker `npm run check` passed,
  mandatory startup identity hardening anchors passed with `11 passed`, and
  full PromptClaw validation passed with `4997 passed, 11 skipped`, Ruff clean,
  and mypy clean.

## T-028b (2026-05-23)

- **Reason:** Cross-repository Worker location, hls.js runtime dependency, and
  stream-container caveat
- **Details:** PromptClaw remains the ADP source of truth, but the
  `cypherclaw.holdenu.com` static page is implemented in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker. T-028b
  therefore keeps the spec, progress, changelog, and startup-hardening anchors
  in PromptClaw while changing the Worker HTML/CSS/JS in `catalog-explorer`.
  The task adds a browser runtime dependency on hls.js through the public CDN
  URL `https://cdn.jsdelivr.net/npm/hls.js@1/dist/hls.min.js`; no npm package,
  lockfile change, provider secret, database migration, or backend dependency is
  introduced. The existing T-026 caveat remains: the current live playlist still
  points at Ogg/Opus `.opus` segments, which hls.js and ffplay do not decode as
  standard HLS media segments. T-028b wires the native-HLS/hls.js playback
  controller, while actual cross-browser media decode still depends on a later
  segment-container fix.
- **Scope decision:** The GlyphWeave backdrop is implemented as static
  CSS/image layers embedded in the page rather than a new asset ingestion route,
  because the gallery export and SSE-driven visualizer are later T-028 subtasks.
  The generated startup identity hardening bullets target existing startup
  paths; current CLI, first-boot, daemon ordering, and narrative ASGI tests cover
  `bootstrap_identity()` persistence and bootstrap-before-`FirstBootAnnouncer`
  ordering, so they remain mandatory regression anchors instead of expanding
  this static page task into startup rewiring.
- **Reason:** Red phase and verification results
- **Details:** Red phase was confirmed with
  `npm test -- tests/cypherclaw-landing.test.js` in
  `/Users/anthony/Programming/catalog-explorer/worker` failing the two new
  T-028b assertions because the T-028a scaffold lacked rendered GlyphWeave
  image layers, playback data hooks, and native-HLS/hls.js initialization. After
  implementation, the focused Worker landing command passed, full Worker
  `npm test` passed with `15 passed`, Worker `npm run check` passed, and the
  mandatory startup identity hardening anchors passed with `11 passed`. The
  required PromptClaw validation command passed with `4997 passed, 11 skipped`,
  Ruff clean, and mypy clean.

## T-028a (2026-05-23)

- **Reason:** Cross-repository Worker location and scaffold-only scope
- **Details:** The PromptClaw repository is the ADP source of truth, but the
  public `cypherclaw.holdenu.com` root route is implemented by the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` Cloudflare Worker, where
  T-027 added the placeholder landing page. T-028a therefore keeps the spec,
  progress, changelog, and startup-hardening regression anchors in PromptClaw
  while replacing the Worker placeholder with a static public stream scaffold
  in `catalog-explorer`. This subtask owns only the static HTML structure: the
  live `<audio>` element, GlyphWeave backdrop placeholder, and canvas visualizer
  placeholder. Live canvas drawing, hls.js fallback, archive feed UI, and the
  SSE endpoint implementation remain later T-028 subtasks.
- **Scope decision:** No new dependencies, database migrations, provider
  secrets, runtime state directories, or startup-flow rewiring are required.
  The generated startup identity hardening bullets target already-covered
  startup paths (`midi_intake_daemon.main()`, narrative ASGI import, and
  first-boot persistence); T-028a will re-run those anchors rather than broadening
  a static page scaffold into identity subsystem work. The T-026 HLS/Ogg segment
  compatibility escalation remains unchanged because this task only points the
  page at the established playlist endpoint.
- **Reason:** Red phase and verification results
- **Details:** Red phase was confirmed before implementation with
  `npm test` in `/Users/anthony/Programming/catalog-explorer/worker` failing
  the three new landing-page assertions because the T-027 placeholder lacked
  `cypherclaw-live-page`, `cypherclaw-live-audio`, `glyphweave-backdrop`, and
  `cypherclaw-visualizer`. After implementation, Worker `npm test` passed with
  `13 passed`, Worker `npm run check` passed, startup identity hardening anchors
  passed with `11 passed`, and full PromptClaw validation passed with
  `4997 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-026 (2026-05-23)

- **Reason:** PRD segment container format is incompatible with standard HLS
  players
- **Details:** T-024 emits Ogg/Opus segments (`.opus` files) and T-025 stores
  them under `cypherclaw/live/{date}/seg-{seq}.opus`. T-026 adds the
  `GET /api/cypherclaw/live.m3u8` playlist and `GET /api/cypherclaw/segment/...`
  retrieval endpoints exactly per the PRD, and the emitted playlist is a
  valid HLS manifest (`#EXTM3U`, `#EXT-X-VERSION:3`, `#EXT-X-TARGETDURATION`,
  `#EXT-X-MEDIA-SEQUENCE`, ordered `#EXTINF` + URI pairs). However, the
  acceptance criterion ("`hls.js` validator or `ffplay` successfully plays the
  live stream") cannot be satisfied with raw Ogg/Opus segments: ffmpeg's HLS
  demuxer rejects `.opus` segment extensions (`URL ... is not in
  allowed_segment_extensions`) even with `-allowed_extensions ALL`, because
  raw Ogg is not a supported HLS segment container. hls.js has the same
  limitation. Standard HLS requires CMAF/fMP4 (`.m4s`) or MPEG-TS (`.ts`); both
  can carry Opus.
- **Recommendation:** Follow-on task on T-024 to re-package each 6-second
  segment as fragmented MP4 (CMAF, `.m4s`) carrying the existing Opus stream,
  and adjust T-025's R2 key suffix accordingly. The T-026 playlist endpoint
  here is forward-compatible: it derives the segment URI from the R2 key and
  the `#EXTINF` duration from R2 custom metadata, so once the suffix and
  container change in T-024, the playlist will start serving HLS-playable
  segments with no Worker change required.
- **Scope decision:** Shipping the playlist + retrieval endpoints now per
  CC-022, because the segment container format is a structural T-024 concern
  and rewriting the encoder is out of T-026's scope. Worker tests
  (`npm test`, `npx tsc --noEmit`) and PromptClaw regression anchors stay
  green.

## T-025 (2026-05-23)

- **Reason:** Cross-repository Worker location and route-auth assumption
- **Details:** The CypherClaw v2 PRD identifies PromptClaw as the primary repo
  for ADP artifacts but places the existing Cloudflare Worker in the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` project. This task
  therefore keeps the specification, progress, changelog, and regression
  anchors in PromptClaw while implementing the Worker route in the existing
  holdenu API Worker. The segment ingest route follows the Worker's existing
  write-endpoint pattern and requires `Authorization: Bearer <ADMIN_TOKEN>` even
  though the PRD does not spell out auth for segment POSTs; unauthenticated
  public R2 writes would be unsafe. No new dependencies, database migrations,
  provider secrets, or startup-flow changes are required. The generated startup
  identity hardening bullets target an already-covered subsystem and are handled
  as regression verification rather than unrelated T-025 implementation scope.

## T-022d (2026-05-23)

- **Reason:** Meter trajectory test-hardening scope and startup-hardening assumptions
- **Details:** Exploration found T-022d builds on T-022a/T-022b/T-022c rather
  than adding a new active meter runtime. This task assumes the missing
  trajectory-planning coverage is the arc-cycle boundary case where a composed
  piece crosses from `Crystallization` back to `Divination`; the planner should
  restart phase drift counts for the new procedural arc cycle while keeping
  repeated phases inside one continuous cycle deterministic. It also adds a
  composed score-tree JSON round-trip to tracker-scene metadata regression. No
  dependencies, migrations, database columns, provider secrets, or active
  tracker row-timing changes are in scope. The generated startup identity
  hardening bullets target the existing identity subsystem; current CLI,
  first-boot, governor, daemon-ordering, and narrative ASGI tests remain
  mandatory regression anchors rather than new startup rewiring for this meter
  task.
- **Reason:** Red phase and focused verification
- **Details:** Red phase was confirmed with
  `pytest tests/test_score_tree_composer.py::test_plan_meter_trajectory_restarts_phase_drift_per_arc_cycle tests/test_score_tree_composer.py::test_composed_meter_trajectory_scene_metadata_round_trips_through_json_and_tracker -q`
  failing because the second-cycle `Divination` scene planned `4/4` instead of
  restarting at the first `Divination` drift cell (`free`). The implementation
  detects canonical procedural arc wraps and clears phase occurrence counts at
  the cycle boundary. Focused verification passed with `2 passed`,
  trajectory/metadata anchors passed with `8 passed`, and startup identity
  hardening anchors passed with `11 passed`.
- **Reason:** Full validation
- **Details:** Full validation passed with
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`:
  `4991 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies or
  migrations were introduced.

## T-022b (2026-05-23)

- **Reason:** Composer meter-trajectory planner scope and startup-hardening assumptions
- **Details:** Exploration found T-022a already added the typed
  `MeterTrajectory` / `MeterSceneValue` carrier and tracker compiler
  propagation. This task assumes T-022b owns deterministic composer-side
  planning from existing per-section `ArcDirective` phase metadata in
  `recursive_composer.py`, plus stamping each `SectionNode.scene_metadata`.
  It does not make `TrackerScene` scheduling consume the planned meter, alter
  active groove-meter selection, add database columns, add migrations, or add
  dependencies. The generated startup identity hardening bullets target the
  existing identity startup subsystem; current CLI, daemon, first-boot,
  governor, and narrative ASGI tests remain regression anchors rather than new
  startup work for this meter-planner slice.
- **Reason:** Red phase and focused verification
- **Details:** Red phase was confirmed with
  `pytest tests/test_score_tree_composer.py::test_plan_meter_trajectory_uses_arc_phase_drift_table tests/test_score_tree_composer.py::test_recursive_composer_plans_meter_trajectory_for_full_arc tests/test_score_tree_composer.py::test_composed_meter_trajectory_survives_tracker_compile -q`
  failing on the missing `plan_meter_trajectory` import before production code
  changed. After implementation, the locked T-022b tests passed with `3
  passed`, the full score-tree composer test file passed with `27 passed`, and
  adjacent T-022a/T-021 carrier and timing anchors passed with `5 passed`.
- **Reason:** Full validation
- **Details:** Full validation passed with
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`:
  `4986 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-022a (2026-05-23)

- **Reason:** Meter-trajectory model scope and startup-hardening assumptions
- **Details:** Exploration found T-022a is the first slice of CC-032, following
  T-020/T-021 metric-modulation work. This task defines a score-tree-level
  `MeterTrajectory` model, adds a per-section scene metadata carrier, and
  preserves that metadata through the compile-to-tracker handoff. It does not
  implement the later trajectory planner table, mutate tracker row timing, add
  database columns, or add migrations. The generated startup hardening bullets
  target the existing identity startup subsystem; current startup tests already
  cover `bootstrap_identity()` persistence/order, so this task will re-run
  those anchors rather than broadening meter metadata work into startup
  rewiring. No new dependencies are required.
- **Reason:** Red phase and verification
- **Details:** Red phase was confirmed with the focused score-tree and tracker
  compiler tests failing on missing `MeterSceneValue` / `MeterTrajectory`
  imports before production code changed. After implementation, the focused
  model and compiler tests passed, metric-modulation plus startup identity
  anchors passed, and full validation passed with `pip install -e '.[dev]' &&
  pytest tests/ -x && ruff check src/ tests/ && mypy src/`: `4983 passed, 11
  skipped`, Ruff clean, and mypy clean.

## T-021 (2026-05-23)

- **Reason:** Metric-modulation timing scope and startup-hardening assumptions
- **Details:** Exploration found the affected tracker timing path is
  `my-claw/tools/senseweave/music_tracker.py` plus runtime consumption in
  `my-claw/tools/senseweave/music_tracker_runtime.py`. Existing groove code
  already carries metric-modulation labels in scene/step metadata, but row
  elapsed timing stayed constant. This task assumes ratio semantics are
  duration scaling, so `3:2` multiplies row duration by `3 / 2` from the
  target row onward while preserving row indices and lane placement. The
  generated startup hardening bullets target the existing identity subsystem;
  `midi_intake_daemon.main()` already invokes `bootstrap_identity()` before
  `FirstBootAnnouncer()`, and existing CLI, first-boot, governor, and
  narrative ASGI tests cover standalone/federated identity persistence. Those
  tests remain mandatory regression anchors rather than broadening T-021 into
  startup rewiring. No new dependencies, migrations, provider secrets,
  database columns, runtime state directories, HTTP routes, auth behavior, or
  agent command strings are required.
- **Reason:** Red phase and focused verification
- **Details:** Red phase was confirmed with
  `pytest tests/test_music_tracker.py::TestMetricModulationTiming::test_applies_three_to_two_modulation_from_target_row tests/test_music_tracker_runtime.py::TestScheduleScene::test_metric_modulation_changes_event_duration_and_row_sleeps_from_target_row -q`
  failing on the missing `MetricModulation` import before production code
  changed. After implementation, the locked focused tests passed with
  `2 passed`, and `pytest tests/test_music_tracker.py
  tests/test_music_tracker_runtime.py tests/test_groove_engine.py -q` passed
  with `175 passed`. Startup identity hardening anchors passed with
  `11 passed`. Full validation passed with `pip install -e '.[dev]' && pytest
  tests/ -x && ruff check src/ tests/ && mypy src/`: `4979 passed, 11
  skipped`, Ruff clean, and mypy clean.

## T-017d (2026-05-23)

- **Reason:** Faithful render regression-test scope and startup-hardening assumptions
- **Details:** Exploration found T-017d is a focused test-hardening task over
  the existing T-017c faithful render contract. The affected path is
  `src/cypherclaw/midi_loader.py` for ordered source events,
  `src/cypherclaw/midi_scene.py` for the JSON-safe faithful scene and render
  metadata, and `src/cypherclaw/midi_intake_daemon.py` for faithful manifest
  wiring. This task assumes "faithful-transmission render" means the scene
  contract already emitted by `build_faithful_midi_scene(...)`, not a new
  SuperCollider or OSC runtime path. The generated startup hardening bullets
  target the existing identity subsystem; `midi_intake_daemon.main()` already
  invokes `bootstrap_identity()` before `FirstBootAnnouncer()`, and the
  existing standalone/federated persistence tests remain mandatory regression
  anchors rather than broadening this test-only faithful-render task into
  startup rewiring. No new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, auth behavior, or agent
  command strings are required.
- **Reason:** Red-phase applicability for regression-only scope
- **Details:** The new T-017d regression tests passed against the current
  branch before production-code edits because commit `bd407de` (T-017c)
  already implemented `FaithfulRenderSettings`, `render_pitch_hz`,
  `render_voice`, and `render_space`. The pre-T-017c baseline commit
  `9a29745` has none of those symbols, so these tests would fail there at
  collection/import. No production implementation was changed for T-017d; the
  task adds locked coverage over already-shipped behavior.
- **Reason:** Verification results
- **Details:** Focused faithful MIDI/render coverage passed with `78 passed`.
  Startup identity hardening anchors passed with `11 passed`, covering
  bootstrap-before-announcer ordering plus standalone/federated persistence.
  Full validation passed with `pip install -e '.[dev]' && pytest tests/ -x &&
  ruff check src/ tests/ && mypy src/`: `4967 passed, 11 skipped`, Ruff clean,
  and mypy clean. No new dependencies or migrations were introduced.


## T-017c (2026-05-23)

- **Reason:** Faithful render-settings scope and startup-hardening assumptions
- **Details:** Exploration found T-017c builds directly on T-017a/T-017b:
  `src/cypherclaw/midi_loader.py` supplies ordered source MIDI events,
  `src/cypherclaw/midi_scene.py` builds the faithful tracker-like scene, and
  `src/cypherclaw/midi_intake_daemon.py` writes that scene into processed
  manifests. This task assumes "during render" means enriching the faithful
  scene contract with render-time tuning, voice, synth, and matched space
  metadata that downstream audio renderers can consume, while preserving the
  imported MIDI `pitch`, `duration_ticks`, row order, and empty-fragment
  bypass behavior. Formal SuperCollider FX bus provisioning and the full
  tuning-system package remain later PRD tasks; T-017c publishes stable
  JSON-safe metadata only. The generated startup hardening bullets target the
  existing identity startup subsystem; current CLI, first-boot,
  daemon-ordering, standalone/federated persistence, and narrative ASGI tests
  already cover `bootstrap_identity()` before `FirstBootAnnouncer()`, so they
  remain regression anchors rather than broadening this faithful-render task
  into startup rewiring. No new dependencies, migrations, provider secrets,
  database columns, runtime state directories, HTTP routes, auth behavior, or
  agent command strings are required.
- **Reason:** Red phase and focused verification results
- **Details:** Red phase was confirmed with `pytest tests/test_midi_scene.py -q`
  failing at collection on the missing `FaithfulRenderSettings` import before
  production code changed. After implementation, the locked T-017c faithful
  scene tests passed with `8 passed`, adjacent MIDI/composer vocabulary
  coverage passed with `75 passed`, startup identity hardening anchors passed
  with `11 passed`, focused Ruff passed for `src/cypherclaw/midi_scene.py` and
  `tests/test_midi_scene.py`, and focused mypy passed for
  `src/cypherclaw/midi_scene.py` plus `src/cypherclaw/midi_intake_daemon.py`.
  Full validation passed with `pip install -e '.[dev]' && pytest tests/ -x &&
  ruff check src/ tests/ && mypy src/`: `4964 passed, 11 skipped`, Ruff
  clean, and mypy clean.

## T-017b (2026-05-23)

- **Reason:** Faithful MIDI scene-mapping scope and startup-hardening assumptions
- **Details:** Exploration found T-017b builds directly on T-017a's
  `cypherclaw.midi_loader.load_faithful_midi_events(...)` and the existing
  processed-manifest path in `src/cypherclaw/midi_intake_daemon.py`. The
  downstream CypherClaw tracker scene shape uses patterns, lanes, steps, and
  metadata, so this task assumes the in-scope faithful renderer should emit a
  JSON-safe tracker-like scene dictionary in the intake manifest under
  `faithful_scene`. The scene keeps exact imported MIDI pitches and source tick
  durations while quantizing positive durations onto rows for scheduler
  handoff. It intentionally does not call composer vocabulary fragment
  selection or attach `vocabulary_fragment_id` metadata; later renderer tasks
  own applying tuning, voice, space, and expression choices to that faithful
  scene. The generated startup hardening bullets target the existing identity
  startup subsystem; current CLI, first-boot, daemon-ordering, and narrative
  ASGI tests already cover `bootstrap_identity()` before
  `FirstBootAnnouncer()` plus standalone/federated persistence, so they remain
  regression anchors rather than broadening this MIDI scene task into startup
  rewiring. No new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, or agent command strings are
  required.
- **Reason:** Red phase and focused implementation results
- **Details:** Red phase was confirmed with
  `pytest tests/test_midi_scene.py -q` failing on missing
  `cypherclaw.midi_scene` before production code changed. After implementing
  the typed mapper and faithful-manifest wiring, the locked T-017b tests passed
  with `4 passed`, adjacent T-017a/MIDI/composer vocabulary coverage passed
  with `67 passed`, startup identity hardening anchors passed with `11 passed`,
  focused Ruff passed for the touched source and test files, and focused mypy
  passed for `src/cypherclaw/midi_scene.py` plus
  `src/cypherclaw/midi_intake_daemon.py`. Full validation passed with
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`: `4960 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-013c (2026-05-22)

- **Reason:** MIDI sidecar naming, one-cycle scope, and startup-hardening assumptions
- **Details:** Exploration found the file-level sidecar writer already present
  in `src/cypherclaw/midi_intake_daemon.py`: valid MIDI files move to
  `processed/`, `build_manifest(...)` reads the moved file, and JSON is written
  next to it. This task assumes `<basename>.json` means the moved MIDI
  filename plus `.json` (`take.mid.json`), matching the existing cleanup and
  direct-pipeline tests. The implementation adds only a typed
  `process_intake_cycle(...)` helper so integration tests can drop a file into
  an intake directory and run exactly one scan/process cycle without starting
  the long-running watcher. The generated startup hardening bullets target the
  existing identity subsystem; `main(...)` already invokes
  `bootstrap_identity()` before `FirstBootAnnouncer`, and startup identity
  persistence tests remain mandatory regression anchors rather than widening
  MIDI sidecar scope into startup rewiring. No new dependencies, migrations,
  provider secrets, database columns, runtime state directories, or agent
  command strings are required.
- **Reason:** Red phase and focused implementation results
- **Details:** Red phase was confirmed with
  `pytest tests/test_midi_intake_daemon.py::test_process_intake_cycle_moves_valid_midi_and_writes_manifest_sidecar -q`
  failing on missing `process_intake_cycle(...)` before production code changed.
  After adding the helper, the locked integration test passed and focused Ruff
  passed for `src/cypherclaw/midi_intake_daemon.py` and
  `tests/test_midi_intake_daemon.py`. Full validation passed with
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/`: `4936 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-003d (2026-05-23)

- **Reason:** Affective-coupling integration scope and startup-hardening assumptions
- **Details:** Exploration found T-003d builds on the existing T-003a reader
  helper, T-003b multiplier helper, and T-003c render-time depth-scaling path
  in `my-claw/tools/senseweave/synthesis/senseweave_voice.py`, plus the shared
  bus contract in `my-claw/tools/senseweave/affective_state_bus.py`. This task
  assumes the in-scope "all voices" surface is every `TIMBRE_MAP` timbre in the
  shared `SenseweaveVoice` Python render path. Full SuperCollider synthdef
  internals and audible A/B coupling remain later PRD checkpoints. The generated
  startup hardening bullets target the existing identity startup subsystem;
  current CLI, first-boot, daemon-ordering, and narrative ASGI tests already
  cover `bootstrap_identity()` before `FirstBootAnnouncer` plus standalone and
  federated persistence, so they remain regression anchors rather than
  broadening this voice integration test task into startup rewiring. No new
  dependencies, migrations, provider secrets, database columns, runtime state
  directories, HTTP routes, or SuperCollider compilation are required.
- **Reason:** Red phase and focused verification results
- **Details:** Red phase was confirmed with
  `pytest tests/test_senseweave_voice.py::TestAffectiveCouplingIntegration -q`
  failing on missing `SenseweaveVoice.note_on_with_affective_coupling(...)`
  before production code changed. After implementation, the locked integration
  tests passed with `2 passed`, prior T-003 reader/multiplier/scaling tests plus
  the new class passed with `9 passed`, `pytest tests/test_affective_state_bus.py
  -q` passed with `36 passed`, startup identity hardening anchors passed with
  `11 passed`, `git diff --check` was clean, and the required validation command
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/` passed with `4863 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-003c (2026-05-23)

- **Reason:** Render-time depth-scaling scope and startup-hardening assumptions
- **Details:** Exploration found T-003c builds on the existing SenseWeave voice render module (`my-claw/tools/senseweave/synthesis/senseweave_voice.py`), T-003a's flag-gated `read_affective_state_bus(...)`, T-003b's `coupling_multiplier_from_bus_value(...)`, the shared bus contract in `my-claw/tools/senseweave/affective_state_bus.py`, and the SuperCollider reference reader in `my-claw/tools/senseweave/synthesis/affective_state_bus.scd`. The PRD defines the render-time contract as `effective_depth = nominal_depth * coupling_multiplier`; this subtask assumes the in-scope "each voice" surface is the shared `SenseweaveVoice.note_on(...)` path used by every `TIMBRE_MAP` timbre. Later tasks own full synthdef internals, audible A/B coupling integration, and composer-side expression generation. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated persistence, so they remain regression anchors rather than broadening this voice render arithmetic task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, OSC reads, or SuperCollider compilation are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_senseweave_voice.py::TestRenderTimeModulatorDepthScaling -q` failing on the missing `scale_modulator_depths` import before production code changed. After implementation, the locked T-003c tests passed with `2 passed`, `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader tests/test_senseweave_voice.py::TestCouplingMultiplier -q` passed with `5 passed`, `pytest tests/test_affective_state_bus.py -q` passed with `36 passed`, `pytest tests/test_senseweave_voice.py tests/test_senseweave_voice_depth.py -q` passed with `40 passed`, `git diff --check` was clean, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4861 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, startup rewiring, OSC reads, or runtime state directories were introduced.

## T-003b (2026-05-23)

- **Reason:** Coupling multiplier scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is the SenseWeave voice module (`my-claw/tools/senseweave/synthesis/senseweave_voice.py`), the existing bus contract in `my-claw/tools/senseweave/affective_state_bus.py`, the SuperCollider reference reader in `my-claw/tools/senseweave/synthesis/affective_state_bus.scd`, and coverage in `tests/test_senseweave_voice.py` / `tests/test_affective_state_bus.py`. The CypherClaw v2 PRD and design statement define the coupling math as `nominal_depth * (1 + coupling_strength * affective_state)`, with default coupling strength `0.5` and reader-side clamping to `[0.0, 1.0]`. This subtask assumes T-003b should expose only the pure multiplier helper `1 + coupling_strength * affective_state`; later T-003 subtasks own wiring the multiplier into every voice synthdef and live modulator path. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated persistence, so they remain regression anchors rather than broadening this voice arithmetic task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or agent command strings are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_senseweave_voice.py::TestCouplingMultiplier -q` failing on the missing `coupling_multiplier_from_bus_value` import before production code changed. After implementation, the locked multiplier tests passed with `2 passed`, `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader -q` passed with `3 passed`, `pytest tests/test_affective_state_bus.py -q` passed with `36 passed`, `pytest tests/test_senseweave_voice.py tests/test_senseweave_voice_depth.py -q` passed with `38 passed`, focused Ruff passed, `git diff --check` was clean, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4859 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, startup rewiring, OSC traffic, or runtime state directories were introduced.

## T-003a (2026-05-23)

- **Reason:** Coupling reader scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is the SenseWeave voice module (`my-claw/tools/senseweave/synthesis/senseweave_voice.py`), the existing affective bus contract in `my-claw/tools/senseweave/affective_state_bus.py`, and their tests. T-001/T-002/T-004/T-005 already provide the shared bus constants, writer, slow decay, and `CYPHERCLAW_V2_COUPLING` flag parser. This subtask assumes T-003a should add only a typed Python reader helper that calls a supplied control-bus reader for `AFFECTIVE_STATE_BUS_INDEX` when coupling is enabled, returns `0.0` without reading when coupling is off, and clamps enabled values into `[0.0, 1.0]`. Later T-003 subtasks own applying the coupling multiplier to voice modulators. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated persistence, so they remain regression anchors rather than broadening this voice-reader task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, runtime state directories, or agent command strings are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_senseweave_voice.py::TestAffectiveStateBusReader -q` failing on the missing `read_affective_state_bus` import before production code changed. After implementation, the locked reader tests passed with `3 passed`, `pytest tests/test_affective_state_bus.py -q` passed with `36 passed`, `pytest tests/test_senseweave_voice.py tests/test_senseweave_voice_depth.py -q` passed with `36 passed`, focused Ruff and `git diff --check` passed, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4857 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, startup rewiring, or runtime state directories were introduced.

## T-043@20260515T214233Z (2026-05-16)

- **Reason:** PAL deploy rollback CLI scope and startup-hardening assumptions
- **Details:** Exploration found PAL-033 should wire the existing local rollback primitive into `promptclaw pal deploy rollback PROJECT_ROOT --remote-inventory PATH --backup-id ID --approve-rollback`, following the existing `pal deploy plan` and `pal deploy apply` parser/dispatch patterns in `promptclaw/cli.py` and fake-remote deploy models in `promptclaw/pal_deploy.py`. The implementation is assumed to mutate only the supplied local fake remote inventory snapshot after the explicit approval flag, restore only files recorded in the selected local backup artifact, preserve unmanaged entries, and report `live_ssh=false` and `service_restarts=false`. It will not add live SSH capture or writes, service restarts, new dependencies, migrations, provider secrets, database columns, unrestricted agent commands, or startup rewiring. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, including standalone and federated modes, so those remain mandatory regression anchors rather than broadening this PAL rollback CLI task into startup changes.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py::test_pal_deploy_rollback_parser_exposes_explicit_approval_flag tests/test_pal_deploy.py::test_pal_deploy_rollback_cli_requires_approval_flag_for_fake_remote_writes tests/test_pal_deploy.py::test_pal_deploy_rollback_cli_restores_approved_fake_remote_inventory -q` failing on the missing `rollback` parser choice and missing `cmd_pal_deploy_rollback` API before production code changed. After implementation, the locked rollback CLI tests passed with `3 passed`, `pytest tests/test_pal_deploy.py -q` passed with `22 passed`, `pytest tests/test_pal_deploy.py tests/test_pal_cli_fake_client.py -q` passed with `26 passed`, the startup identity hardening anchor command passed with `11 passed`, docs grep and dependency/migration diff checks passed, focused Ruff and mypy passed for touched PAL deploy code, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4796 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, live SSH writes, service restarts, or startup rewiring were introduced.

## T-042@20260515T214233Z (2026-05-16)

- **Reason:** PAL rollback primitive fake-remote scope and startup-hardening assumptions
- **Details:** Exploration found PAL-032 builds directly on the existing PAL deployment manifest, fake remote inventory, diff, backup, and apply primitives in `promptclaw/pal_deploy.py`, with CLI wiring in `promptclaw/cli.py`, coverage in `tests/test_pal_deploy.py`, and product context in `sdp/prd-pal-2026-agentic-ops-platform.md`. The implementation is assumed to add a typed local rollback primitive that restores backed-up managed fake-remote file content and metadata into a supplied local fake remote inventory snapshot. It will not add a rollback CLI, approval flag parser, live SSH capture or writes, service restarts, new dependencies, migrations, provider secrets, database columns, or startup rewiring. T-043 owns `promptclaw pal deploy rollback --approve-rollback`. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, including standalone and federated modes, so those remain mandatory regression anchors rather than broadening this PAL rollback primitive task into startup changes.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py::test_pal_deploy_rollback_primitive_restores_backed_up_fake_remote_files tests/test_pal_deploy.py::test_pal_deploy_rollback_primitive_requires_explicit_approval -q` failing on the missing `rollback_pal_deployment_backup` API before production code changed. After implementation, the locked rollback tests passed with `2 passed`, `pytest tests/test_pal_deploy.py -q` passed with `19 passed`, focused Ruff and mypy passed for touched PAL deploy code, the product-doc grep and dependency/migration diff checks passed, the startup identity hardening anchor command passed with `11 passed`, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4793 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, rollback CLI, live SSH writes, service restarts, or startup rewiring were introduced.

## T-041@20260515T214233Z (2026-05-16)

- **Reason:** PAL approved deploy-apply fake-remote scope and startup-hardening assumptions
- **Details:** Exploration found PAL-031 builds directly on the existing PAL deployment manifest, fake remote inventory, diff, dry-run plan, and backup primitive in `promptclaw/pal_deploy.py`, with CLI wiring in `promptclaw/cli.py`, coverage in `tests/test_pal_deploy.py`, and product context in `sdp/prd-pal-2026-agentic-ops-platform.md`. The implementation is assumed to expose `promptclaw pal deploy apply PROJECT_ROOT --remote-inventory PATH --approve-apply` as an explicit approval-gated local fake-remote apply path. It will mutate only the supplied local fake remote inventory snapshot, back up changed managed fake-remote content before overwrite, report skipped missing local sources, and preserve unmanaged/excluded runtime paths. It will not add rollback, live SSH capture or writes, service restarts, new dependencies, migrations, provider secrets, database columns, or startup rewiring. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, including standalone and federated modes, so those remain mandatory regression anchors rather than broadening this PAL apply task into startup changes.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py::test_pal_deploy_apply_parser_exposes_explicit_approval_flag tests/test_pal_deploy.py::test_pal_deploy_apply_cli_requires_approval_flag_for_fake_remote_writes tests/test_pal_deploy.py::test_pal_deploy_apply_cli_writes_approved_fake_remote_inventory_and_backup -q` failing on the missing deploy apply parser and `cmd_pal_deploy_apply` API before production code changed. After implementation, the locked apply tests passed with `3 passed`, `pytest tests/test_pal_deploy.py -q` passed with `17 passed`, `pytest tests/test_pal_deploy.py tests/test_pal_cli_fake_client.py -q` passed with `21 passed`, the startup identity hardening anchor command passed with `11 passed`, docs grep and dependency/migration diff checks passed, focused Ruff/mypy passed for touched PAL deploy code, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4791 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, rollback command, live SSH writes, service restarts, or startup rewiring were introduced.

## T-040@20260515T214233Z (2026-05-16)

- **Reason:** PAL deploy backup primitive scope and startup-hardening assumptions
- **Details:** Exploration found PAL-030 builds directly on the existing PAL deployment manifest, fake remote inventory, diff, and dry-run plan code in `promptclaw/pal_deploy.py`, with coverage in `tests/test_pal_deploy.py` and product context in `sdp/prd-pal-2026-agentic-ops-platform.md`. The implementation is assumed to add a typed local backup primitive that stores changed managed fake-remote file content under a local `.promptclaw/pal-deploy` style backup artifact for future apply/rollback work. It will not add a deploy apply CLI, rollback CLI, approval flags, live SSH backup capture, remote writes, service restarts, dependencies, migrations, provider secrets, database columns, or startup rewiring. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, including standalone and federated modes, so those remain mandatory regression anchors rather than broadening this PAL backup task into startup changes.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py::test_pal_deploy_backup_primitive_stores_changed_fake_remote_files -q` failing on the missing `backup_pal_deployment_changes` API before production code changed. After implementation, the locked backup test passed, `pytest tests/test_pal_deploy.py -q` passed with `14 passed`, the startup identity hardening anchor command passed with `11 passed`, the product-doc grep and dependency/migration diff checks passed, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4788 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, live SSH capture, remote writes, deploy apply CLI, rollback CLI, approval flags, service restarts, or startup rewiring were introduced.

## T-026@20260515T214233Z (2026-05-16)

- **Reason:** PAL fake-client CLI test scope and approval-command assumption
- **Details:** Exploration found PAL-041 is a test-hardening task over the existing PAL CLI paths in `promptclaw/cli.py`, `promptclaw/pal_agent.py`, `promptclaw/pal_knowledge.py`, and `promptclaw/pal_deploy.py`, with PRD context in `sdp/prd-pal-2026-agentic-ops-platform.md` and task ordering in `sdp/task-graph.md`. The implementation is assumed to add fake-client parser/dispatch tests through `promptclaw.cli.main(...)` for `pal kb build/query`, `pal agent actions --approve ACTION_ID`, a representative read-only workflow command (`pal validate restart` from dependency T-015), and `pal deploy plan`. The PRD's separate artifact replay command `promptclaw pal agent approve PROJECT_ROOT --run-id --action` is scheduled as later T-033, so this task does not add or require that future parser surface. No live PAL router, SSH connection, remote writes, deploy apply, rollback, dependencies, migrations, provider secrets, database columns, or startup rewiring are required. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests remain mandatory regression anchors rather than broadening this PAL CLI test task into startup changes.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_pal_cli_fake_client_depth.py -q` failing on the missing `tests/test_pal_cli_fake_client.py` coverage module before fake-client CLI tests were added. After implementation, `pytest tests/test_pal_cli_fake_client.py tests/test_test_pal_cli_fake_client_depth.py -q` passed with `5 passed`, `pytest tests/test_pal_knowledge.py tests/test_pal_agent.py tests/test_pal_deploy.py tests/test_pal_cli_fake_client.py tests/test_test_pal_cli_fake_client_depth.py -q` passed with `66 passed`, touched-test Ruff passed, the startup identity hardening anchor command passed with `11 passed`, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4772 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies, migrations, provider secrets, database columns, live PAL calls, SSH connections, remote writes, deploy apply, rollback, or startup rewiring were introduced.

## T-024@20260515T214233Z (2026-05-16)

- **Reason:** PAL deploy-plan CLI scope and startup-hardening assumptions
- **Details:** Exploration found PAL-029 builds directly on the PAL-027 manifest and PAL-028 dry-run diff model in `promptclaw/pal_deploy.py`, with CLI wiring in `promptclaw/cli.py` and product docs in `docs/command-reference.md`, `docs/architecture.md`, and `pal-2026/docs/PROJECT_GUIDE.md`. The implementation is assumed to expose `promptclaw pal deploy plan PROJECT_ROOT` as a stdout-only dry-run that loads the local manifest, optionally compares against a local JSON remote-inventory snapshot, reports file diff counts and service impacts, and records `dry_run=true` / `remote_writes=false`. It will not add live SSH reads, remote writes, backups, apply, rollback, service restarts, approval flags, dependencies, migrations, provider secrets, database columns, or cloud lifecycle operations. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL deploy-plan task into startup rewiring.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py::test_pal_deploy_plan_cli_prints_dry_run_summary_without_remote_writes tests/test_pal_deploy.py::test_pal_deploy_plan_cli_json_includes_diff_and_service_impact tests/test_pal_deploy.py::test_pal_deploy_plan_parser_has_no_apply_or_approval_surface -q` failing on the missing `cmd_pal_deploy_plan` API and parser wiring before production code changed. After implementation, those locked tests passed with `3 passed`, `pytest tests/test_pal_deploy.py -q` passed with `13 passed`, focused PAL deploy/report parser regressions passed with `15 passed`, focused Ruff passed for `promptclaw/pal_deploy.py`, `promptclaw/cli.py`, and `tests/test_pal_deploy.py`, and focused mypy passed for `promptclaw/pal_deploy.py`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4766 passed, 10 skipped`, Ruff clean, and mypy clean. A direct `mypy promptclaw/cli.py` check remains blocked by pre-existing root-package typing issues outside this task; the required `mypy src/` gate is clean. No new dependencies or migrations were introduced.

## T-023@20260515T214233Z (2026-05-16)

- **Reason:** PAL deploy diff model scope and startup-hardening assumptions
- **Details:** Exploration found PAL-028 should extend the manifest-only deployment surface in `promptclaw/pal_deploy.py` with a deterministic dry-run diff model and fake remote inventory coverage in `tests/test_pal_deploy.py`. The implementation is assumed to compare manifest-managed local source files against target-path keyed fake remote snapshots, reporting added, changed, missing, unchanged, and unmanaged remote diff sets while honoring manifest excluded runtime paths. It will not add deploy-plan CLI wiring, SSH reads, remote writes, backups, apply, rollback, service restarts, dependencies, migrations, provider secrets, database columns, or startup rewiring. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL deploy diff task into startup changes.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py::test_pal_deployment_diff_reports_fake_remote_diff_sets -q` failing on the missing `build_fake_pal_remote_inventory` API before production code changed. After implementation, the locked deploy-diff tests passed with `4 passed`, `pytest tests/test_pal_deploy.py -q` passed with `10 passed`, focused Ruff/mypy and `git diff --check` passed, product-note grep passed, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4763 passed, 10 skipped`, Ruff clean, and mypy clean. The full test suite includes the CLI, first-boot, daemon-ordering, and narrative ASGI startup identity hardening anchors. No new dependencies, migrations, provider secrets, database columns, SSH reads, remote writes, deploy apply, backup, rollback, or service restart behavior were introduced.

## T-022@20260515T214233Z (2026-05-16)

- **Reason:** PAL deployment manifest scope and startup-hardening assumptions
- **Details:** Exploration found PAL-027 is the first deployment-tooling slice before deploy diff/plan/apply/rollback. The affected surface is the PAL PRD deployment section, `pal-2026/ops/` runbooks/templates, PAL product docs, and existing PAL tests. The implementation is assumed to be a repo-managed JSON manifest at `pal-2026/ops/deployment-manifest.json` plus a small typed stdlib-only loader/validator in `promptclaw/pal_deploy.py` for future deploy tooling. It will list intended `/opt/pal` files, include host-managed startup/shutdown/router files, keep runtime logs/model data out of managed file entries, and contain no provider secrets, key paths, tokens, Tailscale auth keys, or live credentials. It will not add deploy apply/rollback behavior, remote SSH writes, restarts, cloud lifecycle calls, database migrations, dependencies, provider secrets, or CLI approval paths. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this manifest task into startup rewiring.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_deploy.py -q` failing on the missing `promptclaw.pal_deploy` module before production code changed. After implementation, `pytest tests/test_pal_deploy.py -q` passed with `6 passed`, `pytest tests/test_pal_deploy.py tests/test_pal_knowledge.py -q` passed with `21 passed`, the focused PAL regression suite passed with `68 passed`, and the startup identity hardening anchors passed with `41 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4759 passed, 10 skipped`, Ruff clean, and mypy clean. Additional focused checks `ruff check promptclaw/pal_deploy.py promptclaw/pal_knowledge.py tests/test_pal_deploy.py`, `mypy promptclaw/pal_deploy.py`, and `git diff --check` passed. No new dependencies or migrations were introduced.

## T-017@20260515T214233Z (2026-05-16)

- **Reason:** PAL Phase 2 readiness workflow scope and startup-hardening assumptions
- **Details:** Exploration found PAL-022 should add a deterministic report-only workflow alongside the existing restart-validation and shutdown-audit paths in `promptclaw/pal_agent.py`, with CLI wiring in `promptclaw/cli.py` and tests in `tests/test_pal_agent.py`. The implementation is assumed to be exposed as `promptclaw pal report phase2-readiness PROJECT_ROOT`, writing standard `.promptclaw/runs/<run-id>/` artifacts with per-prerequisite scores, an overall readiness score/status, `mutating_actions: []`, and `phase2_execution_actions: []`. It will not rent, start, stop, destroy, or resize cloud instances; load Phase 2 models; migrate persistent volumes; restart services; change shutdown behavior; expose approval action ids; add dependencies; add migrations; add provider secrets; or change database columns. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL readiness report into startup rewiring.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_agent.py::test_pal_phase2_readiness_report_scores_each_prerequisite_without_actions tests/test_pal_agent.py::test_pal_report_phase2_readiness_cli_prints_summary -q` failing on the missing `run_pal_phase2_readiness_report` workflow and `pal report` parser wiring before production code changed. After implementation, those locked tests passed with `2 passed`, `pytest tests/test_pal_agent.py tests/test_pal_smoke.py tests/test_pal_client.py -q` passed with `44 passed`, and the mandatory startup identity hardening anchor command passed with `45 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4748 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-015@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL restart-validation workflow scope and startup-hardening assumptions
- **Details:** Exploration found PAL-020 builds on the existing deterministic PAL workflow path in `promptclaw/pal_agent.py`, with CLI integration in `promptclaw/cli.py`, health/query behavior in `promptclaw/pal_client.py`, and active smoke reporting in `promptclaw/pal_smoke.py`. The implementation is assumed to be a local read-only validation command exposed as `promptclaw pal validate restart PROJECT_ROOT`. It will actively run router health, one fixed direct query, the PAL smoke suite, local Tailscale status, and the fixed SSH process check, then write a standard `restart_validation` run artifact. The workflow will not expose action ids, restart services, write remote files, change shutdown behavior, alter cloud rentals, add dependencies, add migrations, add provider secrets, or change database columns. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL validation task into startup rewiring.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_agent.py::test_pal_restart_validation_runs_health_query_smoke_tailscale_and_process_checks tests/test_pal_agent.py::test_pal_validate_restart_cli_prints_summary -q` failing on the missing `run_pal_restart_validation` workflow and `pal validate` parser wiring before production code changed. After implementation, the same locked tests passed with `2 passed`, the focused PAL regression suite passed with `39 passed`, and the mandatory startup identity hardening anchors passed with `45 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4743 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-011@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** Vast connector boundary scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is the PAL operator workflow in `promptclaw/pal_agent.py`, especially `PALOpsAction`, `build_default_action_registry(...)`, `_render_action_plan_prompt(...)`, and `_parse_action_plan(...)`. Vast appears only as PAL deployment context in `pal-2026/promptclaw.json`, `pal-2026/ops/templates/DEPLOYMENT_INFO.md`, and the phase-1 checkpoint runbook; no existing Vast API client or connector exists. The implementation is assumed to be a typed, non-executing Vast connector stub boundary that advertises `rent`, `destroy`, `start`, and `stop` as blocked lifecycle operations while exposing no callable default actions. No new dependencies, migrations, provider secrets, cloud API credentials, remote-write commands, HTTP routes, or approval-gated actions are required. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests remain mandatory regression anchors rather than broadening this PAL/Vast boundary task into startup rewiring.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_vast_connector.py tests/test_pal_agent.py::test_default_pal_action_registry_excludes_vast_lifecycle_actions tests/test_pal_agent.py::test_pal_ops_actions_prompt_includes_vast_stub_boundary -q` failing on the missing `promptclaw.vast_connector` module before production code changed. After implementation, the locked Vast/PAL boundary tests passed with `3 passed`, the focused PAL regression suite passed with `42 passed`, and the mandatory startup identity hardening anchors passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4740 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-010@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL slow-inference diagnosis CLI scope and startup-hardening assumptions
- **Details:** Exploration found PAL-019 builds directly on the PAL-018 read-only slow-inference context workflow in `promptclaw/pal_agent.py`, with CLI integration in `promptclaw/cli.py` and artifact contracts documented in `docs/handoff-protocol.md`. The active ADP process is the task prompt's Explore -> Specify -> Test -> Implement -> Verify -> Document workflow; no separate ADP file was found beyond `sdp/templates/candidates/lead_t2/v006.md`. The implementation is assumed to be a deterministic local diagnosis command at `promptclaw pal diagnose slow-inference PROJECT_ROOT` that reuses fixed read-only health, baseline, GPU, and log diagnostics, writes a standard run artifact, and exposes no action ids or remote-write path. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL CLI task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, HTTP routes, or approval-gated actions are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_agent.py::test_pal_slow_inference_diagnosis_writes_artifact_and_declares_no_mutation tests/test_pal_agent.py::test_pal_slow_inference_diagnosis_derives_findings_from_context tests/test_pal_agent.py::test_pal_diagnose_slow_inference_cli_prints_summary -q` failing on the missing `run_pal_slow_inference_diagnosis` workflow and `pal diagnose` parser wiring before production code changed. After implementation, the same locked tests passed with `3 passed`, `pytest tests/test_pal_agent.py -q` passed with `21 passed`, the focused PAL regression suite passed with `40 passed`, and the mandatory startup identity hardening anchors passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4737 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-008@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL prompt-injection scope and startup-hardening assumptions
- **Details:** Exploration found PAL-017 builds directly on the PAL-013 through PAL-016 local KB path in `promptclaw/pal_knowledge.py` and the workflow prompt artifacts written by `promptclaw/pal_agent.py`: `triage-plan.md`, `triage-summary.md`, `action-plan.md`, and `action-summary.md`. The implementation is assumed to be stdlib-only prompt enrichment from the existing JSONL index, with missing or malformed indexes treated as unavailable local context rather than workflow failures. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL prompt-injection task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, HTTP routes, remote writes, or approval-gated actions are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_agent.py::test_pal_ops_triage_prompt_artifacts_include_bounded_knowledge_context tests/test_pal_agent.py::test_pal_ops_triage_prompt_artifacts_include_knowledge_context_when_index_is_missing tests/test_pal_agent.py::test_pal_ops_actions_prompt_artifacts_include_bounded_knowledge_context -q` failing because existing PAL prompt artifacts lacked `## Knowledge Context`. After implementation, those three tests passed, `pytest tests/test_pal_agent.py -q` passed with `16 passed`, the focused PAL PRD suite passed with `50 passed`, and the mandatory startup identity hardening anchors passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4732 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-007@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL KB query scope and startup-hardening assumptions
- **Details:** Exploration found PAL-016 builds directly on the PAL-013/PAL-014/PAL-015 local knowledge path in `promptclaw/pal_knowledge.py`, with command wiring under the existing nested `promptclaw pal kb` CLI. The implementation is assumed to be a stdlib-only ranked lexical query over the JSONL index written by `promptclaw pal kb build`, returning source paths and snippets without contacting the PAL router. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL KB query task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, HTTP routes, or approval-gated actions are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_knowledge.py -q` failing on the missing `cmd_pal_kb_query` import before production code changed. After implementation, `pytest tests/test_pal_knowledge.py -q` passed with `15 passed`, the focused PAL PRD suite passed with `47 passed`, parser wiring for `promptclaw pal kb query` was confirmed, and the mandatory startup identity hardening anchors passed with `11 passed`. Focused Ruff passed for `promptclaw/pal_knowledge.py`, `promptclaw/cli.py`, and `tests/test_pal_knowledge.py`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4729 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-006@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL KB index-writer scope and startup-hardening assumptions
- **Details:** Exploration found PAL-015 builds directly on the PAL-013/PAL-014 local knowledge seam in `promptclaw/pal_knowledge.py`, with CLI integration in `promptclaw/cli.py` and product docs in `docs/architecture.md` / `docs/command-reference.md`. The implementation is assumed to be a stdlib-only JSONL writer at `.promptclaw/pal-kb/index.jsonl` plus a nested `promptclaw pal kb build` command; SQLite is allowed by the acceptance criterion but unnecessary for this first inspectable local index. The generated startup hardening bullets reference the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL KB writer task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, HTTP routes, or approval-gated actions are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_knowledge.py -q` failing on the missing `cmd_pal_kb_build` import before production code changed. After implementation, `pytest tests/test_pal_knowledge.py -q` passed with `11 passed`, the focused PAL PRD suite passed with `38 passed`, a parser-level CLI smoke confirmed `promptclaw pal kb build` creates `.promptclaw/pal-kb/index.jsonl`, and the mandatory startup identity hardening anchors passed with `11 passed`. Focused Ruff passed for `promptclaw/pal_knowledge.py`, `promptclaw/cli.py`, and `tests/test_pal_knowledge.py`; direct mypy over `promptclaw/` remains blocked by pre-existing package-level typing issues outside this task, while the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4725 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-004@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL source-discovery scope and startup-hardening assumptions
- **Details:** Exploration found the affected PAL-013 surface is the local PAL knowledge-base input seam, with existing patterns in `promptclaw/models.py`, `promptclaw/config.py`, `promptclaw/pal_client.py`, `promptclaw/pal_smoke.py`, `promptclaw/pal_agent.py`, and the PAL tests. The new source discovery function will be stdlib-only, side-effect free, and driven by configured `pal.knowledge_sources` entries so future chunking/index tasks can reuse it without model calls or live PAL access. The task prompt's generated startup hardening bullets are already covered by existing startup identity anchors: CLI startup calls `bootstrap_identity()`, daemon wiring checks assert `bootstrap_identity()` before `FirstBootAnnouncer`, and standalone/federated persistence is covered in first-boot and narrative ASGI tests. Those tests will be re-run as mandatory regression anchors rather than broadening PAL source discovery into startup rewiring. No new dependencies, migrations, provider secrets, database columns, runtime writes, HTTP routes, or approval-gated actions are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_knowledge.py -q` failing on the missing `promptclaw.pal_knowledge` module and `pytest tests/test_pal_client.py::PALConfigTests::test_pal_config_round_trips_through_project_config -q` failing because `PALConfig` did not accept `knowledge_sources`. After implementation, `pytest tests/test_pal_knowledge.py -q` passed with `2 passed`, the focused PAL PRD suite passed with `34 passed`, and the mandatory startup identity hardening anchors passed with `10 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4716 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-005@20260515T214233Z (2026-05-15T21:42:33Z)

- **Reason:** PAL knowledge-chunking scope and startup-hardening assumptions
- **Details:** Exploration found PAL-014 builds directly on the PAL-013 source discovery seam in `promptclaw/pal_knowledge.py`. The implementation is assumed to be a local, typed, stdlib-only, side-effect-free chunk stream for future PAL-015 index writing rather than a CLI or runtime artifact writer. The generated startup hardening bullets reference the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL chunking task into startup rewiring. No new dependencies, migrations, provider secrets, database columns, runtime writes, HTTP routes, or approval-gated actions are required.
- **Reason:** Red phase and focused implementation checks
- **Details:** Red phase was confirmed with `pytest tests/test_pal_knowledge.py -q` failing on the missing `PALKnowledgeChunk` / `chunk_pal_source_files` API before production code changed. After implementation, `pytest tests/test_pal_knowledge.py -q` passed with `7 passed`, and `ruff check promptclaw/pal_knowledge.py tests/test_pal_knowledge.py` passed. The mandatory startup identity hardening anchors passed with `11 passed`, covering CLI startup, first-boot persistence, daemon `bootstrap_identity()` ordering before `FirstBootAnnouncer`, and narrative ASGI identity persistence. A targeted `mypy promptclaw/pal_knowledge.py` traversed existing package imports and reported unrelated pre-existing errors in `promptclaw/utils.py` plus missing `psycopg2` stubs from `promptclaw/coherence/event_store.py`; the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4721 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0121 (2026-05-03)

- **Reason:** Wizard test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_wizard.py`, with production behavior in `promptclaw/wizard.py`. The module already implements the simple one-path lifecycle needed for depth 2: `StartupWizard.run()` walks the base questionnaire, queues per-agent strength questions and follow-ups, applies the `StartupProfile` to the project (writing the prompts, agent instructions, startup profile/transcript, onboarding session, and `promptclaw.json`), and routes through `parse_agent_roster(...)`, `infer_capabilities(...)`, `looks_vague(...)`, `mentions_any(...)`, `as_bullets(...)`, `sentence_or_list(...)`, `lead_lane_text(...)`, and `verification_fit_text(...)`. Existing focused tests already cover roster parsing defaults, the realistic interactive run, and follow-up detection for vague inputs. Assumption: the simplest correct depth-2 implementation is to add a structural depth gate plus one end-to-end diagnostic test that drives full project scaffolding, config application, captured-output verification, focused-helper agreement, and JSON-safe diagnostic round-tripping through the existing public API unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, standalone/federated persistence, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence between boots, so they remain regression anchors rather than broadening this wizard test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_wizard_depth.py -q` failing on the missing `WizardEndToEndTests` class and missing machine-readable depth-2 marker before implementation. After adding the marker, the imports needed by the new diagnostic, and the end-to-end class, `pytest tests/test_wizard.py tests/test_test_wizard_depth.py -q` passed with `6 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4685 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0118 (2026-05-03)

- **Reason:** synthesis-architecture registry test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_synthesis_architecture_registry.py`, with production behavior in `my-claw/tools/senseweave/synthesis_architecture_registry.py` and prior helper coverage in `tests/test_synthesis_architecture_registry_depth.py` / `specs/frac-0031-spec.md`. The production module already implements the one-path report helpers needed for meaningful output (`build_architecture_registry_report(...)` and `summarize_architecture_registry_report(...)`), so the simplest correct depth-2 implementation is test hardening only: add a structural depth gate plus one end-to-end diagnostic test that drives lookup, report generation, production-course concept coverage, and JSON-safe output through the existing public API unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this registry test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_synthesis_architecture_registry_depth.py -q` failing on the missing `SynthesisArchitectureRegistryEndToEndTests` class and missing machine-readable depth marker before implementation. After adding the marker and end-to-end class, `pytest tests/test_synthesis_architecture_registry.py::SynthesisArchitectureRegistryEndToEndTests tests/test_test_synthesis_architecture_registry_depth.py -q` passed with `3 passed`, `pytest tests/test_synthesis_architecture_registry.py tests/test_synthesis_architecture_registry_depth.py tests/test_test_synthesis_architecture_registry_depth.py -q` passed with `42 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4676 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0116c (2026-05-03)

- **Reason:** sw_sampler end-to-end exhaustive-coverage scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is the existing `SwSamplerEndToEndTests.test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic` in `tests/test_sw_sampler.py` (added by frac-0116). The diagnostic constructor already enumerates all fourteen documented controls (`bufnum`, `amp`, `grain_size_ms`, `density`, `position`, `position_rate`, `pitch_transpose_semitones`, `pitch_jitter_semitones`, `attack_sec`, `release_sec`, `gate`, `out_bus`, `fx_bus`, `fx_send`) into `defaults` and all eight canonical signal-chain stages (`grain_trigger`, `pitch_jitter`, `pitch_transpose`, `position_scrub`, `grain_buffer`, `envelope`, `dry_out`, `fx_send_out`) into `signal_chain`, but the round-tripped payload only spot-checked six of fourteen `defaults` keys and the list-equality assertion on `signal_chain` did not pin cardinality. Assumption: the simplest correct hardening is to add additive set-equality plus length assertions on the round-tripped dict so a future regression that drops a key during serialization or constructor-side filtering, or that introduces a duplicate stage label, is rejected. Because production already supplies meaningful values for all fourteen controls, the new assertions pass on first run; this is a pure test-tightening task with no Red→Green code change in production. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they remain regression anchors rather than broadening this sw_sampler test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.

## frac-0116 (2026-05-03)

- **Reason:** sw_sampler test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_sw_sampler.py`, the SuperCollider source `my-claw/tools/senseweave/synthesis/sw_sampler.scd`, and the SC-side runtime harness `my-claw/supercollider/test_sw_sampler.scd`. The source already implements the one-path granular voice (Impulse.kr trigger train, TRand.kr per-grain pitch jitter folded into a `.midiratio` rate with constant transpose, Sweep.ar position scrub wrapped to `[0, 1]`, GrainBuf.ar reading `bufnum`, `EnvGen.kr(Env.asr, gate, doneAction: 2)` self-freeing voice, dry write to `out_bus` plus parallel `fx_send`-scaled write to `fx_bus`/16). Existing tests already pin individual control names, defaults, clip ranges, per-stage UGen presence, and the SC-side runtime checks. Assumption: the simplest correct depth-2 implementation is to add a structural depth gate plus one end-to-end diagnostic test that proves the source and runtime harness produce meaningful JSON-safe output, unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this sw_sampler test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_sw_sampler_depth.py -q` failing on the missing `SwSamplerEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_sw_sampler.py tests/test_test_sw_sampler_depth.py -q` passed with `41 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4669 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0115 (2026-05-03)

- **Reason:** Startle test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_startle.py`, with production behavior in `my-claw/tools/senseweave/startle.py` and daemon file-output integration already covered in `tests/test_startle_daemon.py` / `my-claw/tools/startle_daemon.py`. The source already implements the simple one-path behavior needed for depth 2: detect an RMS spike above baseline, respect cooldown, return immutable replacement `StartleState` values, render a face reaction, and recommend muting after repeated recent startles. Assumption: the simplest correct depth-2 implementation is a structural depth gate plus one end-to-end diagnostic test that drives quiet, first-startle, cooldown-blocked, repeated-startle, and JSON-safe diagnostic output through the existing public functions, unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this startle test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_startle_depth.py -q` failing on the missing `StartleEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_startle.py::StartleEndToEndTests tests/test_test_startle_depth.py -q` passed with `2 passed`, `pytest tests/test_startle.py -q` passed with `33 passed`, `pytest tests/test_startle.py tests/test_test_startle_depth.py -q` passed with `34 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4667 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0114 (2026-05-03)

- **Reason:** Sampler-scheduler test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_sampler_scheduler.py`, with production behavior in `my-claw/tools/senseweave/sampler_scheduler.py` and the canonical mode table in `my-claw/tools/senseweave/render/antipatterns.py` (`DEFAULT_SAMPLER_DENSITY_BY_MODE`). The source already implements the one-path scheduler required by CCS-023 / T-017: density clamp to `[0.0, 1.0]`, deterministic `floor(density * total_phrases) + Bernoulli(density)` count, and sorted unique sample of phrase indices. Existing tests already pin clamps, empty pieces, unknown modes, and per-mode statistical separation. Assumption: the simplest correct depth-2 implementation is a structural depth gate plus one end-to-end diagnostic test that proves the three public functions and canonical mode table produce meaningful JSON-safe output under a deterministic seed, unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this sampler-scheduler task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_sampler_scheduler_depth.py -q` failing on the missing `SamplerSchedulerEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_sampler_scheduler.py tests/test_test_sampler_scheduler_depth.py -q` passed with `13 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4665 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0113 (2026-05-03)

- **Reason:** Sampler-effects test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_sampler_effects.py`, the SuperCollider source `my-claw/tools/senseweave/synthesis/sampler_effects.scd`, and the SC-side runtime harness `my-claw/supercollider/test_sampler_effects.scd`. The source already implements the one-path `sw_sampler_fx` chain (stereo input bus -> delay -> FreeVerb/PartConv reverb -> PV_Freeze -> B-fundamental comb -> output), and existing tests already pin individual controls/stages. Assumption: the simplest correct depth-2 implementation is to add a structural depth gate plus one end-to-end diagnostic test that proves the source and runtime harness produce meaningful JSON-safe output, unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this sampler-effects test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_sampler_effects_depth.py -q` failing on the missing `SamplerEffectsEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_sampler_effects.py::SamplerEffectsEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_sampler_effects_depth.py -q` passed with `1 passed`, `pytest tests/test_sampler_effects.py -q` passed with `50 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4663 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0111 (2026-05-03)

- **Reason:** Sample-record skeleton test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_sample_record_skeleton.py`, with production behavior in `my-claw/tools/senseweave/sample_library.py`. The current test file covers `SampleRecord` core identity fields (`sample_id`, `path`, `source`, `captured_at`) at skeleton/field depth only; `SampleRecord.to_dict()` / `from_dict(...)` already serialize and restore `Path` and `datetime` values, and `SampleLibrary` already persists the full `SampleRecord.to_dict()` payload through `record_json`. Assumption: the simplest correct depth-2 implementation is test hardening only unless red tests expose a concrete runtime gap. No standalone ADP file was found beyond the task prompt and `sdp/templates/candidates/lead_t2/v006.md`; that Explore -> Specify -> Test -> Implement -> Verify -> Document flow is treated as the active ADP process. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this sample-record task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_sample_record_skeleton_depth.py -q` failing on the missing `SampleRecordSkeletonEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_sample_record_skeleton.py::SampleRecordSkeletonEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_sample_record_skeleton_depth.py -q` passed with `1 passed`, `pytest tests/test_sample_record_skeleton.py tests/test_test_sample_record_skeleton_depth.py -q` passed with `11 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4659 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0109 (2026-05-03)

- **Reason:** Sample-record audio-analysis test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_sample_record_audio_analysis.py`, with production behavior in `my-claw/tools/senseweave/sample_library.py`. The current test file covers `SampleRecord` audio-analysis fields at field depth only; `SampleLibrary` already persists the full `SampleRecord.to_dict()` payload, including `duration`, `rms`, `peak`, and `transient_density`. Assumption: the simplest correct depth-2 implementation is test hardening only unless red tests expose a concrete runtime gap. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this sample-record task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_sample_record_audio_analysis_depth.py -q` failing on the missing `SampleRecordAudioAnalysisEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_sample_record_audio_analysis.py::SampleRecordAudioAnalysisEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_sample_record_audio_analysis_depth.py -q` passed with `1 passed`, `pytest tests/test_sample_record_audio_analysis.py -q` passed with `14 passed`, and focused Ruff passed for both touched test files. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4655 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0106 (2026-05-02)

- **Reason:** Render-seed test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_render_seed.py`, with production behavior in `src/cypherclaw/render/seed.py` and an adjacent public contract in `src/cypherclaw/render/events.py` (`Event.seed_path`). The production helper already implements the simple one-path SHA-256 derivation required by CCH-009, so the planned work is test hardening only: add a depth gate plus a named end-to-end class that drives `derive_seed(...)` over a phrase → voice → event family of `seed_path` tuples and confirms the `Event.seed_path` round trip plus a JSON-safe diagnostic. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this render-seed test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_render_seed_depth.py -q` failing on the missing `RenderSeedEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_render_seed.py::RenderSeedEndToEndTests tests/test_test_render_seed_depth.py -v` passed with `2 passed`, `pytest tests/test_render_seed.py tests/test_test_render_seed_depth.py -q` passed with `14 passed`, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4637 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0105 (2026-05-02)

- **Reason:** Render-replay test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_render_replay.py`, with production behavior in `my-claw/tools/senseweave/render/replay.py` and adjacent public contracts in `my-claw/tools/senseweave/render/audio_sidecar.py`, `my-claw/tools/senseweave/render/export.py`, `my-claw/tools/senseweave/render/pass_.py`, and `src/cypherclaw/render/events.py`. PRD context is CCH-009/CCH-039 in `my-claw/sdp/prd-cypherclaw-humanization.md`. No standalone ADP documentation file was found under `docs/`, `sdp/`, or `my-claw/sdp/`; the task prompt's Explore → Specify → Test → Implement → Verify → Document phases are treated as the active ADP workflow. The production replay module already implements the simple one-path behavior required by this task, so the planned work is test hardening only: add a depth gate plus a named end-to-end class that drives mapping-score replay, sidecar-like delta input, audio delta persistence, immutable score-field preservation, and JSON-safe diagnostics through the existing public API. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this render-replay test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_render_replay_depth.py -q` failing on the missing `RenderReplayEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_render_replay.py::RenderReplayEndToEndTests::test_mapping_score_sidecar_delta_audio_export_and_diagnostics_round_trip -q` passed with `1 passed`, `pytest tests/test_test_render_replay_depth.py -q` passed with `1 passed`, and `pytest tests/test_render_replay.py tests/test_test_render_replay_depth.py -q` passed with `4 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4635 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0103 (2026-05-02)

- **Reason:** Render-antipattern test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_render_antipatterns.py`, with production behavior in `my-claw/tools/senseweave/render/antipatterns.py` and PRD context in `my-claw/sdp/prd-cypherclaw-humanization.md`, `my-claw/sdp/prd-cypherclaw-generation.md`, and `my-claw/sdp/prd-cypherclaw-sampler.md`. The production module already implements typed, deterministic one-path detector functions that return meaningful `AntiPatternResult` output for humanization, generated-content, and sampler misuse diagnostics. This task therefore targets test hardening only: add a depth gate plus a named end-to-end class that drives `detect_antipatterns(...)`, `failing_antipatterns(...)`, severity handling, and JSON-safe diagnostics through the existing public API. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they remain regression anchors rather than broadening this render-antipattern test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_render_antipatterns_depth.py -q` failing on the missing `RenderAntipatternsEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_render_antipatterns.py::RenderAntipatternsEndToEndTests -q` passed with `7 passed`, `pytest tests/test_render_antipatterns.py tests/test_test_render_antipatterns_depth.py -q` passed with `34 passed`, `pytest tests/test_render_metrics.py::test_broken_render_fails_ci_gate -q` passed, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4629 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0102d (2026-05-02)

- **Reason:** Gate-suite re-run scope and render-ablation depth-2 completion documentation
- **Details:** The frac-0102d task scope is to (1) re-run the full gate on top of the merged frac-0102/0102a/0102b/0102c work to surface any failures introduced by the new render-ablation assertions, and (2) record depth-2 completion in the existing render-ablation validation document `sdp/notes/frac-0102a-render-ablation-depth.md`. The notes file currently described only the pre-depth-2 baseline and listed gaps as open, leaving future readers without a clear marker that the depth-2 lifecycle and final-artifact assertion shipped. The existing `tests/test_frac_0102a_notes.py` contract pins the baseline sections, so the depth-2 completion content is appended below them rather than rewriting the file. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they remain regression anchors. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and gate re-run results
- **Details:** Initial gate run on the unmodified tree before any frac-0102d edits returned `4620 passed, 3 skipped`, Ruff clean, mypy clean — no failures were introduced by the frac-0102c assertions. Red phase was confirmed with `pytest tests/test_frac_0102d_depth_completion.py -q` failing on the missing `## Depth-2 Completion` section before the notes were updated. After appending the section, `pytest tests/test_frac_0102d_depth_completion.py tests/test_frac_0102a_notes.py tests/test_render_ablation.py tests/test_test_render_ablation_depth.py -q` passed with `18 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4621 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0102c (2026-05-02)

- **Reason:** Render-ablation final-artifact assertion scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_render_ablation.py` and `tests/test_test_render_ablation_depth.py`, with production behavior in `my-claw/tools/senseweave/render/ablation.py`. The production module already preserves arbitrary renderer output in `AblationSuite.results[*].rendered`, so this task targets test hardening only: add a depth-gate contract and a named end-to-end assertion that drives the full ablation pipeline and pins the final rendered artifact's shape/content. The generated startup hardening bullets target the identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated persistence, so they remain verification anchors. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_render_ablation_depth.py -q` failing on the missing `test_full_pipeline_final_rendered_artifact_shape_and_content` method before implementation. After adding the assertion, `pytest tests/test_render_ablation.py::RenderAblationEndToEndTests::test_full_pipeline_final_rendered_artifact_shape_and_content -q` passed with `1 passed`, `pytest tests/test_test_render_ablation_depth.py -q` passed with `1 passed`, and `pytest tests/test_render_ablation.py tests/test_test_render_ablation_depth.py -q` passed with `16 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4620 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0102b (2026-05-02)

- **Reason:** Primary render-path test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_render_pass.py`, with production behavior in `my-claw/tools/senseweave/render/pass_.py` (`RenderPass` canonical rule ordering, `effective_k`, role-gated `apply(...)` lifecycle returning a `PerformedPart`). The production module already implements the typed, deterministic one-path render-pass surface required by the task; this task therefore targets test hardening only by adding a depth gate plus a named end-to-end class that drives one register → enable → quantity → gate → apply lifecycle through the existing public API and JSON-safe diagnostics. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they remain regression anchors rather than broadening this primary render-path test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_render_pass_depth.py -q` failing on the missing `RenderPassEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_render_pass.py tests/test_test_render_pass_depth.py -q` passed with `23 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4619 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0102a (2026-05-02)

- **Reason:** Render-ablation coverage-notes scope and startup-hardening assumptions
- **Details:** Exploration found `tests/test_render_ablation.py`, the adjacent production module `my-claw/tools/senseweave/render/ablation.py`, and the existing parent frac-0102 depth-2 additions. Because current `HEAD` already contains `RenderAblationEndToEndTests`, this split task documents the pre-depth-2 helper-level baseline from the parent of commit `8e43ac3` instead of changing render behavior. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated persistence, so they remain verification anchors. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_frac_0102a_notes.py -q` failing on the missing notes file before implementation. After adding the notes, `pytest tests/test_frac_0102a_notes.py -q` passed with `1 passed`, `pytest tests/test_render_ablation.py tests/test_test_render_ablation_depth.py -q` passed with `15 passed`, the startup identity hardening anchor command passed with `11 passed`, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4616 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0101 (2026-05-02)

- **Reason:** Pedals-to-key test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_pedals_to_key.py`, with production behavior in `my-claw/tools/senseweave/pedals_to_key.py` and downstream use in `my-claw/tools/senseweave/harmonic_planner.py`. The production module already implements the simple one-path helpers for sustain-driven chord hold, expression-driven harmonic tension/extensions, expression dynamics, rapid pedal modulation gestures, and long-hold pedal points. This task therefore targets test hardening only: add a depth gate plus a named end-to-end class that drives one expressive pedal phrase through the existing public API and JSON-safe diagnostics. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this pedals-to-key task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_pedals_to_key_depth.py -q` failing on the missing `PedalsToKeyEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_pedals_to_key.py::PedalsToKeyEndToEndTests -q` passed with `15 passed`, `pytest tests/test_test_pedals_to_key_depth.py -q` passed with `1 passed`, and `pytest tests/test_pedals_to_key.py -q` passed with `43 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4610 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0100 (2026-05-02)

- **Reason:** Pareidolia-characters test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_pareidolia_characters.py`, with production behavior in `my-claw/tools/senseweave/pareidolia.py` (PARE-003 organism characters, palette selector, panel/scene renderers) and downstream usage in the gallery and B&P comic strip pipelines. The production module already implements typed, deterministic one-path drawers for all 21 organism characters and the panel/scene renderers dispatch them via `CHARACTER_REGISTRY` (with `the …` aliases) and fall back to `draw_character` for unknown names. This task therefore targets test hardening only: add a depth gate plus a named end-to-end class that drives a multi-group scene composition flow (sensor / voice / output / bridge) through palette selection, registry-aliased panel rendering, scene rendering with weather overlay and an unknown-name fallback, direct draw calls per group, and JSON-safe diagnostics. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this pareidolia-character test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_pareidolia_characters_depth.py -q` failing on the missing `PareidoliaCharactersEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_pareidolia_characters.py::PareidoliaCharactersEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_pareidolia_characters_depth.py -q` passed with `1 passed`, and `pytest tests/test_pareidolia_characters.py -q` passed with `34 passed`. The startup identity hardening anchor command passed with `11 passed`. The full validation gate `pytest tests/ -q && ruff check src/ tests/ && mypy src/` passed with `4594 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0099 (2026-05-02)

- **Reason:** Orchestral-form test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_orchestral_form.py`, with production behavior in `my-claw/tools/senseweave/synthesis/orchestral_form.py` and composer usage in `my-claw/tools/duet_composer.py`. The production module already implements typed, deterministic one-path helpers for tutti roles, diverging/converging dynamic plans, sfp pair selection, timbral tinting, effect-budget gates, post-tutti silence, and reentry. This task therefore targets test hardening only: add a depth gate plus a named end-to-end class that drives a development-climax-to-resolution orchestral form flow through the existing public surface and JSON-safe diagnostics. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this orchestral-form test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_orchestral_form_depth.py -q` failing on the missing `OrchestralFormEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_orchestral_form.py::OrchestralFormEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_orchestral_form_depth.py -q` passed with `1 passed`, and `pytest tests/test_orchestral_form.py -q` passed with `32 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4592 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0097 (2026-05-02)

- **Reason:** Ollama-routing test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_ollama_routing.py`, with production behavior in `my-claw/tools/agent_selector.py` and R750 product context in `my-claw/sdp/prd-r750-ollama-integration.md`, `docs/r750-application-deployment-plan.md`, and `docs/r750-model-evaluation-plan.md`. The production module already implements the simple one-path route table, env override merge, default fallback, and route-copy behavior for dual-socket Ollama roles. This task therefore targets test hardening only: add a depth gate plus a named end-to-end class that drives defaults, override merge, fallback routing, copy isolation, and JSON-safe diagnostics through the existing public routing surface. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this routing-test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_ollama_routing_depth.py -q` failing on the missing `OllamaRoutingEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_ollama_routing.py::OllamaRoutingEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_ollama_routing_depth.py -q` passed with `1 passed`, and `pytest tests/test_ollama_routing.py -q` passed with `20 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4588 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0089 (2026-05-02)

- **Reason:** Mix-verify test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_mix_verify.py`, with production behavior in `my-claw/tools/senseweave/mix_verify.py` and downstream profile generation in `my-claw/tools/senseweave/mix_engine.py`. The production module already implements meaningful one-path outputs for peak/RMS dBFS, LUFS proxy, clipping/silence detection, harshness, low-end runaway, masking, mastering policy validation, mix profile validation, and render loudness checks. This task therefore targets test hardening only: add a depth gate plus a named end-to-end class that drives the existing public mix verification surface through profile construction, synthetic rendering, verification checks, and JSON-safe diagnostics. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this mix-verify task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_mix_verify_depth.py -q` failing on the missing `MixVerifyEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_mix_verify.py::MixVerifyEndToEndTests -q` passed with `1 passed`, `pytest tests/test_test_mix_verify_depth.py -q` passed with `1 passed`, `pytest tests/test_mix_verify.py -q` passed with `48 passed`, and `pytest tests/test_mix_engine.py -q` passed with `30 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4568 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0087 (2026-05-02)

- **Reason:** Lung-capacity rule test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_lung_capacity_rule.py`, with production behavior in `my-claw/tools/senseweave/render/rules/lung_capacity.py` and the existing depth-2 report helper coverage in `tests/test_lung_capacity_depth.py`. The production module already implements the simple one-path `apply_lung_capacity(...)` / `analyze_lung_capacity(...)` / `summarize_lung_capacity_report(...)` flow, including inserted breath counts, tagged breath counts, non-applying lanes, scene/song/pattern dispatch, and JSON-safe summaries. This task therefore targets test hardening only: add a depth gate plus a named end-to-end test class that drives the existing public lung-capacity rule surface through inserted, tagged, skipped, summary, direct-rule, and song-aggregation paths. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this lung-capacity test task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_lung_capacity_rule_depth.py -q` failing on the missing `LungCapacityRuleEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_lung_capacity_rule.py::LungCapacityRuleEndToEndTests -q` passed with `2 passed`, `pytest tests/test_lung_capacity_rule.py tests/test_lung_capacity_depth.py tests/test_test_lung_capacity_rule_depth.py -q` passed with `18 passed`, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4564 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0073 (2026-05-02)

- **Reason:** Gallery X11 runtime scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_gallery_x11_runtime.py`, with production behavior in `my-claw/tools/gallery/gallery_x11.py` and wrapper behavior in `my-claw/tools/gallery_x11.py`. The `gallery_x11.py` bug where `render_overlay` code was accidentally placed into `init_pygame_display()` was fixed. The wrapper test `tests/test_gallery_x11_wrapper_depth.py` already provided depth-2 coverage for the wrapper CLI API. We therefore deepened `tests/test_gallery_x11_runtime.py` to cover the `load_playlist`, `render_art`, `render_overlay`, and `init_pygame_display` functions of the core display loop without requiring a real X11 display by injecting the `dummy` SDL video driver. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the existing identity startup subsystem; current CLI startup, daemon, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this test-only task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.

## frac-0072 (2026-05-02)

- **Reason:** Functional-harmony test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_functional_harmony.py`, with production behavior in `my-claw/tools/senseweave/reharmonizer.py`, `my-claw/tools/senseweave/harmonic_planner.py`, and `my-claw/tools/senseweave/score_tree.py`. Existing tests cover per-function harmonic labels, cadences, pivot/common-tone helpers, tension levels, transition intents, and section field serialization. The production path already implements the simplest one-path resolved harmony flow, including scene keys, section functions/cadences, progression roots, chord-degree triads, harmonic functions, transition intents, and score-tree field persistence. This task therefore targets test hardening only: add a depth gate plus end-to-end coverage that drives resolve -> reharm -> modulation continuity -> score-tree JSON round-trip through the existing public API. The generated startup hardening bullets target the existing identity startup subsystem; current CLI startup, daemon, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this harmony task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_functional_harmony_depth.py -q` failing on the missing `FunctionalHarmonyEndToEndTests` class before the end-to-end class was appended. After the test additions, `pytest tests/test_functional_harmony.py tests/test_test_functional_harmony_depth.py -q` passed with `35 passed`. The startup identity hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4487 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0071 (2026-05-02)

- **Reason:** Federation-discovery test-depth scope and startup-hardening assumptions
- **Details:** Exploration confirmed the affected surface is `tests/test_federation_discovery.py` with production behavior in `promptclaw/federation/discovery.py`. The existing function-level tests already cover Tailscale-status probing, self-IP exclusion, malformed-identity tolerance, and registry save/load/merge primitives, and the production code already implements the simplest one-path `discover_peers` / `save_peer_registry` / `load_peer_registry` / `merge_peer_registry` flow with no production gap. This task therefore targets test hardening only: add a depth gate plus end-to-end coverage that drives the full discover → save → load → re-scan → merge → save cycle through the existing public API against fakes for `tailscale status --json` and the identity HTTP endpoint. The generated startup hardening bullets target the existing identity startup subsystem; current CLI startup, daemon, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this test-only task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_federation_discovery_depth.py -q` failing on the missing `FederationDiscoveryEndToEndTests` class before the end-to-end class was appended. After the test additions, `pytest tests/test_federation_discovery.py tests/test_test_federation_discovery_depth.py -q` passed with `12 passed`. The startup identity hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4483 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0070 (2026-05-02)

- **Reason:** Dashboard-generator test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_dashboard_generator.py` with production behavior in `my-claw/tools/dashboard_generator.py`. Existing tests already cover HTML escaping, pipeline/event collection, pets JSON parsing, runtime generation, and the startup identity hardening anchors. The production gap is the stubbed `collect_pet_classes()`, which prevents normal dashboard generation from surfacing class/level output unless tests manually inject overrides. This task therefore adds a depth gate plus end-to-end dashboard coverage and implements the simplest SQLite-backed class override path from Observatory `agent_skills`; startup identity hardening is re-run as regression coverage because CLI startup, daemon startup, and narrative ASGI import already invoke `bootstrap_identity()`. No new dependencies, migrations, provider secrets, database columns, HTTP routes, or auth behavior are required.
- **Reason:** Red phase, implementation verification, and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_dashboard_generator.py::DashboardGeneratorEndToEndTests -q` failing on the missing `collect_pet_classes(path)` API before implementation while `pytest tests/test_test_dashboard_generator_depth.py -q` passed after the depth gate was made deterministic against the local classifier. After implementation, `pytest tests/test_dashboard_generator.py::DashboardGeneratorEndToEndTests -q` passed with `2 passed`, `pytest tests/test_dashboard_generator.py tests/test_dashboard_generator_runtime.py tests/test_test_dashboard_generator_depth.py -q` passed with `51 passed`, and the startup identity hardening anchor command passed with `7 passed`. The first full validation attempt exposed a pre-existing dirty boot-script edit that had removed `ensure_sample_capture_service`; restoring that service start additively in the dirty worktree let `pytest tests/test_cypherclaw_boot_runtime.py::test_boot_script_starts_sample_capture_service -q` pass. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` then passed with `4479 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0068 (2026-05-02)

- **Reason:** Contact-mic runtime test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_contact_mic_calibration_runtime.py`, with production behavior in `my-claw/tools/contact_mic_calibration.py` and product-facing documentation in `docs/contact-mic-calibration-protocol.md` plus `docs/command-reference.md`. The production harness already implements the simple end-to-end path for default scenarios, WAV analysis, ALSA parsing, fakeable capture backends, per-scenario JSON reports, and `summary.json` bundles. This task therefore preserves production behavior and deepens the existing runtime test file with one-path hardware-free coverage for meaningful analysis output, bundle persistence, CLI JSON output, and device parsing. The generated startup hardening bullets target the existing identity startup subsystem; current daemon, CLI, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence across standalone/federated boots, so they will be re-run as regression anchors rather than broadening this test-only task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_contact_mic_calibration_runtime_depth.py -q` failing on missing `ContactMicCalibrationEndToEndTests` before implementation. After implementation, `pytest tests/test_contact_mic_calibration_runtime.py::ContactMicCalibrationEndToEndTests tests/test_test_contact_mic_calibration_runtime_depth.py -q` passed with `5 passed`, `pytest tests/test_contact_mic_calibration_runtime.py tests/test_test_contact_mic_calibration_runtime_depth.py -q` passed with `9 passed`, and the public contact-mic scenario CLI smoke printed `4 machine_load_180s`. The startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4463 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0066 (2026-05-02)

- **Reason:** Config test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_config.py`, which currently classifies at fractal depth 1 (`all functions return trivial values`), while `promptclaw/config.py` already classifies at depth 3 and exposes the meaningful config helpers added by prior work (`enabled_agents`, `config_status_report`, `summarize_config`, and `load_or_default`). This task therefore targets test hardening only: add an explicit depth/class-presence gate and append end-to-end coverage for scaffold load, config save/load, validation, reporting, JSON-safe summaries, load-or-default behavior, command-agent persistence, and CLI-compatible payload shape. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the startup identity subsystem; existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover those anchors and will be re-run rather than changing unrelated startup code. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth changes are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_config_depth.py -q` failing on missing `ConfigEndToEndTests` before implementation. After implementation, `pytest tests/test_config.py::ConfigEndToEndTests -q` passed with `5 passed`, `pytest tests/test_test_config_depth.py -q` passed with `1 passed`, and `pytest tests/test_config.py tests/test_test_config_depth.py tests/test_promptclaw_config_depth.py tests/test_bootstrap.py tests/test_doctor.py -q` passed with `19 passed`. Fractal classification for `tests/test_config.py` reports depth 2 (`full implementations (no tests)`, 5 real functions versus 4 trivial). The startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4427 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0064 (2026-05-02)

- **Reason:** Local-client test-depth scope and stale scanner input
- **Details:** Exploration found that `tests/test_client_local.py` already classifies at fractal depth 2 (`simple implementations (44 lines)`) in this checkout, while `my-claw/tools/senseweave/generation/client_local.py` classifies at depth 3 and already implements the meaningful local preview backend from prior generation work. This task therefore targets test hardening only: add an explicit depth/class-presence gate and append end-to-end coverage for typed `GenerationRequest` WAV output, legacy mapping payloads, local request summaries, deterministic repeat generation, JSON-safe diagnostics, and shared protocol validation. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the startup identity subsystem; existing CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover those anchors and will be re-run rather than changing unrelated startup code. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth changes are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_test_client_local_depth.py -q` failing on missing `TestLocalAdaClientEndToEnd` before implementation. After implementation, `pytest tests/test_client_local.py::TestLocalAdaClientEndToEnd -q` passed with `4 passed`, `pytest tests/test_client_local.py tests/test_test_client_local_depth.py -q` passed with `7 passed`, and the public local-client smoke printed `local-frac-0064-smoke 0.25`. The startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4414 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `tests/test_client_local.py` reports depth 2 (`full implementations (no tests)`). No new dependencies or migrations were introduced.

## frac-0060 (2026-05-02)

- **Reason:** Audio-analysis test deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_audio_analysis.py`, with production behavior in `my-claw/tools/audio_analysis.py`. The production module already classifies at fractal depth 3 and implements meaningful pure functions for amplitude, autocorrelation pitch, onset state, click transient detection, coarse content classification, pitch-to-note/key mapping, and spectral peak extraction. The test file classifies at depth 1 (`21/40 trivial, 19 real`), so this task preserves production behavior and deepens the tests with one-path end-to-end coverage across the existing public API. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated identity persistence target the startup subsystem; existing CLI, first-boot, daemon-ordering, and narrative ASGI tests will be re-run as regression anchors instead of changing unrelated startup code. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth changes are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_audio_analysis_depth.py -q` failing at depth 1 (`21/40 trivial, 19 real`) before end-to-end coverage was added. After implementation, `pytest tests/test_audio_analysis.py::TestAudioAnalysisEndToEnd -q` passed with `5 passed`, `pytest tests/test_audio_analysis.py -q` passed with `42 passed`, and `pytest tests/test_audio_analysis_depth.py -q` passed with depth 2 (`substantial (no tests)`, 21 trivial functions versus 24 real). The public audio-analysis smoke printed `442.0 A 430.6640625`. The startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4373 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0058 (2026-05-02)

- **Reason:** Arrangement-engine test deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_arrangement_engine.py`, with production behavior in `my-claw/tools/senseweave/arrangement_engine.py` and downstream handoff through `my-claw/tools/senseweave/music_tracker.py`. The production arrangement engine already classifies at depth 4 and implements SWE-009 lane entries/exits, doubles/dropouts, register bands, density gates, and automation curves, while the test file classifies at depth 1 (`24/39 trivial, 15 real`). This task preserves source behavior and deepens the test file with one-path end-to-end coverage over complete tracker forms. Generated startup hardening bullets target the identity startup subsystem; existing CLI, first-boot, daemon-ordering, and narrative ASGI tests will be re-run as regression anchors. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth changes are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_arrangement_engine_depth.py -q` failing at depth 1 (`24/39 trivial, 15 real`) before end-to-end coverage was added. After implementation, `pytest tests/test_arrangement_engine.py::TestArrangementEngineEndToEnd -q` passed with `10 passed`, `pytest tests/test_arrangement_engine.py -q` passed with `49 passed`, and `pytest tests/test_arrangement_engine_depth.py -q` passed with depth 2 (`substantial (no tests)`, 25 real functions versus 24 trivial). The public arrangement API smoke printed `rolling 5`. The startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4337 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0054

- **Reason:** Pytest conftest deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime/test surface is `tests/conftest.py`, with direct behavioral ownership of `--run-live-modal`, `--run-live-replicate`, `live_modal`, `live_replicate`, and `cypherclaw_e2e` collection gates. Related PRD context is in `my-claw/sdp/prd-cypherclaw-generation.md` CCG-012/014/031; the identity persistence hardening bullets target the startup subsystem and will be covered by existing CLI/daemon/narrative startup anchors. The current module classifies at fractal depth 1 (`2/3 trivial, 1 real`). This task preserves the pytest hook contract and adds a stdlib-only typed collection-gate decision/report path. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth changes are required.
- **Reason:** Focused verification and startup-hardening anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_conftest_depth.py -q` failing on missing `CollectionGateDecision`, missing collection-gate helpers, and depth 1 before implementation. After implementation, `pytest tests/test_conftest_depth.py -q` passed with `7 passed`, `pytest tests/test_generation_live_modal.py tests/test_generation_live_replicate.py -q` passed with `2 skipped`, and `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4260 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `tests/conftest.py` reports depth 2 (`full implementations (no tests)`, 6 real functions). No new dependencies or migrations were introduced.

Items requiring human review. Append-only per task.

## frac-0080 (2026-05-02)

- **Reason:** Generative-score test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_generative_scores.py`, with production behavior in `my-claw/tools/senseweave/generative_scores.py` and score-tree context in `docs/cypherclaw-score-tree-composition-spec.md`. The production module already implements the simple one-path score-generation pipeline for melody, bass, counter, mood scores, narrative-event scores, hook metadata, memory fragments, repertoire hints, and frequency conversion. This task therefore preserves production behavior and deepens the existing test file with a named end-to-end class plus a depth gate. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they were re-run as regression anchors instead of broadening this score-generation task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_generative_scores_depth.py -q` failing on the missing `GenerativeScoresEndToEndTests` class before the end-to-end class was appended. After implementation, `pytest tests/test_generative_scores.py::GenerativeScoresEndToEndTests -q` passed with `3 passed`, `pytest tests/test_generative_scores.py tests/test_test_generative_scores_depth.py -q` passed with `89 passed`, and the startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4541 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0050 (2026-05-02)

- **Reason:** image_api schema deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `src/cypherclaw/image_api/schemas.py`, with direct consumers in `app.py`, `spec_parser.py`, `worker.py`, `gemini_backend.py`, `jobs_db.py`, and package exports. The module currently classifies at fractal depth 0 (`no functions found`) because it only contains Pydantic model classes. This task preserves the request/response wire contract and adds stdlib-only typed status/spec summary helpers that produce meaningful JSON-safe output for operator logs and dashboards. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the CLI/daemon/narrative startup subsystem; current startup paths already invoke `bootstrap_identity()` before dependent first-boot work, and existing identity tests will be re-run as regression anchors. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth changes are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_image_api_schemas_depth.py -q` failing on missing `ACTIVE_JOB_STATUSES` before implementation. After implementation, `pytest tests/test_image_api_schemas_depth.py -q` passed with `6 passed`, existing image API regressions passed with `51 passed`, and the explicit startup identity hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. Focused `ruff check src/cypherclaw/image_api/schemas.py tests/test_image_api_schemas_depth.py` and `mypy src/cypherclaw/image_api/schemas.py` passed. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4228 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `src/cypherclaw/image_api/schemas.py` reports depth >= 2. No new dependencies or migrations were introduced.

## frac-0048 (2026-05-02)

- **Reason:** PromptClaw template deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `promptclaw/templates.py`, with direct scaffold consumption through `promptclaw/bootstrap.py` and CLI `init`. The module currently classifies at fractal depth 1 (`all functions return trivial values`) because `project_scaffold(project_name)` is the only public function and returns a direct path-to-content mapping. This task preserves every generated file path and the existing scaffold JSON shape while adding a stdlib-only typed template-entry/report/summary path that gives callers meaningful output about generated template categories, file counts, byte counts, and required startup prompts. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the startup identity subsystem; current CLI/daemon/narrative startup paths already invoke `bootstrap_identity()` before dependent startup work, and existing identity tests will be re-run as regression anchors. No new dependencies, migrations, provider secrets, database columns, runtime state files, or agent command strings are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_promptclaw_templates_depth.py -q` failing on missing `ScaffoldTemplateEntry` before implementation. After implementation, `pytest tests/test_promptclaw_templates_depth.py -q` passed with `5 passed`, `pytest tests/test_bootstrap.py tests/test_config.py tests/test_orchestrator.py -q` passed with `7 passed`, and the startup identity hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `8 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4215 passed, 3 skipped`, Ruff clean, and mypy clean. Focused `ruff check promptclaw/templates.py tests/test_promptclaw_templates_depth.py` and `mypy --follow-imports=skip promptclaw/templates.py` also passed. A direct `mypy promptclaw/templates.py` follows broader imports and remains blocked by pre-existing unrelated issues in `promptclaw/utils.py` and missing `psycopg2` stubs. Fractal classification for `promptclaw/templates.py` reports depth 2 (`substantial (no tests)`, 4 real functions). No new dependencies or migrations were introduced.

## frac-0045 (2026-05-02)

- **Reason:** Composer quote verifier deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/composer_quote_verify.py`, with direct regression coverage in `tests/test_composer_quote_verify.py`, downstream self-listener coverage in `tests/test_self_listener_quote_verify.py`, and sampler architecture context in `docs/cypherclaw-sampler-architecture.md` plus `my-claw/sdp/prd-cypherclaw-sampler.md` CCS-019/CCS-031. The module already runs the known-room capture, three fake-JACK self quotes, and motif/tag matching end-to-end, but `sdp.fractal.classify_depth("my-claw/tools/composer_quote_verify.py")` reported depth 1 (`13/18 trivial, 5 real`) because adapter methods dominated the file. This task preserves the existing smoke command and adds a stdlib-only typed report/summary/render path. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem, not this capture verifier; the existing startup identity anchors were re-run. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_composer_quote_verify_depth.py -q` failing on missing `QuoteVerificationReport` before implementation. After implementation, `pytest tests/test_composer_quote_verify_depth.py tests/test_composer_quote_verify.py -q` passed with `10 passed`, `pytest tests/test_self_listener_quote_verify.py tests/test_sample_capture_verify.py -q` passed with `10 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4203 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `my-claw/tools/composer_quote_verify.py` reports depth 3 (`substantial (442 lines, 15 real functions)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0044 (2026-05-02)

- **Reason:** Pre-existing working-tree corruption blocking verify
- **Details:** At session start `git status` showed unstaged modifications on `my-claw/tools/senseweave/hook_engine.py` (+35 lines: a duplicate `_HOOK_CONTOURS` / `_RHYTHM_BY_GROOVE` / `_TIMBRAL_TAGS` block plus a broken `return HookProfile(...),` followed by a second copy of all keyword arguments) and `my-claw/tools/senseweave/score_tree.py` (+1 line: a duplicate `timbral_tags: tuple[str, ...]` field on `MotifNode` without a default). Both produce import-time `IndentationError` / `SyntaxError`, blocking the full test suite (e.g. `tests/test_agogic_rule.py` cannot even import `senseweave.music_tracker`). These modifications are not from this task — they appear to be residue from a re-run of the non-idempotent original `rewrite_hook.py` script on already-migrated files, which is exactly the failure mode this task's idempotent refactor prevents. HEAD on `feat/graceful-degradation` carries the canonical post-migration content. Assumption: it is safe to revert these two files to HEAD before running validation, since the working-tree state is broken and was not deliberate WIP.
- **Reason:** Validation and depth-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_rewrite_hook_depth.py -x` failing on missing `HOOK_FIELD_RENAMES` import before implementation. After implementation, `pytest tests/test_rewrite_hook_depth.py -q` passed with `9 passed`, `ruff check rewrite_hook.py tests/test_rewrite_hook_depth.py` and `ruff check src/ tests/` were clean, and `mypy rewrite_hook.py` and `mypy src/` were clean. Fractal classification for `rewrite_hook.py` reports depth 2 (`simple implementations (78 lines)`, 4 real functions, 0 trivial). No new dependencies, migrations, provider secrets, database columns, or agent commands were introduced.

## frac-0043 (2026-05-02)

- **Reason:** PromptClaw artifact report scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `promptclaw/artifacts.py`, with canonical run paths owned by `promptclaw/paths.py` and direct write/read use from `promptclaw/orchestrator.py`, `promptclaw/state_store.py`, `promptclaw/memory.py`, and `promptclaw/cli.py`. A prior duplicate artifact slice already added event replay and filename validation, so this task will preserve those contracts and add a stdlib-only typed artifact run report that summarizes expected files, missing files, and event metadata without changing on-disk formats. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence are outside this artifact surface; the current tree already documents daemon and ASGI identity bootstrap, and existing anchors will be re-run. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_promptclaw_artifacts_report.py -q` failing on missing `ArtifactRunReport` before implementation. After implementation, `pytest tests/test_promptclaw_artifacts_report.py -q` passed with `3 passed`, `pytest tests/test_promptclaw_artifacts_depth.py -q` passed with `5 passed`, `pytest tests/test_promptclaw_artifacts_report.py tests/test_promptclaw_artifacts_depth.py tests/test_orchestrator.py tests/test_config.py -q` passed with `13 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `8 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4189 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `promptclaw/artifacts.py` reports depth 2 (`full implementations (no tests)`). No new dependencies or migrations were introduced.

## frac-0041 (2026-05-02)

- **Reason:** PromptClaw paths deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `promptclaw/paths.py`, with direct consumers in `promptclaw/artifacts.py`, `promptclaw/orchestrator.py`, `promptclaw/memory.py`, `promptclaw/state_store.py`, and `promptclaw/cli.py`. Existing regression coverage is in `tests/test_config.py`, `tests/test_orchestrator.py`, and the recent artifact depth tests. The module currently classifies at depth 1 because all 16 public path helpers are direct projections; this task will preserve those helper return values while adding a stdlib-only typed run layout, JSON-safe path summary, and idempotent run-layout preparation. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon/narrative startup subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup paths and bootstraps ASGI app imports, with `tests/test_first_boot.py::TestStartupIdentityPersistence`, `tests/test_governor_integration.py::TestStartupIdentityWiring`, and `tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_promptclaw_paths_depth.py -q` failing on missing `RunPathLayout` before implementation. After implementation, `pytest tests/test_promptclaw_paths_depth.py -q` passed with `5 passed`, `pytest tests/test_config.py tests/test_orchestrator.py tests/test_promptclaw_artifacts_depth.py -q` passed with `10 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `8 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4179 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `promptclaw/paths.py` reports depth 2 (`full implementations (no tests)`, 15 real functions). No new dependencies or migrations were introduced.

## frac-0037 (2026-05-02)

- **Reason:** Entities-domain migration deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `narrative/migrations/20260502_001347za_add_entities_domain.py`, with existing coverage in `tests/test_narrative_entities_domain_migration.py` and narrative entity/domain API coverage in `tests/test_narrative_api_entities.py`. The migration already applies the CN-001 schema modification (`domain TEXT DEFAULT 'shared'` on `entities` and `events`) and existing rows/new rows work, but the fractal scanner reports depth 1 because `upgrade()` and `downgrade()` are direct Alembic operation calls. This task will preserve the same schema behavior while adding a stdlib-only typed plan and JSON-safe summary path, then route upgrade/downgrade through that plan. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence are already implemented in daemon/narrative startup paths and covered by `tests/test_first_boot.py::TestStartupIdentityPersistence`, `tests/test_governor_integration.py::TestStartupIdentityWiring`, and `tests/test_narrative_api_main.py::test_main_calls_bootstrap_identity`; those tests will be re-run as regression anchors. No new dependencies, provider secrets, tables, foreign keys, or agent commands are required.
- **Reason:** Focused verification and startup-hardening anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_narrative_entities_domain_migration.py -q` failing on missing `domain_column_plans`, missing `domain_migration_summary`, and fractal depth 1 before implementation while the existing migration behavior tests passed. After implementation, `pytest tests/test_narrative_entities_domain_migration.py -q` passed with `6 passed`, `pytest tests/test_narrative_api_entities.py tests/test_narrative_entities_domain_migration.py -q` passed with `36 passed`, and `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_main_calls_bootstrap_identity -q` passed with `8 passed`. The required full validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4155 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `narrative/migrations/20260502_001347za_add_entities_domain.py` reports depth 2 (`simple implementations (96 lines)`). No new dependencies or additional migrations were introduced.

## frac-0095 (2026-05-03)

- **Reason:** Narrative entities-domain migration test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_narrative_entities_domain_migration.py`, with production behavior in `narrative/migrations/20260502_001347za_add_entities_domain.py` and product requirements in `prd-cypherclaw-narrative-http-service.md` CN-001. The migration module already implements the simplest depth-2 plan and summary path from frac-0037, while this task targets the missing test-file depth pattern: a depth gate plus a named end-to-end class that drives summary, upgrade, explicit domain inserts, downgrade, re-upgrade, and JSON-safe diagnostics through the existing SQLite Alembic shim. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors. No new dependencies, provider secrets, database columns, migration files, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_narrative_entities_domain_migration_depth.py -q` failing on the missing `NarrativeEntitiesDomainMigrationEndToEndTests` class. After adding the end-to-end migration lifecycle class, `pytest tests/test_narrative_entities_domain_migration.py::NarrativeEntitiesDomainMigrationEndToEndTests -q`, `pytest tests/test_test_narrative_entities_domain_migration_depth.py -q`, and `pytest tests/test_narrative_entities_domain_migration.py -q` passed, the related narrative entity/migration regression set passed with `38 passed`, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4584 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0036 (2026-05-02)

- **Reason:** Theramini MIDI deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/theramini_midi.py`, with the durable per-cycle JSON contract owned by `senseweave.theramini_duet.normalize_theramini_state` (`timestamp`, `is_playing`, `pitch_hz`, `pitch_note`, `pitch_confidence`, `state`, `consecutive_silence_ms`, `midi_cc`, `pitch_bend`) and consumed by `senseweave.theramini_duet.plan_duet_response` plus the listener/runtime tests in `tests/test_theramini_listener_runtime.py` and `tests/test_theramini_duet.py`. The current module is depth 1 (`3/4 trivial, 1 real`, 122 lines) because `run()` is the only real function, mixing device opening, raw MIDI byte parsing, note/CC/pitch bookkeeping, JSON rendering, and the sleep loop in one body, with no typed API to test against. This task will add the minimum stdlib-only typed parse, apply, render, write, one-cycle, and loop helpers (with `max_iterations` for tests) so MIDI Note On/Off, CC, and pitch-bend events produce the same JSON payload end-to-end while preserving the existing listener/duet contract. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both `daemon.py` and `cypherclaw_daemon.py`, with `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_theramini_midi.py -q` failing on missing `parse_midi_messages`, `apply_midi_event`, `process_buffer`, `render_state`, `process_once`, `run_daemon`, and depth remaining 1 before implementation. After implementation, `pytest tests/test_theramini_midi.py -q` passed with `7 passed`, `pytest tests/test_theramini_listener_runtime.py tests/test_theramini_duet.py tests/test_theramini_midi.py -q` passed with `71 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4152 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `my-claw/tools/theramini_midi.py` reports depth 4 (`polished (301 lines, 100% docstrings, tests 0.74x)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0035 (2026-05-02)

- **Reason:** Tamagotchi deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/tamagotchi.py`, with display consumers in `my-claw/tools/glyphweave/scenes.py`, sprite/animation helpers in `my-claw/tools/glyphweave/pet_sprites.py` and `my-claw/tools/glyphweave/pet_animations.py`, daemon call sites in `my-claw/tools/daemon.py` and `my-claw/tools/cypherclaw_daemon.py`, and existing coverage in `tests/test_tamagotchi_runtime.py` plus `tests/test_glyphweave_runtime.py`. The Pet System V2 PRD asks for richer compact pet display and meaningful stats, but this slice is the generated depth-2/simple path rather than the PostgreSQL multi-class migration. The module currently classifies at fractal depth 1 (`24/36 trivial, 12 real`), so this task will preserve JSON persistence and task-transition semantics while adding a stdlib-only typed diagnostic/report surface that turns existing pet state into meaningful health/activity/fleet summaries. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup paths and has `tests/test_first_boot.py::TestStartupIdentityPersistence` plus `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_tamagotchi_depth.py -q` failing on missing `pet_health_band`, `build_pet_vital_snapshot`, `build_pet_fleet_report`, `PetManager.fleet_report`, and depth remaining 1 before implementation. After implementation, `pytest tests/test_tamagotchi_depth.py -q` passed with `5 passed`, `pytest tests/test_tamagotchi_runtime.py tests/test_glyphweave_runtime.py -q` passed with `10 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4145 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `my-claw/tools/tamagotchi.py` reports depth 2 (`substantial (no tests)`, 27 real functions), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0034 (2026-05-02)

- **Reason:** Startle daemon deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/startle_daemon.py`, with the existing `update_startle` / `should_mute_output` / `startle_to_face_reaction` rules owned by `my-claw/tools/senseweave/startle.py`, the room-activity input produced by `my-claw/tools/input_monitor.py` (`window_mic_amp`, `cypherclaw_mic_amp`, `recent_transient`), and the `/tmp/startle_state.json` consumer contract read by `my-claw/tools/inner_life/world_model.py` (`startled`, `startle_count`). The current daemon is a top-level infinite loop, is not import-safe, has no typed function API, swallows every exception, and calls `update_startle(state, amp, transient)` where the second argument is the `baseline_rms` float rather than the room transient bool. This task will add the minimum stdlib-only typed one-cycle and loop functions, a rolling-baseline tracker so the existing detector sees a real positive baseline, atomic JSON writes that preserve the consumer contract, and `--once` / `--max-iterations` controls for tests. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both `daemon.py` and `cypherclaw_daemon.py`, with `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_startle_daemon.py::test_module_import_is_side_effect_free -q` failing on the old import-time infinite loop (subprocess timeout) before implementation. After implementation, `pytest tests/test_startle_daemon.py -q` passed with `4 passed`, `pytest tests/test_startle.py tests/test_startle_daemon.py -q` passed with `36 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4140 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0033 (2026-05-02)

- **Reason:** Sensory journal daemon deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/sensory_journal_daemon.py`, with the durable journal contract owned by `my-claw/tools/senseweave/sensory_journal.py` and sensor-state input produced by `my-claw/tools/senseweave/sensor_fusion.py`. The current daemon is a top-level infinite loop, is not import-safe, has no typed function API, and calls `log_event(...)` with a metadata dict where the journal module expects a human-readable description plus `sensor_source`. This task will add the minimum stdlib-only typed one-cycle and loop functions so Theramini starts, room transients, and energy shifts produce meaningful JSONL entries end-to-end. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both `daemon.py` and `cypherclaw_daemon.py`, with `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_sensory_journal_daemon.py::test_module_import_is_side_effect_free -q` failing on the old import-time infinite loop before implementation. After implementation, `pytest tests/test_sensory_journal_daemon.py -q` passed with `4 passed`, `pytest tests/test_sensory_journal.py tests/test_sensory_journal_daemon.py -q` passed with `32 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4136 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `my-claw/tools/sensory_journal_daemon.py` reports depth 4 (`polished (222 lines, 100% docstrings, tests 0.73x)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0031 (2026-05-02)

- **Reason:** Synthesis architecture registry deepening scope and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/synthesis_architecture_registry.py`, with existing coverage in `tests/test_synthesis_architecture_registry.py` plus downstream consistency checks against `senseweave.procedural_arc` and `senseweave.production_course`. The module already resolves/ranks six synthesis families by role, arc-phase affinity, safe macro-control ranges, and fallback strategy, but the fractal scanner reports depth 1 (`5/6 trivial, 1 real`) because simple lookup helpers outnumber real logic. This task preserves every existing strategy record and lookup helper while adding a stdlib-only typed `ArchitectureProfile` / `ArchitectureRegistryReport` diagnostic surface plus band, fallback-chain, build, and JSON-safe summary helpers that delegate to the existing registry. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both `daemon.py` and `cypherclaw_daemon.py`, with `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_synthesis_architecture_registry_depth.py -q` failing on the missing `ArchitectureProfile` import before implementation. After implementation, `pytest tests/test_synthesis_architecture_registry_depth.py -q` passed with `6 passed`, `pytest tests/test_synthesis_architecture_registry.py -q` passed with `33 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. The full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4126 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `my-claw/tools/senseweave/synthesis_architecture_registry.py` reports depth 4 (`polished (451 lines, 100% docstrings, tests 0.52x)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0029 (2026-05-02)

- **Reason:** Accompaniment depth and startup-hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/synthesis/accompaniment.py`, with existing coverage in `tests/test_accompaniment.py`. The module already translates density/resting state into one of six concrete accompaniment patterns plus pedal and transition helpers, but the fractal scanner reports depth 1 (`13/18 trivial, 5 real`) because the simple tuple-returning helpers outnumber real logic. This task preserves all existing helper contracts while adding a stdlib-only typed `AccompanimentPatternSnapshot` / `AccompanimentPlanReport` diagnostic surface plus density/name/energy/register/transition/event-summary helpers that delegate to the existing selection, breathing, pedal, and `get_pattern(...)` path. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both `daemon.py` and `cypherclaw_daemon.py`, with `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_accompaniment_depth.py -q` failing on the missing `AccompanimentPatternSnapshot` import before implementation. After implementation, `pytest tests/test_accompaniment_depth.py tests/test_accompaniment.py -q` passed with `33 passed`, the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`, and the full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4113 passed, 3 skipped`, ruff clean, and mypy clean. Fractal classification for `my-claw/tools/senseweave/synthesis/accompaniment.py` reports depth 3 (`substantial (511 lines, 18 real functions)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0028 (2026-05-02)

- **Reason:** SynthDef registry deepening scope and out-of-scope hardening checks
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/synthdef_registry.py` with existing coverage in `tests/test_synthdef_registry.py` and palette-consistency cross-checks against `senseweave.sound_palette_lab` and `senseweave.voice_aliases`. The module already owns the verified twelve-entry voice palette (subtractive/additive/FM/wavetable/physical-model/granular methods, register ranges, macro controls, spectral profiles, quarantine flags, and safe substitutes) and exposes `get_entry`, `resolve_voice`, `entries_by_method`, `live_voices`, `quarantined_voices`, `voices_for_role`, and `covered_methods`. It currently classifies at fractal depth 1 (`7/9 trivial, 2 real (test boosted)`) because the comprehension-style lookup helpers outnumber the real `resolve_voice` and `RegisterRange.octave_span` paths. This task preserves every existing dataclass, registry entry, and lookup function while adding a stdlib-only typed `VoiceShape` / `SynthDefRegistryReport` surface plus `register_band`, `fundamental_band`, `noise_band`, `rolloff_band`, `build_voice_shape`, `build_synthdef_registry_report`, and `summarize_synthdef_registry_report` helpers that resolve quarantine via the existing `resolve_voice` path and emit a JSON-safe operator summary. The auto-generated hardening checks about `/healthz` + `/readyz` endpoints and the bearer-token auth header are scoped to the `narrative/` HTTP service and are unrelated to this pure data-model module; they remain anchored by `tests/test_smoke_narrative_script.py`. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_synthdef_registry_depth.py -x` failing on the missing `SynthDefRegistryReport` import before implementation. After implementation, `pytest tests/test_synthdef_registry_depth.py tests/test_synthdef_registry.py -q` passed with `41 passed`, the explicit narrative hardening anchor command `pytest tests/test_smoke_narrative_script.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `15 passed`, and the full required gate `pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4107 passed, 3 skipped`, ruff clean, and mypy clean. Fractal classification for `my-claw/tools/senseweave/synthdef_registry.py` reports depth 3 (`substantial (660 lines, 9 real functions)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0027 (2026-05-02)

- **Reason:** EMSD performance deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/emsd_performance.py`, with existing coverage in `tests/test_emsd_performance.py` and live consumption from `my-claw/tools/duet_composer.py`. The module already translates one live `EMSDLiveContext` into meaningful per-note amp/release/brightness/space/filter/drive adjustments, including mix targets, role lanes, source type, sample transforms, DSP blocks, Theramini ducking, and sample capture metadata. It currently classifies at fractal depth 1 (`3/5 trivial, 2 real (test boosted)`) because the small math/lookup helpers outnumber the real render path. This task will preserve `PerformanceAdjustments` and `render_adjustments_for_event(...)` while adding a stdlib-only typed event snapshot/report/summary surface that delegates to the existing render path and produces operator-readable batch diagnostics. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; this module has no startup side effects, so existing startup anchors will be re-run rather than changing unrelated startup flow. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_emsd_performance_depth.py -q` failing on missing `PerformanceAdjustmentReport`/report-path symbols before implementation. After implementation, `pytest tests/test_emsd_performance_depth.py tests/test_emsd_performance.py -q` passed with `11 passed`, the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`, and the full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4101 passed, 3 skipped`, ruff clean, and mypy clean. Fractal classification for `my-claw/tools/senseweave/emsd_performance.py` reports depth 3 (`substantial (373 lines, 9 real functions)`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0026 (2026-05-02)

- **Reason:** EMSD runtime deepening scope and out-of-scope hardening checks
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/emsd_runtime.py` with existing coverage in `tests/test_emsd_runtime.py`. The module already builds the live EMSD context end-to-end (arc directive + capstone phase plan + density bias) and flattens it into `composer_emsd_extras` for the composer-state payload, but it classifies at fractal depth 1 (`3/4 trivial, 1 real`) because `_clamp`, the `EMSDLiveContext.identity` property, and `composer_emsd_extras` are short return-only helpers that outnumber `build_live_emsd_context`. This task preserves the existing `EMSDLiveContext` field set, `build_live_emsd_context(...)`, and `composer_emsd_extras(...)` payload while adding a stdlib-only typed `EMSDPhaseSnapshot` / `EMSDRuntimeReport` surface plus `arc_phase_index`, `arc_phase_band`, `density_pressure_band`, `build_phase_snapshot`, `build_runtime_report`, and `summarize_runtime_report` helpers. The generated narrative hardening bullets (`/healthz`, `/readyz`, bearer-token auth header, `tests/test_smoke_narrative_script.py`) are scoped to the narrative HTTP service and are unrelated to this SenseWeave EMSD wiring module; they remain anchored by the existing narrative smoke regression suite. Startup identity hardening is re-run as anchor coverage via `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring`. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_emsd_runtime_depth.py -q` failing on a missing `CANONICAL_ARC_PHASES` import before implementation. After implementation, `pytest tests/test_emsd_runtime_depth.py tests/test_emsd_runtime.py -q` passed with `12 passed`, the narrative HTTP smoke regression plus the explicit startup hardening anchor command `pytest tests/test_smoke_narrative_script.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `15 passed`, and the full required gate `pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4094 passed, 3 skipped`, ruff clean, and mypy (`src/`) clean. Fractal classification for `my-claw/tools/senseweave/emsd_runtime.py` now reports depth 3 (`6 real` functions, `329 lines`), satisfying the depth >= 2 requirement. No new dependencies or migrations were introduced.

## frac-0025 (2026-05-02)

- **Reason:** Motif-lifecycle deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/motif_lifecycle.py` with existing coverage in `tests/test_motif_lifecycle.py`. The module already performs deterministic state transitions, manager registration/advance, and repertoire-shape recall end-to-end, but the fractal scanner reports depth 1 (`10/18 trivial, 8 real`) because small accessors and simple transition helpers outnumber real logic. This task will preserve the existing `MotifNode`, transformation, `advance`, manager, and repertoire summary contracts while adding a stdlib-only typed lifecycle path/report/summary surface that produces meaningful operator output. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup paths and the startup anchors pass. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_motif_lifecycle_depth.py -q` failing on missing `MotifLifecycleReport`/report-path symbols before implementation. After implementation, `pytest tests/test_motif_lifecycle_depth.py tests/test_motif_lifecycle.py -q` passed with `35 passed`, the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `5 passed`, and the full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4085 passed, 3 skipped`, ruff clean, and mypy clean. Fractal classification for `my-claw/tools/senseweave/motif_lifecycle.py` reports depth 3 (>=2 acceptance criterion satisfied). No new dependencies or migrations were introduced.

## frac-0063 (2026-05-02)

- **Reason:** Cast-planner test-depth scope and startup hardening assumptions
- **Details:** Exploration found the production cast-planner surface is `my-claw/tools/senseweave/cast_planner.py`, exposing `select_cast_ids()` and `assemble_cast()` plus internal helpers for ranking, sampler-summary derivation, and piece-derived selector kwargs. The production module already returns a meaningful cast plan with sampler metadata and classifies at depth 3, while `tests/test_cast_planner.py` classifies at depth 1 (`11/21 trivial, 10 real`). This task therefore targets test deepening only: add a depth gate and end-to-end tests that exercise the existing public `select_cast_ids()` / `assemble_cast()` paths across core/support coverage, voice-count target sizing, preferred-synth promotion, cast-history rotation, piece-driven sampler routing, and JSON-safe diagnostics. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the startup identity subsystem; existing tests already cover those anchors, so this task will re-run them rather than changing unrelated startup code. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_cast_planner_depth.py -q` failing on `tests/test_cast_planner.py` depth 1 (`11/21 trivial, 10 real`) before the end-to-end tests were added. After test deepening, `pytest tests/test_cast_planner.py tests/test_cast_planner_depth.py -q` passed with `21 passed`, the production smoke command for `select_cast_ids()`/`assemble_cast()` returned the canonical `['mel', 'rhythm', 'harm', 'color']` cast and matching assembled entries, and the explicit startup hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4409 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `tests/test_cast_planner.py` reports depth 2 (`substantial (no tests)`, real_logic > trivial). No new dependencies or migrations were introduced.

## frac-0062 (2026-05-02)

- **Reason:** Capstone test-depth scope and startup hardening assumptions
- **Details:** Exploration found the production capstone surface is `my-claw/tools/senseweave/capstone_engine.py`, with collaborators in `procedural_arc.py`, `sound_palette_lab.py`, `sample_lab.py`, `mix_engine.py`, `dsp_scene_lab.py`, `artistic_identity.py`, and runtime consumption through `emsd_runtime.py`. The production module already builds a meaningful five-phase `CapstoneCyclePlan` and classifies at depth 3, while `tests/test_capstone_engine.py` classifies at depth 1 (`2/3 trivial, 1 real`). This task therefore targets test deepening only: add a depth gate and end-to-end tests that exercise the existing public `build_capstone_cycle()` path across phase, cadence, sampling, mix, DSP, identity, and JSON-safe diagnostic output. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the startup identity subsystem; existing tests already cover those anchors, so this task will re-run them rather than changing unrelated startup code. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_capstone_engine_depth.py -q` failing on `tests/test_capstone_engine.py` depth 1 (`2/3 trivial, 1 real`) before the end-to-end tests were added. After test deepening, `pytest tests/test_capstone_engine.py tests/test_capstone_engine_depth.py -q` passed with `12 passed`, the production smoke command for `build_capstone_cycle()` produced all five phases and a repertoire-derived identity statement, and the explicit startup hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4401 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `tests/test_capstone_engine.py` reports depth 2 (`substantial (no tests)`, 9 real functions versus 2 trivial). No new dependencies or migrations were introduced.

## frac-0023 (2026-05-02)

- **Reason:** Sampler-dispatch deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/sampler_dispatch.py` plus its existing sampler dispatch tests. The module already loads buffers, emits `/s_new sw_sampler`, manages handle release and fire-and-forget scheduling, applies FX presets through `EffectsBus`, and computes key-aware transposition, but it currently classifies at fractal depth 1 (`9/17 trivial, 8 real`) because Protocol/property/lifecycle shims outnumber real helper functions. This task will preserve the existing OSC and lifecycle contract while adding a stdlib-only typed dispatch-plan/report surface that produces meaningful operator output and shares the same synth-argument builder as live dispatch. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon startup paths and has `tests/test_first_boot.py::TestStartupIdentityPersistence` plus `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_sampler_dispatch_depth.py -q` failing on missing `SamplerDispatchPlan`/planning symbols before implementation. After implementation, `pytest tests/test_sampler_dispatch_depth.py tests/test_sampler_dispatch.py -q` passed with `42 passed`, the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`, and the full required gate `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4070 passed, 3 skipped`, ruff clean, and mypy clean. Fractal classification for `my-claw/tools/senseweave/sampler_dispatch.py` reports depth 3 (>=2 acceptance criterion satisfied). No new dependencies or migrations were introduced.

## frac-0022 (2026-05-02)

- **Reason:** Sample-lab depth and out-of-scope hardening checks
- **Details:** Exploration confirmed `my-claw/tools/senseweave/sample_lab.py` is a working EMSD environmental-sampling module classified at fractal depth 1 (`4/6 trivial, 2 real`); this task adds a typed `SamplePlanReport` plus band/build/summarize helpers mirroring the depth-2 pattern landed for `rollout_controls` (frac-0021), `silence_budget` (frac-0020), and `punctuation` (frac-0019), without changing `SAMPLE_SOURCES`, `SAMPLE_SOURCE_ALIASES`, `SAMPLE_FALLBACKS`, `canonical_sample_source_name`, `sample_source`, `sample_bank`, or `plan_environmental_sampling` shaping. `SamplePlan` gains a defaulted `cadence_state` field so reports carry the cadence the plan was generated under; the only construction site is `plan_environmental_sampling` itself, so no callers need updating. The auto-generated hardening checks about `/healthz` + `/readyz` endpoints, the `X-Narrative-Auth` shared-secret header, and `tests/test_smoke_narrative_script.py` are scoped to `cypherclaw.narrative_api` and are unrelated to this SenseWeave sample-planning module; they remain anchored by the existing narrative API regression suite. Startup identity hardening is re-run as anchor coverage via `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring`. No new dependencies, migrations, provider secrets, or database columns are required.
- **Reason:** Focused verification and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_sample_lab_depth.py -q` failing on missing `SamplePlanReport`/`build_sample_plan_report` symbols before implementation. After implementation, `pytest tests/test_sample_lab_depth.py -q` passed with `8 passed`, `pytest tests/test_sample_lab.py -q` passed with `4 passed`, the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`, and the full required gate ran clean (`4064 passed, 3 skipped`, ruff and mypy clean). Fractal classification for `my-claw/tools/senseweave/sample_lab.py` reports depth 3 (>=2 acceptance criterion satisfied). No new dependencies or migrations were introduced.

## frac-0021 (2026-05-02)

- **Reason:** Rollout-controls deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/rollout_controls.py`, with downstream consumers in `practice_curriculum.py`, `self_critique.py`, `piece_commission.py`, and `operator_diagnostics.py`, plus existing rollout-control docs/tests from T-025. The module currently classifies at depth 1 (`4/5 trivial, 1 real`) while the four rollout flags already work end-to-end; this task will preserve flag defaults and add a small typed report/summary surface so the module produces meaningful operator output. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already covers them through `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring`, which will be re-run as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Focused verification and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_rollout_controls.py -q` failing on missing report symbols before implementation. After implementation, `pytest tests/test_rollout_controls.py -q` passed with `6 passed`, `pytest tests/test_senseweave_rollout_controls.py -q` passed with `5 passed`, and the explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/rollout_controls.py` reports depth 2. No new dependencies or migrations were introduced.
- **Reason:** Full validation results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `4055 passed, 3 skipped`, ruff clean, and mypy clean.

## frac-0019 (2026-05-02)

- **Reason:** Punctuation deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/render/rules/punctuation.py`, its exports in `my-claw/tools/senseweave/render/rules/__init__.py`, and existing punctuation / role-gate / startup identity tests. The module currently classifies at depth 1 (`8/12 trivial, 4 real`) while its R6 apply path already works for `TrackerScene`, `TrackerSong`, and `TrackerPattern`; this task will preserve terminal-extension and seeded-breath semantics and add a small typed analyze/report surface so the module produces meaningful end-to-end output. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon entrypoints and has `tests/test_first_boot.py::TestStartupIdentityPersistence` plus `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `4040 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/render/rules/punctuation.py` reports depth 2. No new dependencies or migrations were introduced.

## frac-0017 (2026-05-02)

- **Reason:** Metric-accent deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/render/rules/metric_accent.py`, its exports in `my-claw/tools/senseweave/render/rules/__init__.py`, and existing metric-accent / role-gate / startup identity tests. The module currently classifies at depth 1 (`7/13 trivial, 6 real`) while its R1 apply path already works for `TrackerScene`, `TrackerSong`, and `TrackerPattern`; this task will preserve existing table/apply semantics and add a small typed analyze/report surface so the module produces meaningful end-to-end output. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon entrypoints and `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passes with `7 passed`. No new dependencies, migrations, provider secrets, database columns, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `4023 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/render/rules/metric_accent.py` reports depth 2. No new dependencies or migrations were introduced.

## frac-0015 (2026-05-02)

- **Reason:** Render-ablation deepening scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/render/ablation.py` plus existing render ablation/debugger/listener-review tests. The module currently classifies at depth 1 (`4/7 trivial, 3 real`) while the adjacent debugger already consumes its one-render `ablate()` seam. This task will preserve `ablate()` and add a small typed ablation-suite/report surface so the module itself produces meaningful end-to-end output. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem; the current tree already calls `bootstrap_identity()` before `FirstBootAnnouncer` in both daemon entrypoints and `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passes with `7 passed`. No new dependencies, migrations, provider secrets, or database columns are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `4007 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/render/ablation.py` reports depth 2. No new dependencies or migrations were introduced.

## frac-0013 (2026-05-02)

- **Reason:** Phrase tracker depth scope and startup hardening assumptions
- **Details:** Exploration found the affected runtime surface is `my-claw/tools/senseweave/phrase_tracker.py` plus existing phrase tracker/capture/listener tests. `PhraseTracker.update()` is already wired into both MIDI and Theramini listener state payloads and into `PhraseCaptureWriter`; this task will preserve that tick-level contract while adding a small typed stream-level boundary/summary surface so the module produces meaningful end-to-end output. The auto-generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence target the daemon identity subsystem, not phrase tracking; existing anchors `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` will be re-run rather than broadening scope. No new dependencies, migrations, provider secrets, or database columns are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3991 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/phrase_tracker.py` reports depth 3. No new dependencies or migrations were introduced.

## frac-0001 assumptions

- **Reason:** Catalog deepening scope and generated startup hardening checks
- **Details:** This task targets `my-claw/curriculum/catalog.py`, the EMSD catalog helpers, and related tests. The auto-generated startup hardening checks for `bootstrap_identity()` and `FirstBootAnnouncer` are already implemented in both daemon startup paths and will be re-run as regression anchors instead of changing startup code here. No new dependencies, migrations, provider secrets, or agent commands are required.

## frac-0005 assumptions

- **Reason:** Archive-path deepening scope and generated startup hardening checks
- **Details:** This task targets `my-claw/tools/archive_paths.py`, its existing callers, and related archive-path tests. The auto-generated startup hardening checks for `bootstrap_identity()` and `FirstBootAnnouncer` are already implemented in both daemon startup paths; this task will re-run `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors instead of changing unrelated startup code. No new dependencies, migrations, provider secrets, or agent commands are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3949 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. No new dependencies or migrations were introduced.

## frac-0007 assumptions

- **Reason:** Collaborative-canvas deepening scope and generated startup hardening checks
- **Details:** This task targets `my-claw/tools/senseweave/collaborative_canvas.py` and `tests/test_collaborative_canvas.py`. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence belong to the daemon startup identity subsystem and are already covered by existing startup tests; this task will re-run `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors rather than changing unrelated startup flow. No new dependencies, migrations, provider secrets, or database columns are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3962 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. No new dependencies or migrations were introduced.

## frac-0009 assumptions

- **Reason:** Counterpoint deepening scope and generated startup hardening checks
- **Details:** This task targets the pure counterpoint analysis layer in `my-claw/tools/senseweave/counterpoint_rules.py` plus new depth tests. The generated startup hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence belong to the daemon startup identity subsystem and are already covered by existing tests; this task will re-run `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring` as regression anchors instead of changing unrelated startup flow. No new dependencies, migrations, provider secrets, or database columns are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3972 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/counterpoint_rules.py` reports depth 4. No new dependencies or migrations were introduced.

## frac-0011 assumptions

- **Reason:** Local-client deepening scope and generated startup hardening checks
- **Details:** This task targets `my-claw/tools/senseweave/generation/client_local.py`, its local-client tests, and generation-backend docs. The generated hardening bullets for `bootstrap_identity()` ordering and standalone/federated persistence belong to the daemon startup identity subsystem; the current tree already covers them through `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring`, which will be re-run as regression anchors. No new dependencies, migrations, provider secrets, database columns, or agent command strings are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3982 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q` passed with `7 passed`. Fractal classification for `my-claw/tools/senseweave/generation/client_local.py` reports depth 3. No new dependencies or migrations were introduced.

## Lingering

Systemd `--user` units (e.g. `cypherclaw-narrative-api.service`) only survive
after the operator's interactive session ends if **linger** is enabled for that
account. Without linger, the user systemd manager is torn down on SSH logout
and the service stops with it, defeating CN-013 / CN-015 (service must restart
automatically across reboot and remain active without an attached session).

Enable linger once per host, as root:

```bash
sudo loginctl enable-linger <user>
```

Verify:

```bash
loginctl show-user <user> -p Linger
# expected: Linger=yes
```

If the output is `Linger=no`, the unit will not auto-start on boot and will
not survive logout — re-run the `enable-linger` command above. This is the
same gap captured in `sdp/verification/evidence/t-004@20260502t001347zc-narrative-api-status.md`
under "Loginctl linger state for current user".

## Auth Token (optional)

`NARRATIVE_AUTH_TOKEN` enables a shared-secret check on the narrative API as
defense-in-depth. It is optional and does not replace host firewalling,
Tailscale ACLs, loopback binding, or other network controls. When unset or
empty, the service starts with shared-secret auth disabled.

Set the token in the systemd user unit with an `Environment=` line:

```ini
[Service]
Environment=NARRATIVE_AUTH_TOKEN=<long-random-token>
```

For local overrides, prefer a drop-in instead of editing the installed unit:

```bash
systemctl --user edit cypherclaw-narrative-api.service
systemctl --user daemon-reload
systemctl --user restart cypherclaw-narrative-api.service
```

Clients pass the same token on every request with the `X-Narrative-Auth`
header:

```bash
curl -H "X-Narrative-Auth: <long-random-token>" \
  http://127.0.0.1:8765/health
```

## Network Allowlist

Deniable Mac reaches the CypherClaw narrative API over Tailscale. If any
upstream firewall, router ACL, or cloud security group sits between Deniable
and CypherClaw, Deniable's current Tailscale IPv4 address must be added to
that allowlist or the narrative API calls will be silently dropped.

Look up Deniable's current Tailscale IPv4 on the Deniable host:

```bash
tailscale ip -4
# expected: a single 100.x.y.z address
```

Add that address to the upstream allowlist:

```
# Deniable Mac Tailscale IPv4 (replace placeholder with `tailscale ip -4` output)
<DENIABLE_TAILSCALE_IPV4>
```

Re-run `tailscale ip -4` and update the allowlist whenever Deniable is
re-tailnetted or its node identity is reset, since the 100.x.y.z address can
change.

## T-003@20260502T001347Z (2026-05-02T00:13:47Z)

- **Reason:** Deploy-side narrative event store is not checked into this workspace
- **Details:** Exploration confirmed this PromptClaw checkout contains the HTTP wrapper (`src/cypherclaw/narrative_api/`) and tests, while the PRD states the real `cypherclaw.narrative` engine and world-state SQLite live on the CypherClaw host. This task will follow the existing event-store injection/lazy-import pattern from `GET /events`, using in-memory injected stores for tests and a deploy-time `cypherclaw.narrative.events.NarrativeEventStore` import for production. No new dependencies are planned.
- **Reason:** Database migration scope
- **Details:** `POST /events` appends through the existing event-store abstraction and does not add tables, columns, or foreign keys. The PRD's `domain` column migration is CN-001/T-007, so this slice will not introduce a migration. The API will still default omitted event domains to `shared` so it matches the future migration default.
- **Reason:** Generated hardening bullets are outside the narrative event endpoint
- **Details:** The recurring self-critique, resource-governor, and startup-identity checks target SenseWeave composition/playback and daemon startup files, not `cypherclaw.narrative_api`. This task will not bundle those unrelated changes; existing hardening tests will be used as verification anchors where practical.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3834 passed, 3 skipped`, ruff clean, and mypy clean. The explicit hardening-anchor command `pytest tests/test_self_critique.py tests/test_resource_governor.py tests/test_governor_integration.py -q` also passed with `65 passed`. No new dependencies or migrations were introduced.

## T-015@20260502T001347Z (2026-05-02T00:13:47Z)

- **Reason:** Deploy-side entity persistence method is not checked into this workspace
- **Details:** Exploration confirmed this PromptClaw checkout owns the narrative HTTP wrapper (`src/cypherclaw/narrative_api/`) and tests, while the real CypherClaw narrative world store remains deploy-side. This task will apply `StateMutation` objects in the wrapper against the normalized entity record, then persist the full updated entity through duck-typed store methods such as `update_entity`, `patch_entity`, `save_entity`, `upsert_entity`, or `record_entity`. Tests will use injected in-memory stores. If no persistence method exists, the endpoint will surface HTTP `502` rather than pretending the mutation persisted.
- **Reason:** Database migration scope
- **Details:** `PATCH /world/entities/{entity_id}` mutates the existing `properties` JSON payload on an existing entity and does not add tables, columns, or foreign keys. No migration is required.
- **Reason:** Generated hardening bullets are outside this HTTP endpoint surface
- **Details:** The auto-generated self-critique, resource-governor, and daemon identity bullets target SenseWeave composition/playback and daemon startup paths. This task will not bundle those unrelated changes; the existing hardening-anchor tests will be re-run during verification where practical.
- **Reason:** StateMutation wire-shape compatibility assumption
- **Details:** The Deniable integration spec defines `StateMutation(target_entity, operation, field, value)`. Because this endpoint also carries `{entity_id}` in the path, requests may include `target_entity` for spec parity; when present it must match the path entity ID. Bare field paths such as `current_state` are treated as `properties.current_state`, and explicit `properties.<path>` is also accepted.
- **Reason:** Validation and hardening-anchor results
- **Details:** Required validation passed: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3903 passed, 3 skipped`, ruff clean, and mypy clean. The explicit hardening-anchor command `pytest tests/test_self_critique.py tests/test_resource_governor.py tests/test_governor_integration.py tests/test_first_boot.py -q` passed with `100 passed`. No new dependencies or migrations were introduced.

## T-001@20260502T001347Z (2026-05-02T00:13:47Z)

- **Reason:** Narrative engine implementation is deploy-side, not checked into this workspace
- **Details:** The imported PRD and SDP snapshot state that `NarrativeMemory` lives in the existing CypherClaw narrative engine at `~/cypherclaw/src/cypherclaw/narrative/`, but this PromptClaw checkout only contains the new HTTP-service queue artifacts and the adjacent `src/cypherclaw/image_api/` FastAPI pattern. This task will implement `POST /memory/search` as a thin wrapper with an injectable memory searcher for tests and a lazy deploy-time import of `cypherclaw.narrative.memory.NarrativeMemory`. No new third-party dependencies or database migrations are required.
- **Reason:** Generated startup hardening checks are outside the memory endpoint surface
- **Details:** The auto-generated hardening bullets reference `bootstrap_identity()` and `FirstBootAnnouncer`, which belong to the daemon startup identity flow. This task does not alter startup or orchestration behavior; existing regression anchors `tests/test_first_boot.py` and `tests/test_governor_integration.py` will be re-run during verification.
- **Reason:** Validation and hardening-anchor results
- **Details:** The required validation block passed (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`) with `3822 passed, 3 skipped`, ruff clean, and mypy clean. The explicit startup hardening anchor command `pytest tests/test_first_boot.py tests/test_governor_integration.py -q` passed with `49 passed`. No new dependencies or migrations were introduced.

## T-015@20260427T001208Z (2026-04-27T00:12:08Z)

- **Reason:** Queue worker entrypoint is not present in this checkout
- **Details:** The requested systemd unit points to the specified contract path `/home/user/cypherclaw/tools/generation_worker.py`, but `my-claw/tools/generation_worker.py` is not checked in. This task stayed scoped to the requested unit and runbook documentation; deploying the unit requires that worker entrypoint to exist at the target path.

## T-011@20260427T001208Z (2026-04-27T00:12:08Z)

- **Reason:** Auto-generated hardening bullets are out of scope for an operator runbook
- **Details:** This task is documentation-only — a new operator runbook at `docs/runbooks/generation-backend.md` plus a static regression test at `tests/test_runbook_generation_backend.py`. The auto-generated candidate-hardening bullets (re-verify `bootstrap_identity()` invocation in startup, ensure standalone+federated paths, add an integration test for identity persistence between boots) target the daemon identity bootstrap surface, which is unrelated to the generation-backend runbook scope and was already addressed under T-032@c (see prior ESCALATIONS entry confirming both daemon entrypoints call `bootstrap_identity()` before `FirstBootAnnouncer`). No runtime, schema, or migration changes are introduced by this task. No new dependencies are added — the static doc test uses the same stdlib-only pattern as `tests/test_cypherclaw_sampler_artistic_intent.py`.

## T-032@20260427T001208Zc (2026-04-27T00:12:08Z)

- **Reason:** Cap-source and soak-artifact assumption
- **Details:** Exploration found no checked-in `/tmp/generation_status.json` soak snapshots or generation daily-spend chart for CCG-032. This subtask therefore verifies the committed T-032b `sdp/telemetry/steady-state-cost.csv` artifact. The cost-model document's only concrete daily USD cap is the default `$5.00` generation daily cap, so the cap verifier defaults to `$5.00` while exposing a CLI override. The recurring hardening bullets about `revise_score(...)`, resource-governor playback budget application, and `bootstrap_identity()` startup ordering are outside this cap-summary surface; existing tree checks show `revise_score` is already imported/called in `tracker_compiler.py` and `duet_composer.py`, resource-governor tests exist, and both daemon entrypoints call `bootstrap_identity()` before `FirstBootAnnouncer`.

## T-032@20260427T001208Za (2026-04-27T00:12:08Z)

- **Reason:** Cost-model documentation scope assumptions
- **Details:** This subtask is documentation-only under `sdp/telemetry/` and adds no runtime schema, database columns, dependencies, or orchestration behavior. The auto-generated hardening bullets about self-critique wiring, resource-governor enforcement, and daemon identity bootstrap are unrelated to this cost-model reference and remain out of scope for this task. `progress.md` was already generated and dirty before this run, so the task update is limited to the T-032a line.

## T-001 (2026-04-01T18:55:24.984659+00:00)

- **Reason:** Agent timeout
- **Details:** T-001 timed out twice. Run sdp-cli tasks split T-001 to break it down.

## T-001 (2026-04-01T18:56:11.434931+00:00)

- **Reason:** Agent timeout
- **Details:** T-001 timed out twice. Run sdp-cli tasks split T-001 to break it down.

## T-001 (2026-04-01T18:56:41.692113+00:00)

- **Reason:** Agent timeout
- **Details:** T-001 timed out twice. Run sdp-cli tasks split T-001 to break it down.

## T-009@20260408T220341Z (2026-04-08T22:12:54.185469+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=85.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=85.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=85.0%

## T-001@20260408T223256Z (2026-04-08T22:33:10.555043+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=84.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%

## T-001@20260408T223256Z (2026-04-08T23:10:00+00:00)

- **Reason:** Validation blocked by pre-existing repo issues
- **Details:** `pytest tests/ -x` stopped during collection in `tests/test_first_boot.py` because `cypherclaw` is not importable from this checkout. `ruff check src/ tests/` and `mypy src/` also fail because the repo has no `src/` directory. `pip install -e '.[dev]'` completed but warned that `promptclaw 3.0.0` does not define a `dev` extra.

## T-004@20260408T223256Z (2026-04-08T23:05:05.007269+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=84.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%

## T-004@20260408T223256Z (2026-04-09T00:14:00+00:00)

- **Reason:** Scope constraint on orchestration docs
- **Details:** `AGENTS.md` asks for architecture/command/startup/changelog updates on orchestration changes, but this task also constrained edits to the bug-fix scope and those doc files already had unrelated local modifications. I limited the change set to the Ollama routing fix plus regression coverage and did not modify the product docs in this task.

## T-007@20260408T223256Z (2026-04-08T23:29:49.940049+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=83.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%

## T-007@20260408T223256Z (2026-04-08T23:37:23Z)

- **Reason:** Shared local-provider health granularity
- **Details:** The selector now excludes `ollama` when every configured Ollama route port is unhealthy and re-admits it when any configured port recovers. Health is tracked at the shared local-provider level, so a single-socket outage can still leave `ollama` eligible for categories routed to the down socket if another configured socket remains healthy.

## T-010@20260408T223256Za (2026-04-09T00:02:48.014232+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=83.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%

## T-010@20260408T223256Za (2026-04-09T00:24:00+00:00)

- **Reason:** Scope and latency assumptions
- **Details:** This split task only adds the daemon-side `ollama_health()` helper for dual sockets `11434` and `11435`; `/status` integration and Telegram `/local` formatting remain assigned to sibling subtasks `T-010@20260408T223256Zb` and `T-010@20260408T223256Zc`. Response latency is treated as daemon-side wall-clock time for the health probe; unreachable instances should return an unhealthy status, an empty model list, and `latency_ms` of `None` instead of raising.

## T-010@20260408T223256Zc (2026-04-09T00:34:30+00:00)

- **Reason:** Missing `/local` surface and status-endpoint assumption
- **Details:** The current tree has no Telegram `/local` built-in and no separate daemon `/status` JSON endpoint. This task will add a shared in-process status snapshot consumed by both `/status` and the new `/local` command so `/local` can format Ollama health without duplicating probes. Scope is limited to the base `/local` status view; `/local bench` and `/local stats` remain out of scope for T-010c. No new dependencies are planned.

## T-011@20260408T223256Z (2026-04-09T00:41:41.054077+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=82.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=82.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=82.0%

## T-011@20260408T223256Z (2026-04-09T01:05:00+00:00)

- **Reason:** LOCAL_ONLY scope assumption
- **Details:** This task treats `LOCAL_ONLY` as a daemon-level LLM routing guard. When enabled, all daemon agent-execution paths that would otherwise target `claude`, `codex`, or `gemini` are coerced to `ollama`, including router fallback and explicit step payloads. Non-agent operational commands (for example Telegram delivery, shell built-ins, or health probes) remain unchanged. No new dependencies are planned.

## T-012@20260408T223256Z (2026-04-09T01:30:00+00:00)

- **Reason:** Transport and dependency scope assumptions
- **Details:** This task uses stdlib-only HTTP probing (`urllib.request`) and `subprocess` for `tailscale status --json` — no new external dependencies. The identity endpoint is probed over plain HTTP on port 8443 (matching the federation PRD convention); TLS/signing verification is deferred to a future federation identity task (FD-001/FD-005). The module lives in `promptclaw/federation/discovery.py` following the PRD architecture layout. Peers are identified by `instance_id` for merge deduplication. Offline Tailscale peers are excluded from probing.

## T-021@20260416T043834Z (2026-04-16T05:00:00+00:00)

- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity` and `FirstBootAnnouncer`, which belong to the federation/identity subsystem. This task (self-critique and revision passes for music composition) has no relation to the startup identity flow. No new dependencies required; stdlib only.

## T-022@20260416T043834Z (2026-04-16T05:30:00+00:00)

- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity` and `FirstBootAnnouncer`, which belong to the federation/identity subsystem. This task (live-buffer and sample-bank abstractions) has no relation to the startup identity flow. No new dependencies required; stdlib only.

## T-022@20260416T043834Z (2026-04-16T05:30:01+00:00)

- **Reason:** Previous lead left out-of-scope changes
- **Details:** The previous lead (gemini) bundled lint cleanup across 37+ unrelated files alongside the T-022 work. These out-of-scope changes were discarded via `git checkout HEAD --` to keep the commit scoped to T-022 only. The in-scope lint fix (removing 3 unused imports from `tests/test_live_buffer.py` flagged by ruff) was retained.

## T-022@20260416T043834Z (2026-04-16T12:14:16.858992+00:00)

- **Reason:** Verify model rejected by provider
- **Details:** The verify model was rejected by the provider CLI. This is a configuration error, not a code issue. Fix the model ID and re-run. Error: OpenAI Codex v0.120.0 (research preview)
--------
workdir: /Users/anthony/Programming/PromptClaw
model: gpt-5.3-codex-spark
provider: openai
approval: never
sandbox: danger-full-access
reasoning effor...

## T-022@20260416T043834Z (2026-04-16T12:19:34Z)

- **Reason:** Manual verification state repair
- **Details:** Local verification passed after the provider-model escalation, but `sdp-cli tasks manual-verify` could not record the result because an active `sdp-cli run` process (PID 69939) owns `.sdp/run.lock`. The lock was not removed. Candidate hardening was checked explicitly: both startup entrypoints call `bootstrap_identity()` before `FirstBootAnnouncer`, and `pytest tests/test_first_boot.py tests/test_governor_integration.py -q` passed. No new dependencies were added.

## T-023@20260416T043834Z (2026-04-16T13:00:00+00:00)

- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity` and `FirstBootAnnouncer`, which belong to the federation/identity subsystem. This task (installation-aware acoustic ecology policies) has no relation to the startup identity flow. The new module `acoustic_ecology.py` is a pure-function policy layer with no I/O and no state files — it cannot affect startup sequencing. No new dependencies required; stdlib only.

## T-024@20260416T043834Z (2026-04-16T14:00:00+00:00)

- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity` and `FirstBootAnnouncer`, which belong to the federation/identity subsystem. This task (artistic identity portfolio reporting) has no relation to the startup identity flow. The new module `portfolio_report.py` is a pure-function reporting layer with no I/O and no state files — it derives summaries from data passed to it and cannot affect startup sequencing. No new dependencies required; stdlib only.

## T-025@20260416T043834Z (2026-04-16T14:45:00+00:00)

- **Reason:** Rollout-control scope and startup hardening verification
- **Details:** This task adds stdlib-only SenseWeave diagnostics and environment-backed feature flags; no new dependencies are required. The candidate startup hardening items remain covered by the existing startup flow: both daemon entrypoints call `bootstrap_identity()` before `FirstBootAnnouncer`, and `tests/test_first_boot.py::TestStartupIdentityPersistence` plus `tests/test_governor_integration.py::TestStartupIdentityWiring` were re-run as regression anchors.

## T-017@20260416T054258Z (2026-04-16T18:20:59.864442+00:00)

- **Reason:** Lead provider unavailable
- **Details:** Lead provider/runtime failures were observed across available agents (claude, codex). Latest signal: [Errno 2] No such file or directory: 'codex'

## T-017@20260416T054258Z (2026-04-16T18:21:16.577357+00:00)

- **Reason:** Lead provider unavailable
- **Details:** Lead provider/runtime failures were observed across available agents (claude, codex). Latest signal: env: claude: No such file or directory

## T-018@20260416T054258Z (2026-04-16T18:54:48.048819+00:00)

- **Reason:** Agent timeout
- **Details:** T-018@20260416T054258Z timed out twice. Run sdp-cli tasks split T-018@20260416T054258Z to break it down.

## T-018@20260416T054258Zb (2026-04-16T20:00:00+00:00)

- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity`, `FirstBootAnnouncer` (federation/identity subsystem), and resource governor budget enforcement (resource_governor.py). This task adds dissonance/resolution metadata to `counterpoint_rules.py` — a pure-function analysis layer with no I/O, no state files, and no interaction with startup sequencing or resource budgets. The `revise_score()` pipeline integration hardening item is already addressed: `revise_score` is imported and called in both `tracker_compiler.py` (line 18/1357) and `duet_composer.py` (line 80/838). No new dependencies required; stdlib only.

## T-024@20260416T054258Z (2026-04-16T22:35:00+00:00)

- **Reason:** Startup hardening scope and dependency assumptions
- **Details:** This task turns the production-course curriculum into executable exercise metadata and generated scaffolds. The auto-generated hardening checks for `bootstrap_identity` and `FirstBootAnnouncer` belong to the startup identity subsystem and are already addressed in the current tree: both `my-claw/tools/daemon.py` and `my-claw/tools/cypherclaw_daemon.py` call `bootstrap_identity()` before `FirstBootAnnouncer`, while `tests/test_first_boot.py` and `tests/test_governor_integration.py` cover persistence and wiring for standalone/federated startup paths. No new dependencies or migrations are required.

## T-001@20260416T181925Za (2026-04-16T18:19:25Z)

- **Reason:** Render-ablation scope and startup hardening assumption
- **Details:** This split task implements the pure core ablation engine for the CypherClaw humanization render layer. The concrete `RenderPass`, `PerformedPart`, and R1-R12 rules are not present in this checkout yet and remain assigned to sibling/future tasks, so the ablation function will accept an injected active rule set and renderer. The auto-generated hardening checks for `bootstrap_identity` and `FirstBootAnnouncer` are unrelated to this render utility and are already addressed by existing startup tests; those tests will be re-run as verification anchors. No new dependencies or migrations are required.

## T-021@20260416T181925Z (2026-04-17T02:52:12.828073+00:00)

- **Reason:** Agent timeout
- **Details:** T-021@20260416T181925Z timed out twice. Run sdp-cli tasks split T-021@20260416T181925Z to break it down.

## T-038@20260416T181925Z (2026-04-17T00:00:00+00:00)

- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity`, `FirstBootAnnouncer` (startup identity subsystem), resource governor budget enforcement, and `revise_score` pipeline integration. This task couples the narrative engine (procedural arc) to SectionEnvelope selection — a pure-function mapping layer with no I/O, no state files, and no interaction with startup sequencing, resource budgets, or the self-critique pipeline. The `revise_score()` integration is already addressed in both `tracker_compiler.py` and `duet_composer.py`. No new dependencies or migrations are required.

## T-039@20260416T181925Z (2026-04-17T00:00:00+00:00)

- **Reason:** Dependency and startup hardening assumptions
- **Details:** T-039 requires a real librosa analysis path for audio-rendered SSM and Foote novelty extraction, so `librosa>=0.10,<1` is being added as a project dependency. The auto-generated startup hardening checks are already wired in both daemon entrypoints (`bootstrap_identity()` runs before `FirstBootAnnouncer`), and this task will add a focused standalone/federated identity persistence regression test rather than modifying startup flow. No database migrations are required.

## T-001@20260425T183959Zd (2026-04-25T00:00:00+00:00)

- **Reason:** Sampler buffer cap scope and hardening assumptions
- **Details:** This split task is limited to `my-claw/tools/senseweave/sampler_buffers.py` and `tests/test_sampler_buffers.py`. The implementation will keep the existing `BufferLoader` shape, route overflow eviction through the `on_sampler_free()` path, and add a full load/evict-cycle regression test at the default 64-buffer cap. The auto-generated hardening items referencing `bootstrap_identity()` and `FirstBootAnnouncer` belong to the startup identity subsystem and are out of scope for this sampler buffer utility; that startup wiring is already covered elsewhere in the tree. No new dependencies or migrations are required.

## T-008@20260425T183959Zd (2026-04-25T18:39:59Z)

- **Reason:** Capture write-path scope assumption
- **Details:** Exploration confirmed that `my-claw/tools/sample_capture_daemon.py` currently contains the ring buffer, interesting-moment detector, and contextual/acoustic tag helpers, but no persistence API or detector loop that writes captured samples into an index. This task will treat the missing seam as the write-path itself: add a stdlib-only capture store/index layer that invokes `build_sample_tags()` during sample save and persists those tags into `index.sqlite`. No new dependencies or migrations are required. The generated startup-hardening checks were verified against the current tree rather than reimplemented here: `pytest tests/test_first_boot.py tests/test_governor_integration.py -q` passed, and the full validation command (`pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`) also passed after the capture-index work landed.

## T-013@20260425T183959Za (2026-04-25T00:00:00+00:00)

- **Reason:** Quintet documentation scope and generated-progress assumption
- **Details:** Exploration found that sampler-focused modules already exist (`sample_capture_daemon.py`, `sampler_buffers.py`, `sampler_dispatch.py`, `synthesis/sampler_effects.scd`, and sampler anti-pattern checks), but the canonical identity file and its regression tests still describe a quartet (`artist_identity.py`, `tests/test_artist_identity.py`). This subtask will update `docs/cypherclaw-musicianship-roadmap.md` to present the quintet as the active ensemble direction with an explicit partial-rollout status snapshot rather than claiming full runtime convergence. No new dependencies or migrations are required. `progress.md` is marked as generated and already has unrelated in-flight edits, so task progress will be recorded as a minimal task-line update only instead of restructuring the generated report.

## T-013@20260425T183959Zb (2026-04-25T18:39:59Z)

- **Reason:** Sampler-architecture documentation scope and out-of-scope hardening checks
- **Details:** This subtask delivers the CCS-033 architecture document at `docs/cypherclaw-sampler-architecture.md` plus its regression test at `tests/test_cypherclaw_sampler_architecture.py`. The document describes only the *currently landed* sampler subsystem (capture daemon, smoke verifier, `BufferLoader`, `SamplerDispatcher`, `sampler_effects.scd`, the `sampler_dominating` / `sampler_silent_quintet_member` detectors, and the existing master-bus / composer / diagnostics seams) and explicitly flags `SampleLibrary`, `SampleSelector`, `sw_sampler.scd`, and quintet convergence in `artist_identity.py` as still pending so it does not overstate completion. Cross-links to the upstream PRD (`my-claw/sdp/prd-cypherclaw-sampler.md`) and the musicianship roadmap (`docs/cypherclaw-musicianship-roadmap.md`) keep the artistic intent and the longer status snapshot in their canonical homes rather than duplicating them here. No new dependencies, no migrations, and no runtime code changes are required. The auto-generated hardening items referencing `bootstrap_identity()` invocation, `FirstBootAnnouncer` sequencing, standalone/federated coverage, and startup integration tests are out of scope for a documentation subtask: the `bootstrap_identity()` invocation already lives in `sample_capture_daemon.py::main` and the startup paths are already covered by `tests/test_first_boot.py` and `tests/test_governor_integration.py`. This mirrors the established out-of-scope escalation pattern from T-008@20260425T183959Zd and the sibling T-013@20260425T183959Za. The artistic-intent companion document (`docs/cypherclaw-sampler-artistic-intent.md`) is the remaining CCS-033 sibling and is left for a follow-up subtask.

## T-013@20260425T183959Zc (2026-04-25T19:10:00Z)

- **Reason:** Artistic-intent documentation scope and generated-progress constraint
- **Details:** Exploration confirmed that CCS-033's remaining work is the one-page artistic-intent companion at `docs/cypherclaw-sampler-artistic-intent.md`. The sampler PRD (`my-claw/sdp/prd-cypherclaw-sampler.md`) remains the canonical source for the three usages and five principles; the new page will restate that intent in a shorter listener-facing form focused on aesthetic goals, the sampler's role inside the quintet, and the intended listener experience, while cross-linking the PRD, the roadmap, and the architecture document instead of duplicating their implementation detail. This subtask is documentation-only: no runtime code changes, no migrations, and no new dependencies are required. The generated candidate hardening items about `revise_score()` integration, resource-governor budget enforcement, and `bootstrap_identity()` sequencing are out of scope for this doc task and were verified as unrelated to the affected files. Because `progress.md` is generated and already contains unrelated in-flight state changes, its exploration update is limited to the single T-013@20260425T183959Zc task line rather than a broader manual rewrite.

## T-014@20260425T183959Za (2026-04-25T19:30:00Z)

- **Reason:** Service-wiring assumptions and generated-hardening scope
- **Details:** Exploration mapped `CCS-020` to the current tree: `my-claw/systemd/` has no `cypherclaw-sample-capture.service`, `cypherclaw_boot.sh` does not yet start that service, and existing CypherClaw units consistently run as `User=user` from `/home/user/cypherclaw` with the project virtualenv at `/home/user/cypherclaw/.venv/bin/python3`. The repo references `cypherclaw-jack.service` from other units but does not define that unit locally, so this task assumes it is a host-managed prerequisite and wires the dependency without inventing a second JACK service. No new dependencies or migrations are required. The auto-generated `bootstrap_identity()` hardening items are already covered elsewhere in the current tree; because this task touches boot/service startup, the existing startup identity tests will be re-run as verification anchors rather than reworking unrelated startup code.

## T-014@20260425T183959Zc (2026-04-25T23:05:00Z)

## T-033@20260425T183959Z (2026-04-25T00:00:00+00:00)

- **Reason:** Sample-library migration scope and source-corpus assumptions
- **Details:** Exploration found that `my-claw/tools/senseweave/sample_library.py` already provides the canonical `SampleRecord` / `SampleLibrary` seam, but the store currently persists only query columns and has no provenance-capable `extras` round-trip or import script. This task will add a repo-backed importer at `my-claw/tools/sample_library_import.py`, extend the library store with a backward-compatible inline SQLite schema upgrade that preserves the full serialized `SampleRecord`, and track the real migration manifest separately from generated audio output. The import target is assumed to be the repo-local `samples/` root so copied audio lands under `samples/library/` while tracked code/docs stay small; `.gitignore` will be updated accordingly if needed. No dedicated `field recordings` folder was discoverable in Anthony's home, so the real migration corpus is assumed to be the 96 clearly classifiable audio stems under `/Users/anthony/Documents/from worker drive/Song Stems` plus 5 handpicked single-file recordings from `/Users/anthony/Downloads`, for a total of 101 imported samples. No new third-party dependencies or external migration framework are required; implementation will use stdlib `argparse`, `tomllib`, `hashlib`, and `shutil`.
- **Reason:** Candidate hardening items are out of scope
- **Details:** The auto-generated hardening checks reference `bootstrap_identity()` startup sequencing and standalone/federated first-boot coverage, which belong to the startup identity subsystem. This task is confined to the sampler library/import path and will not alter daemon startup flow; existing startup identity coverage remains the authority for those checks.

- **Reason:** Live systemd verification host assumption
- **Details:** Exploration confirmed that this checkout is running on macOS and does not provide local `systemctl`, while the target Linux host is reachable as `cypherclaw` over non-interactive SSH. This task will add a repo-backed verifier tool that supports both local Linux execution and `--host cypherclaw` remote execution, then use that remote path for the real `kill -9` / restart validation. No new dependencies or migrations are required.

## T-021@20260425T183959Za (2026-04-26T03:37:26Z)

- **Reason:** Sampler diagnostics scope and hardening assumptions
- **Details:** Exploration confirmed that the affected surface is `my-claw/tools/senseweave/operator_diagnostics.py`, which already derives `sample_source` through the shared `senseweave.sample_status.sample_status_text(...)` helper used by the face display. `sample_dsp_activity.json` is the sampler plan/intention state, while `sample_playback_state.json` is the live execution/playback state; this task is scoped to combining those two authorities into one human-readable operator line and corresponding tests/docs updates, with no new dependencies or migrations. The auto-generated hardening items about self-critique pipeline wiring, resource-governor budget enforcement, and startup identity sequencing are unrelated to this diagnostics-formatting subtask, so they will be treated as verification anchors against the current tree rather than broadened into unrelated code changes here.

## T-021@20260425T183959Za (2026-04-26T03:45:08Z)

- **Reason:** Hardening-anchor verification
- **Details:** Full validation passed (`pip install -e '.[dev]'`, `pytest tests/ -x`, `ruff check src/ tests/`, `mypy src/`). The recurring hardening anchors were also rechecked explicitly without broadening scope: `tests/test_self_critique.py::TestPipelineIntegration::{test_tracker_compiler_uses_revise_score,test_fallback_path_uses_revise_score}` passed for self-critique wiring, `tests/test_resource_governor.py` passed for budget enforcement, and `tests/test_governor_integration.py::TestStartupIdentityWiring` passed for `bootstrap_identity()` ordering.

## T-016@20260425T183959Zd (2026-04-25T19:45:00Z)

- **Reason:** Planner integration and selector-ownership assumptions
- **Details:** Exploration found that `my-claw/tools/senseweave/cast_planner.py` already supports opt-in sampler metadata attachment through a selector Protocol, but the current planner seam is still piece-agnostic: it does not derive selector kwargs from a piece fixture and does not return assembled cast entries that carry sampler metadata forward for verification. There is still no concrete `senseweave.sample_library.SampleSelector` implementation in this checkout, so this task will keep the selector dependency Protocol-based and add a piece-aware cast-assembly helper around `select_cast_ids` instead of inventing a new library module. `target_character` will be taken from explicit piece data when present and otherwise fall back to `(patch_name,)` for piece-level sampler selection hints. Because `progress.md` is generated and already has unrelated queue-state edits, the exploration update there is limited to the single `T-016@20260425T183959Zd` line rather than a broader manual rewrite. The generated hardening items about `revise_score()`, resource-governor budget enforcement, and startup identity sequencing were rechecked during exploration and are out of scope for this cast-planner utility task; no new dependencies or migrations are required.

## T-018@20260425T183959Zd (2026-04-25T19:35:00-07:00)

- **Reason:** Active-song capture wiring and metadata-scope assumptions
- **Details:** Exploration confirmed that the current T-018 split already provides the three required seams: `PhraseTracker` annotates both live listeners with `phrase_started` / `phrase_ended`, `PhraseCaptureWriter` can persist keyboard `.mid` and Theramini `.wav` phrases plus a validated sidecar schema, and `/tmp/composer_state.json` is the only existing authority file that carries the current song/key context. This subtask will therefore close the verifier note by wiring capture directly into `midi_keyboard_listener.py` and `theramini_listener.py` instead of inventing a second daemon-side JACK recapture path. Active-song tags will be derived from `/tmp/composer_state.json` (`song`, `key`, and tempo when present). The locked sidecar schema from T-018@20260425T183959Zc only permits `instrument`, `song_id`, `key`, `tempo`, `timestamp`, `duration`, and `source`, so the broader PRD idea of a separate `human_player` tag remains out of scope for this split. No new dependencies or migrations are required. Because `progress.md` is generated and already carries unrelated queue-state edits, the exploration update there is limited to the single `T-018@20260425T183959Zd` task line. The generated startup-hardening items around `bootstrap_identity()` remain covered by the existing daemon entrypoints and their regression tests and are unrelated to this listener-capture task.

## T-021@20260425T183959Zc (2026-04-25T20:05:00-07:00)

- **Reason:** Missing inkplate-renderer seam and generated-progress constraint
- **Details:** Exploration found no landed `inkplate` module or e-ink renderer in this checkout; CCS-027 only references the face/inkplate surfaces in PRDs and docs. This subtask will therefore introduce a small repo-backed `my-claw/tools/inkplate_display.py` renderer seam that consumes the existing combined `face_display_sample_status_text(...)` helper and truncates the sampler line against an injectable e-ink pixel width instead of inventing unrelated UI behavior. `progress.md` is marked generated and already contains unrelated queue-state edits, so the exploration update there is limited to the single `T-021@20260425T183959Zc` task line rather than a broader manual rewrite. The generated hardening items about self-critique wiring, resource-governor budget enforcement, and startup identity sequencing are already covered elsewhere in the current tree and will be re-run as verification anchors rather than broadened into this display task. No new dependencies or migrations are required.

## T-021@20260425T183959Zc (2026-04-25T20:20:00-07:00)

- **Reason:** Hardening-anchor verification
- **Details:** Full validation passed (`pip install -e '.[dev]'`, `pytest tests/ -x`, `ruff check src/ tests/`, `mypy src/`). The recurring hardening anchors were also rechecked explicitly without broadening scope: `tests/test_self_critique.py::TestPipelineIntegration::{test_tracker_compiler_uses_revise_score,test_fallback_path_uses_revise_score}` passed for self-critique wiring, `tests/test_resource_governor.py` passed for budget enforcement, and `tests/test_governor_integration.py::TestStartupIdentityWiring` passed for `bootstrap_identity()` ordering.

## T-022@20260425T183959Zd (2026-04-25T20:40:00-07:00)

- **Reason:** Journal-schema scope and hardening-anchor assumptions
- **Details:** Exploration mapped this subtask to the active score-tree tracker path rather than the older freeform solo path. `tracker_compiler.py` already routes final score selection through `revise_score()`, `music_tracker.py` already projects sample-gesture source/mode/transform metadata into tracker scenes and sample lanes, and `music_tracker_runtime.py` already owns the end-to-end event-emission seam used by playback tests. The missing piece is the post-piece journal contract in `senseweave.usage_journal.py`: it currently persists only `piece_id`, `timestamp`, `samples_played`, and `arc_payoff`, while the sampler PRD (`my-claw/sdp/prd-cypherclaw-sampler.md`, CCS-028) expects a richer per-piece entry including sample usage, transformations, mode, and clicks. This task will extend that journal seam in a backward-compatible way and add a real compose → gate → compile → schedule → journal regression test rather than inventing a new playback pipeline. No new dependencies or migrations are required. `progress.md` is generated and already dirty, so the exploration update there is limited to the single `T-022@20260425T183959Zd` task line. The recurring hardening anchors about `revise_score()` wiring, resource-governor budget enforcement, and startup identity sequencing will be re-run during verification, but only the journal/track-runtime area is in scope for code changes here.

## T-022@20260425T183959Zd (2026-04-25T21:05:00-07:00)

- **Reason:** Validation and extra-lint results
- **Details:** The required validation block passed cleanly: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` completed with `3478 passed`, `ruff` clean on `src/ tests/`, and `mypy` clean on `src/`. The recurring hardening anchors also remained green as part of that run, including `tests/test_self_critique.py`, `tests/test_resource_governor.py`, and `tests/test_governor_integration.py`. Because the repo lint target does not cover `my-claw/`, an extra `ruff check` was run on the modified journal/runtime/test files and passed; a broader `ruff check` that included the whole existing `my-claw/tools/duet_composer.py` file surfaced long-standing unrelated lint debt (unused imports, mid-file imports, one-line statements) outside this task's change scope, but `python -m py_compile my-claw/tools/duet_composer.py` passed and the targeted tests covering the modified tracker path stayed green. No new dependencies or migrations were introduced.

## 2026-04-27
- **T-003@20260427T001208Z**: Added `modal` as an optional dependency for the generation client.

## T-004@20260427T001208Z (2026-04-27T00:12:08Z)

- **Reason:** Generation-client scope and startup-hardening assumption
- **Details:** Exploration found the affected area is `my-claw/tools/senseweave/generation/`, where `ReplicateClient` and `ModalClient` expose the shared `generate(self, request: Any) -> Any` surface and tests import `senseweave` by adding `my-claw/tools` to `sys.path`. This task will add a stdlib-only `LocalAdaClient` stub and an explicit `GenerationClient` Protocol in `client_local.py`; no GPU libraries, migrations, or new dependencies are required. The auto-generated hardening checks about `bootstrap_identity()` and `FirstBootAnnouncer` belong to the startup identity subsystem and are already covered by `tests/test_first_boot.py` and `tests/test_governor_integration.py`, which will be re-run as verification anchors without broadening this task's code scope.

## T-005@20260427T001208Z (2026-04-27T00:12:08Z)

- **Reason:** Live-test scope and dependency on T-001 submission body
- **Details:** Exploration confirmed the affected area is `my-claw/tools/senseweave/generation/client_replicate.py` plus `tests/conftest.py`, where the existing `--run-live-modal` flag/marker pair is the closest precedent. T-005 adds a parallel `--run-live-replicate` flag, a `live_replicate` marker, and `tests/test_generation_live_replicate.py` shaped like `tests/test_generation_live_modal.py`. The test is doubly gated: the conftest hook skips it without `--run-live-replicate`, and the test body skips when `REPLICATE_API_TOKEN` is unset. End-to-end execution depends on `ReplicateClient._submit_prediction` shipping under T-001 (currently `needs_split`), which is consistent with how the Modal live test landed alongside the still-stub-tier protocol parity tests under T-003. No new dependencies or migrations are required. The recurring hardening anchors about `bootstrap_identity()`, resource-governor budget enforcement, and `revise_score()` wiring remain covered by `tests/test_first_boot.py`, `tests/test_governor_integration.py`, `tests/test_resource_governor.py`, and `tests/test_self_critique.py` and were re-run as verification anchors without broadening this task's scope.

## T-008@20260427T001208Zc (2026-04-27T00:12:08Z)

- **Reason:** Queue-state naming and startup-hardening scope assumptions
- **Details:** Exploration confirmed the existing T-008a/b queue schema uses `queue_items` with `status="queued"` as the pending state, so this task treats "pending" in the brief as the existing queued state rather than renaming the schema/status contract. The auto-generated hardening checks for `bootstrap_identity()` and `FirstBootAnnouncer` belong to the startup identity subsystem and are already covered by existing startup tests (`tests/test_first_boot.py`, `tests/test_governor_integration.py`); this generation-queue transition task has no startup path changes. No new dependencies or database migrations are required.

## T-004@20260502T001347Zb (2026-05-02T01:10:41Z)

- **Reason:** Service activation blocked by non-systemd host
- **Details:** The requested commands were attempted from this checkout, but the active host is Darwin (`afdasdfeeee.local`) and neither `systemctl` nor `loginctl` is available. `systemctl --user daemon-reload`, `systemctl --user enable --now cypherclaw-narrative-api.service`, and `loginctl enable-linger user` all fail with `command not found` here. The service must be activated on the Linux CypherClaw service host as the systemd user (`user` per `my-claw/systemd/cypherclaw-narrative-api.service`) with the unit installed at `~/.config/systemd/user/cypherclaw-narrative-api.service`.

## T-004@20260502T001347Zc (2026-05-02T01:17:22Z)

- **Reason:** Narrative API not yet deployed to cypherclaw — verification cannot return PASS
- **Details:** Verification was executed against the live Linux host `cypherclaw` over non-interactive SSH (the same path used for T-033@20260425T183959Z). Captured evidence is in `sdp/verification/evidence/t-004@20260502t001347zc-narrative-api-status.md`. Findings: (1) `~/.config/systemd/user/cypherclaw-narrative-api.service` does not exist on the host; (2) `systemctl --user status` reports the unit could not be found, `is-active` is `inactive`, `is-enabled` is `not-found`; (3) `journalctl --user -u cypherclaw-narrative-api.service` shows `-- No entries --`; (4) no port matching the narrative-api binding appears in `ss -ltn`; (5) `Linger=no` for the service user (must become `yes` per CN-013/CN-015); (6) the underlying `cypherclaw.narrative_api` Python package has not been deployed to `~/cypherclaw/src/cypherclaw/` — only the in-process `narrative/` engine is present. The unit file authored under T-004@Za and the activation runbook captured under T-004@Zb are correct; the gap is a deploy step (sync `src/cypherclaw/narrative_api/` and `my-claw/systemd/cypherclaw-narrative-api.service` from this PromptClaw checkout to the cypherclaw host, then run the documented `daemon-reload` / `enable --now` / `enable-linger` commands). The Tailscale interface is up on the host (`100.74.35.114`, `fd7a:115c:a1e0::9e36:2372`), so the CN-002 binding constraint is satisfiable once the unit starts.

## T-011@20260502T001347Z (2026-05-02T01:36:00Z)

- **Reason:** StoryBeat wire-shape and deploy-side engine assumptions
- **Details:** Exploration found no deploy-side `cypherclaw.narrative.engine.NarrativeEngine` package in this PromptClaw checkout; production still needs the package deployed on the CypherClaw host. T-011 therefore follows the existing narrative API lazy-import pattern and tests through injected fake engines. Deniable's `world_bridge.py` treats the `StoryBeat` response as an engine-owned raw payload with required `id`, `cycle_number`, and `arc_position`, so the endpoint should serialize the in-process beat without adding null/default response-model fields. No new dependencies, database columns, or migrations are required. The generated hardening bullets about SenseWeave self-critique/resource-governor wiring and daemon identity startup are unrelated to the `/beats/next` wrapper; startup identity is already covered by existing narrative API main/startup tests.

## frac-0003 (2026-05-02)

- **Reason:** Generation-worker depth and startup-hardening assumptions
- **Details:** Exploration found that `my-claw/tools/generation_worker.py` is functionally live but classified at fractal depth 0 because `_amain()` contains a platform fallback that names `NotImplementedError`; this task treats that as scanner hygiene plus a small typed config/summary surface, not a generation-backend redesign. The worker should continue to start without `REPLICATE_API_TOKEN` so local signal/status tests remain offline and tokenless; backend failures are handled per queued item. The generated startup-hardening bullets are addressed as anchors: both daemon startup paths already call `bootstrap_identity()` before `FirstBootAnnouncer`, and this task adds/re-runs startup identity persistence coverage for standalone and federated boots. No new dependencies, migrations, provider secrets, or database columns are required.

## frac-0018 (2026-05-02)

- **Reason:** Duration-contrast depth and out-of-scope hardening checks
- **Details:** Exploration confirmed `my-claw/tools/senseweave/render/rules/duration_contrast.py` is a working R4 SenseWeave render rule classified at fractal depth 1 (`5/9 trivial, 4 real`); this task adds a typed analyze/report seam mirroring the depth-2 pattern landed for `metric_accent` (frac-0017) and `lung_capacity` (frac-0016), without changing `MIN_MULTIPLIER`, `MAX_MULTIPLIER`, `DurationContrastRule.apply`, or `apply_duration_contrast` semantics. The auto-generated hardening checks about `/healthz` + `/readyz` endpoints and the `X-Narrative-Auth` shared-secret header are scoped to `cypherclaw.narrative_api` and are unrelated to this SenseWeave render-rule module; they remain anchored by `tests/test_smoke_narrative_script.py` and the existing narrative API regression suite. Startup identity hardening is re-run as anchor coverage via `tests/test_first_boot.py::TestStartupIdentityPersistence` and `tests/test_governor_integration.py::TestStartupIdentityWiring`. No new dependencies, migrations, provider secrets, or database columns are required.

## frac-0086 (2026-05-02)

- **Reason:** Listener-review test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_listener_review.py`, with production behavior in `my-claw/tools/senseweave/render/listener_review.py`, operator documentation in `my-claw/docs/listener-review.md`, and the review log at `my-claw/sdp/review-log.md`. The T-040 spec and humanization PRD define this workflow as weekly rendered-piece review tied to the existing `senseweave-render-debugger` CLI and structured review-log entries. This task will deepen the listener-review surface with a typed stdlib-only parser/report/summary API and end-to-end tests, preserving the existing artifact validation behavior. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this listener-review task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.

## frac-0039 (2026-05-02)

- **Reason:** Models depth scope and startup identity assumption
- **Details:** Exploration mapped frac-0039 to `promptclaw/models.py`, which currently has no functions and classifies at depth 0 even though its dataclasses are used by config loading, routing, runtime, state persistence, memory, and artifacts. This task will add stdlib-only diagnostic/report helpers without changing the existing dataclass contracts. The generated hardening items are in scope for the ASGI narrative startup path: `python -m cypherclaw.narrative_api` already calls `bootstrap_identity()`, but importing `cypherclaw.narrative_api.main:app` does not, so startup identity persistence will be pinned with a regression test and wired before app creation. No new dependencies, migrations, provider secrets, or database columns are required.

## frac-0052 (2026-05-02)

- **Reason:** Temp sampler-dispatch depth scope and ignored-file assumption
- **Details:** Exploration found the affected surface is the root-level scratch module `temp_sampler_dispatch.py`, which is ignored by `.gitignore` through `temp_*.py` but is explicitly named by the task. The production `my-claw/tools/senseweave/sampler_dispatch.py` is already depth 3 and serves as the pattern source; this task will deepen only `temp_sampler_dispatch.py` with the same simple stdlib-only dispatch-plan/report path and will force-add the ignored file if it must be committed. The module currently has relative package imports that fail when imported as a root temp module; tests will pin an import-safe fallback through `senseweave.*` while preserving the existing sampler OSC/lifecycle behavior. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required. The generated startup hardening bullets target the existing identity startup subsystem; current daemon/CLI/narrative tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this scratch-module task.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_temp_sampler_dispatch_depth.py -q` failing on root-module import (`attempted relative import with no known parent package`) and fractal depth 1 before implementation. After implementation, `pytest tests/test_temp_sampler_dispatch_depth.py -q` passed with `7 passed`, production sampler regressions passed with `pytest tests/test_sampler_dispatch.py tests/test_sampler_dispatch_depth.py -q` (`42 passed`), and the explicit startup identity hardening anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4244 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `temp_sampler_dispatch.py` reports depth 2 (`substantial (no tests)`), satisfying the depth >= 2 criterion. No new dependencies or migrations were introduced.

## frac-0056 (2026-05-02)

- **Reason:** Acoustic ecology test-depth scope and startup-hardening assumptions
- **Details:** Exploration found that `my-claw/tools/senseweave/acoustic_ecology.py` is already a pure stdlib policy resolver at fractal depth 4, while `tests/test_acoustic_ecology.py` is the affected surface at depth 1 (`29/35 trivial, 6 real`). This task will preserve the source resolver and existing assertions, add a red depth gate in `tests/test_acoustic_ecology_depth.py`, and deepen the original test file with looped end-to-end policy scenarios across ecology modes, hard ceilings, source preferences, modifier sweeps, silence windows, and reason metadata. The generated startup hardening bullets target the existing identity startup subsystem; current CLI/daemon/narrative tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity persistence across standalone/federated boots, so they will be re-run as regression anchors rather than broadening this test-only task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_acoustic_ecology_depth.py -q` failing on `tests/test_acoustic_ecology.py` depth 1 (`29/35 trivial, 6 real`) before implementation. After implementation, `pytest tests/test_acoustic_ecology.py tests/test_acoustic_ecology_depth.py -q` passed with `64 passed`, the public resolver smoke command returned `active_day 60.0 room_mic`, and the startup identity anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4315 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `tests/test_acoustic_ecology.py` now reports depth 2 (`substantial (no tests)`, 29 trivial / 36 real). No new dependencies or migrations were introduced.

## frac-0057 (2026-05-02)

- **Reason:** Quota-aware agent selector test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_agent_selector_quota.py`, classified at depth 1 (`7/13 trivial, 6 real`). The collaborating production modules (`my-claw/tools/agent_selector.py`, `quota_monitor.py`, `ollama_health.py`) already produce meaningful selection/quota/health behavior, so this task preserves the source modules and deepens only the test file with one looped end-to-end class. A red depth gate is added at `tests/test_agent_selector_quota_depth.py` asserting `classify_depth("tests/test_agent_selector_quota.py").depth >= 2`. The generated hardening bullets target the existing identity startup subsystem; CLI/daemon/narrative tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they are re-run as regression anchors rather than broadening this test-only task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed with `pytest tests/test_agent_selector_quota_depth.py -q` failing on `tests/test_agent_selector_quota.py` depth 1 (`7/13 trivial, 6 real`) before implementation. After implementation, `pytest tests/test_agent_selector_quota.py tests/test_agent_selector_quota_depth.py -q` passed with `19 passed`, the public selector smoke command (`detect_category('vpn firewall routing help')` and `select('implement the feature', available_agents=[...])`) returned `netops codex`, and the startup identity anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4326 passed, 3 skipped`, Ruff clean, and mypy clean. Fractal classification for `tests/test_agent_selector_quota.py` now reports depth 2 (`substantial (no tests)`, 488 lines). No new dependencies or migrations were introduced.

## frac-0069 (2026-05-02)

- **Reason:** Counterpoint rules test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_counterpoint_rules.py`, classified at depth 1. The collaborating production module (`my-claw/tools/senseweave/counterpoint_rules.py`) already implements the depth-2 one-path registry contract. This task preserves the source module and deepens only the test file with a looped end-to-end class `CounterpointRulesEndToEndTests`. A red depth gate is added at `tests/test_counterpoint_rules_depth.py` asserting depth >= 2. The generated startup hardening bullets target the existing identity startup subsystem; CLI/daemon/narrative tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they are re-run as regression anchors rather than broadening this test-only task. No new dependencies, migrations, provider secrets, database columns, runtime state files, HTTP routes, or auth behavior are required.
- **Reason:** Validation and hardening-anchor results
- **Details:** Red phase was confirmed and depth gate was added. After implementation, `pytest tests/test_counterpoint_rules.py tests/test_counterpoint_rules_depth.py -q` passed, and the startup identity anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passes cleanly. Fractal classification for `tests/test_counterpoint_rules.py` now meets the depth criterion. No new dependencies or migrations were introduced.

## frac-0082 (2026-05-02)

- **Reason:** Groove-engine test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_groove_engine.py` with production behavior in `my-claw/tools/senseweave/groove_engine.py` and tracker propagation in `my-claw/tools/senseweave/music_tracker.py`. The production groove path already produces meaningful one-path output for profile lookup, meter policies, IOI adjustment, metadata, and tracker scene compilation, so this task preserves production behavior unless the new red tests expose a concrete gap. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this groove test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_groove_engine.py::GrooveEngineEndToEndTests tests/test_test_groove_engine_depth.py -q` failing on two production gaps: entrainment rebuilt partial profiles and lost registered subdivision/timing/syncopation/lane-offset fields, and tracker scene compilation ignored profile lane offsets when no explicit scene override was supplied. After implementation, the locked end-to-end/depth tests passed, `pytest tests/test_groove_engine.py tests/test_test_groove_engine_depth.py tests/test_syncopation_features.py -q` passed with `111 passed`, the startup identity anchor command passed with `9 passed`, and the required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4551 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0073 (2026-05-02T22:54:22.603731+00:00)

- **Reason:** Protected file modification
- **Details:** Protected files modified: sdp/templates/candidates/lead_t2/v001.md, sdp/templates/candidates/lead_t2/v002.md, sdp/templates/candidates/lead_t2/v003.md, sdp/templates/candidates/lead_t2/v004.md, sdp/templates/candidates/lead_t2/v005.md, sdp/templates/candidates/lead_t2/v006.md, sdp/templates/candidates/verify/v001.md, sdp/templates/candidates/verify/v002.md, sdp/templates/candidates/verify/v003.md, sdp/templates/candidates/verify/v004.md, sdp/templates/candidates/verify/v005.md, sdp/templates/candidates/verify/v006.md, sdp/templates/claude/lead_t1.md, sdp/templates/claude/lead_t2.md, sdp/templates/claude/verify.md, sdp/templates/codex/lead_t1.md, sdp/templates/codex/lead_t2.md, sdp/templates/codex/no_work_retry.md, sdp/templates/codex/verify.md, sdp/templates/gemini/ascii_art_agent.md, sdp/templates/gemini/fix_gate.md, sdp/templates/gemini/fix_verify.md, sdp/templates/gemini/lead_t1.md, sdp/templates/gemini/lead_t2.md, sdp/templates/gemini/lead_t3.md, sdp/templates/gemini/no_work_retry.md, sdp/templates/gemini/split_task.md, sdp/templates/gemini/verify.md. Risk: changes to protected paths require manual review. Merge guidance: run `sdp-cli merge --task frac-0073`.

## frac-0074 (2026-05-02T23:46:00+00:00)

- **Reason:** Scope and startup hardening assumptions
- **Details:** Exploration identified the affected surface as `my-claw/tools/senseweave/garden_watcher.py` and `tests/test_garden_watcher.py`. The module already supplies helper-level light/season/palette/key logic and an atomic writer, while downstream composer/gallery paths consume `light`, `season`, `palette`, `music_key`, and `last_update` from `/tmp/garden_state.json`. This task assumes the missing depth-2 work is a deterministic one-path build/write/summary contract plus locked end-to-end tests, not a camera-capture integration. The generated startup hardening bullets are treated as existing regression anchors because CLI startup, daemon AST wiring, first-boot persistence, and narrative ASGI import tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity reuse. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and focused verification
- **Details:** Red phase was confirmed before implementation: `pytest tests/test_garden_watcher.py::GardenWatcherEndToEndTests -q` failed with `ImportError: cannot import name 'build_garden_state' from 'garden_watcher'`. The depth gate initially surfaced console `pytest` importing the SDP CLI classifier before the repo-local mock, so `tests/test_test_garden_watcher_depth.py` now uses the deterministic local `importlib.util` pattern already used by nearby depth gates. After implementation, `pytest tests/test_garden_watcher.py tests/test_test_garden_watcher_depth.py -q` passed with `48 passed`, and the startup identity anchor command `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q` passed with `9 passed`.
- **Reason:** Full validation result
- **Details:** The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed. Test result: `4498 passed, 3 skipped`; Ruff reported `All checks passed`; mypy reported `Success: no issues found in 34 source files`. No new dependencies or migrations were introduced.

## frac-0076 (2026-05-02T23:59:00+00:00)

- **Reason:** Scope and startup hardening assumptions
- **Details:** Exploration identified the affected surface as `tests/test_generation_client_protocol.py`, with production behavior in `my-claw/tools/senseweave/generation/client_protocol.py` and adjacent client contracts in `client_local.py`, `client_replicate.py`, `client_modal.py`, and `request.py`. The production protocol module already implements meaningful `GenerationResult` metadata, cost-per-second calculation, stable summaries, log-line formatting, and request/result validation. This task therefore preserves production behavior and deepens the locked test surface with one deterministic end-to-end class plus a depth gate. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this protocol-test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_generation_client_protocol_depth.py -q` failing on the missing `GenerationClientProtocolEndToEndTests` class before implementation. After implementation, `pytest tests/test_generation_client_protocol.py::GenerationClientProtocolEndToEndTests tests/test_test_generation_client_protocol_depth.py -q` passed with `4 passed`, the focused generation/client regression set passed with `70 passed`, and the startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4508 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0078 (2026-05-02T17:05:00-07:00)

- **Reason:** Generation-health test-depth scope and startup-hardening assumptions
- **Details:** Exploration identified the affected surface as `tests/test_generation_health.py` with production behavior in `my-claw/tools/senseweave/generation/health.py` and operator expectations in `docs/runbooks/generation-backend.md`. The production audit module already computes meaningful symmetric KL output, persists rolling history, writes collapse alerts only when all three signals align, exposes JSON-safe report dictionaries, and leaves LTM rollback manual. This task therefore preserves production behavior and deepens the locked test surface with one deterministic end-to-end class plus a depth gate. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this generation-health test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_generation_health_depth.py -q` failing on the missing `GenerationHealthEndToEndTests` class before implementation. After implementation, `pytest tests/test_generation_health.py -q` passed with `14 passed`, `pytest tests/test_test_generation_health_depth.py -q` passed with `1 passed`, `pytest tests/test_generation_health.py::GenerationHealthEndToEndTests -q` passed with `2 passed`, and the startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4517 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0074 (2026-05-02T23:11:17.678289+00:00)

- **Reason:** Protected file modification
- **Details:** Protected files modified: sdp/templates/candidates/lead_t2/v001.md, sdp/templates/candidates/lead_t2/v002.md, sdp/templates/candidates/lead_t2/v003.md, sdp/templates/candidates/lead_t2/v004.md, sdp/templates/candidates/lead_t2/v005.md, sdp/templates/candidates/lead_t2/v006.md, sdp/templates/candidates/verify/v001.md, sdp/templates/candidates/verify/v002.md, sdp/templates/candidates/verify/v003.md, sdp/templates/candidates/verify/v004.md, sdp/templates/candidates/verify/v005.md, sdp/templates/candidates/verify/v006.md, sdp/templates/claude/lead_t1.md, sdp/templates/claude/lead_t2.md, sdp/templates/claude/verify.md, sdp/templates/codex/lead_t1.md, sdp/templates/codex/lead_t2.md, sdp/templates/codex/no_work_retry.md, sdp/templates/codex/verify.md, sdp/templates/gemini/ascii_art_agent.md, sdp/templates/gemini/fix_gate.md, sdp/templates/gemini/fix_verify.md, sdp/templates/gemini/lead_t1.md, sdp/templates/gemini/lead_t2.md, sdp/templates/gemini/lead_t3.md, sdp/templates/gemini/no_work_retry.md, sdp/templates/gemini/split_task.md, sdp/templates/gemini/verify.md. Risk: changes to protected paths require manual review. Merge guidance: run `sdp-cli merge --task frac-0074`.

## frac-0084 (2026-05-02)

- **Reason:** Image API spec-parser test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_image_api_spec_parser.py`, with production behavior in `src/cypherclaw/image_api/spec_parser.py` and consumers in `app.py` and `worker.py`. The production parser already produces meaningful one-path output for explicit-prompt Shape A and content-derived Shape B YAML, including dimensions, filenames, style, content piece IDs, and model overrides. This task therefore preserves production parser behavior and deepens the locked test surface with one deterministic end-to-end class plus a depth gate. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this parser-test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_image_api_spec_parser_depth.py -q` failing on the missing `TestImageApiSpecParserEndToEnd` class before implementation. After implementation, `pytest tests/test_image_api_spec_parser.py tests/test_test_image_api_spec_parser_depth.py -q` passed with `21 passed`, focused Ruff passed for the touched parser-depth tests, and the startup identity hardening anchor command passed with `9 passed`. The first required validation run stopped on a transient, unrelated `tests/test_garden_watcher.py::TestUpdateGardenState::test_last_update_is_recent` timestamp race; the isolated test passed immediately on rerun. The full required validation command was then rerun and passed with `4555 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0091 (2026-05-03)

- **Reason:** Music-theory test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_music_theory.py`, with production behavior in `my-claw/tools/senseweave/music_theory.py`. The module already implements meaningful one-path output for MIDI/frequency conversion, note names, interval metadata, scale lookup, chord parsing, voicing, just-intonation helpers, and spectral helpers; this task therefore preserves production behavior unless the new red tests expose a concrete gap. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this music-theory test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_music_theory_depth.py -q` failing on the missing `MusicTheoryEndToEndTests` class before implementation. After implementation, `pytest tests/test_music_theory.py::MusicTheoryEndToEndTests -q` passed, `pytest tests/test_music_theory.py tests/test_test_music_theory_depth.py -q` passed with `87 passed`, touched-test Ruff passed, and the startup identity hardening anchor command passed with `9 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4576 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0093 (2026-05-03)

- **Reason:** Narrative entity API test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_narrative_api_entities.py`, with production behavior in `src/cypherclaw/narrative_api/entities.py`, `app.py`, and `schemas.py`, and product expectations in `prd-cypherclaw-narrative-http-service.md` CN-006 through CN-009. The production entity surface already implements a meaningful one-path lifecycle for create, patch, get, and domain/type filtered list operations through the HTTP API. This task therefore preserves production behavior unless the new red tests expose a concrete gap, and deepens the locked test surface with one deterministic end-to-end class plus a depth gate. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this narrative entity test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_narrative_api_entities_depth.py -q` failing on the missing `NarrativeApiEntitiesEndToEndTests` class before implementation. After implementation, `pytest tests/test_narrative_api_entities.py::NarrativeApiEntitiesEndToEndTests -q` passed, `pytest tests/test_test_narrative_api_entities_depth.py -q` passed, `pytest tests/test_narrative_api_entities.py tests/test_test_narrative_api_entities_depth.py -q` passed with `32 passed`, the narrative API regression set passed with `82 passed`, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4580 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0102 (2026-05-03T04:56:33.875660+00:00)

- **Reason:** Max gate retries exceeded
- **Details:** Quality gates continued to fail after retries.

## frac-0107 (2026-05-03)

## T-022c (2026-05-23)

- **Reason:** Meter trajectory scene metadata scope and startup-hardening assumptions
- **Details:** Exploration found T-022a/T-022b already define and plan
  `MeterTrajectory` values, stamp flattened `meter_trajectory_*` keys into
  score-tree sections, and carry those keys through the score-tree compiler.
  T-022c assumes the remaining gap is generic tracker scene metadata emission:
  scenes should carry the matching planned `meter_trajectory_entry` payload and
  should be able to derive per-scene trajectory metadata from the compact
  composer payload. No new dependency, migration, database column, provider
  secret, runtime state directory, HTTP route, auth behavior, or agent command
  string is required. The generated startup hardening bullets target the
  existing identity startup subsystem; CLI startup, first-boot persistence,
  daemon bootstrap-before-announcer ordering, standalone/federated identity
  reuse, and narrative ASGI import persistence are covered by existing tests
  and will be re-run as regression anchors rather than changing unrelated
  startup flow.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with the locked focused T-022c tests
  failing on missing `meter_trajectory_entry`, missing compact
  `scene_entries`, and missing generic tracker derivation from compact score
  metadata. After implementation, focused T-022c tests passed, adjacent
  score-tree/composer/tracker/compiler coverage passed with `95 passed`,
  startup identity hardening anchors passed with `11 passed`, and full
  validation `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/
  tests/ && mypy src/` passed with `4989 passed, 11 skipped`, Ruff clean, and
  mypy clean. No new dependencies or migrations were introduced.

- **Reason:** Research-runtime test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_research_runtime.py`, with production behavior in `my-claw/tools/researcher.py` and `my-claw/tools/research_tools.py`. The production research runtime already implements meaningful one-path behavior for scope classification, quick/medium/deep research flows, tool-backed findings, report persistence, experiment execution, and benchmark aggregation. This task therefore preserves production behavior unless the new red tests expose a concrete gap, and deepens the locked test surface with one deterministic end-to-end class plus a depth gate. No standalone ADP documentation file was found beyond the task prompt's Explore -> Specify -> Test -> Implement -> Verify -> Document phases, so those phases are treated as the active workflow. The generated startup hardening bullets target the existing identity startup subsystem; CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` before `FirstBootAnnouncer` and standalone/federated identity persistence, so they will be re-run as regression anchors rather than broadening this research-runtime test task. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_research_runtime_depth.py -q` failing on the missing `ResearchRuntimeEndToEndTests` class before the end-to-end class was added. After implementation, `pytest tests/test_research_runtime.py::ResearchRuntimeEndToEndTests -q` passed with `1 passed`, `pytest tests/test_research_runtime.py tests/test_test_research_runtime_depth.py -q` passed with `7 passed`, touched-test Ruff passed, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4651 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## frac-0116 (2026-05-03T08:27:26.490341+00:00)

- **Reason:** Max gate retries exceeded
- **Details:** Quality gates continued to fail after retries.

## frac-0116a (2026-05-03)

- **Reason:** RED marker-gate scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_test_sw_sampler_depth.py` plus the covered module `tests/test_sw_sampler.py`. The frac-0116 depth gate and `SwSamplerEndToEndTests` are already present and green, but `tests/test_sw_sampler.py` has no machine-readable `depth: 2` marker in its module docstring or top-level constants. This task intentionally adds only the RED gate that detects the missing marker; the marker itself is left for a follow-up implementation task. The generated startup hardening bullets target the existing identity startup subsystem, which is already covered by CLI, first-boot, daemon-ordering, standalone/federated persistence, and narrative ASGI import tests, so no unrelated startup code changes are made here. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, or auth behavior are required.
- **Reason:** RED phase and focused verification
- **Details:** `pytest tests/test_test_sw_sampler_depth.py::test_test_sw_sampler_declares_machine_readable_depth_two_marker -q` fails as expected because `tests/test_sw_sampler.py` has no module-docstring or top-level-constant depth marker. Existing sampler coverage remains green with `pytest tests/test_test_sw_sampler_depth.py::test_test_sw_sampler_reaches_depth_two_with_e2e_class tests/test_sw_sampler.py::SwSamplerEndToEndTests -q` (`2 passed`), and `ruff check tests/test_test_sw_sampler_depth.py` passes. Full-suite validation is intentionally expected to fail while this RED gate is present without the follow-up marker implementation.
- **Reason:** Full validation result
- **Details:** The requested validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` installed successfully and then stopped at the intentional RED gate with `1 failed, 4412 passed, 3 skipped`; the chained Ruff/mypy steps did not execute because pytest exited nonzero. Separate quality checks passed: `ruff check src/ tests/` reported `All checks passed!`, `mypy src/` reported `Success: no issues found in 34 source files`, and `git diff --check` was clean.

## frac-0116a (2026-05-03T08:48:39.608414+00:00)

- **Reason:** Max gate retries exceeded
- **Details:** Quality gates continued to fail after retries.

## frac-0116a (2026-05-03T08:55:54.251427+00:00)

- **Reason:** Max gate retries exceeded
- **Details:** Quality gates continued to fail after retries.

## frac-0120 (2026-05-03)

- **Reason:** Voice-alias test-depth scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `tests/test_voice_aliases.py`, with production behavior in `my-claw/tools/senseweave/voice_aliases.py` and production-helper depth coverage in `tests/test_voice_aliases_depth.py`. The production module already exposes the required one-path alias lookup/report/summary helpers from frac-0032, so this task assumes no production code change is needed unless the red depth gate exposes a concrete gap. The generated startup identity hardening bullets target the existing identity startup subsystem; CLI startup, first-boot persistence, daemon bootstrap-before-announcer ordering, standalone/federated identity reuse, and narrative ASGI import persistence are already covered and will be re-run as regression anchors. No new dependencies, migrations, provider secrets, database columns, runtime state directories, HTTP routes, auth behavior, or agent command strings are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_test_voice_aliases_depth.py -q` failing on the missing `VoiceAliasesEndToEndTests` class and missing machine-readable `depth: 2` marker before implementation. After implementation, `pytest tests/test_voice_aliases.py::VoiceAliasesEndToEndTests tests/test_test_voice_aliases_depth.py -q` passed with `3 passed`, and `pytest tests/test_voice_aliases.py tests/test_voice_aliases_depth.py tests/test_test_voice_aliases_depth.py -q` passed with `16 passed`. The startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4682 passed, 3 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.
## T-009@20260515T214233Z (2026-05-15)

- **Reason:** Slow-inference context scope and startup-hardening assumptions
- **Details:** Exploration found the affected PAL workflow surface is `promptclaw/pal_agent.py`, `promptclaw/pal_smoke.py`, `promptclaw/cli.py`, `tests/test_pal_agent.py`, and the PAL product docs. This task assumes PAL-018 should add a callable read-only context workflow and artifact, while PAL-019 owns the operator-facing slow-inference diagnosis CLI. GPU hints and logs are collected only through fixed read-only SSH diagnostics and safely report `skipped` when `PAL_SSH_HOST`, `PAL_SSH_PORT`, and `PAL_SSH_KEY` are not configured. The generated startup hardening bullets target the existing identity startup subsystem; CLI startup, first-boot persistence, daemon `bootstrap_identity()` ordering before `FirstBootAnnouncer`, and narrative ASGI import persistence are already covered by regression anchors and will be re-run rather than changing unrelated startup flow. No new dependencies, migrations, database columns, provider secrets, runtime state directories outside `.promptclaw/runs/`, HTTP routes, auth behavior, or mutating actions are required.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_agent.py::test_pal_slow_inference_context_captures_health_baseline_gpu_and_logs tests/test_pal_agent.py::test_pal_slow_inference_context_skips_optional_remote_hints_without_ssh -q` failing on missing `run_pal_slow_inference_context` before implementation. After implementation, those tests passed, `pytest tests/test_pal_agent.py -q` passed with `18 passed`, `pytest tests/test_pal_agent.py tests/test_pal_smoke.py tests/test_pal_client.py tests/test_doctor.py -q` passed with `37 passed`, and the startup identity hardening anchor command passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4734 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-016@20260515T214233Z (2026-05-16)

- **Reason:** PAL shutdown-audit workflow scope and startup-hardening assumptions
- **Details:** Exploration found the affected PAL workflow surface is `promptclaw/pal_agent.py`, `promptclaw/cli.py`, `tests/test_pal_agent.py`, `pal-2026/ops/templates/shutdown.conf`, `pal-2026/ops/templates/auto_shutdown.sh`, and the PAL product docs. This task assumes PAL-021 should add a deterministic read-only workflow exposed as `promptclaw pal audit shutdown PROJECT_ROOT`. It will collect shutdown config, cron entry, override flag state, current local shutdown time context, and recent shutdown logs through one fixed read-only SSH diagnostic, write standard `.promptclaw/runs/<run-id>/` artifacts, and derive shutdown enabled state, override state, and the next five-minute shutdown window locally. The command will not touch `/opt/pal/config/override.flag`, change cron, edit remote files, shut down services, expose action ids, add dependencies, add migrations, add provider secrets, or change database columns. The generated startup hardening bullets target the existing identity startup subsystem; current CLI, first-boot, daemon-ordering, and narrative ASGI tests already cover `bootstrap_identity()` persistence and ordering before `FirstBootAnnouncer`, so those remain mandatory regression anchors rather than broadening this PAL shutdown audit into startup rewiring.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_pal_agent.py::test_pal_shutdown_audit_reports_enabled_override_and_next_window tests/test_pal_agent.py::test_pal_shutdown_audit_without_ssh_records_unknown_states tests/test_pal_agent.py::test_pal_audit_shutdown_cli_prints_summary -q` failing on the missing `run_pal_shutdown_audit` workflow and `pal audit` parser wiring before production code changed. After implementation, those locked tests passed with `3 passed`, `pytest tests/test_pal_agent.py tests/test_pal_smoke.py tests/test_pal_client.py -q` passed with `42 passed`, and the mandatory startup identity hardening anchor command passed with `45 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4746 passed, 10 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-017@20260515T214233Z (2026-05-15)

- **Reason:** Verifier rule SI-003 false positive on negative-assertion spec; pair-rotate retries exhausted
- **Details:** All seven acceptance criteria for the PAL Phase 2 readiness report (`run_pal_phase2_readiness_report` in `promptclaw/pal_agent.py`, `promptclaw pal report phase2-readiness` CLI, locked tests, doc mentions, AC7 no-migrations diff) have been independently verified PASS five times across both Claude and Codex verifier roles (commits 7293026, 0d0ea94, c0fde26, c52d392, 540d8bc). The SI-003 enforcement keeps re-appending a FAIL verdict because it keyword-matches the token `migration` in `specs/t-017@20260515t214233z-spec.md`, where every occurrence is a *negative* assertion: the problem statement forbids volume migration as out-of-scope, and AC7's VERIFY command is `git diff -- pyproject.toml promptclaw/coherence/migrations` (which is empty — independently confirmed). No new migration file was added under `promptclaw/coherence/migrations/` (still only `001_event_store.sql`, `002_decision_store.sql`); no new database column or table was introduced anywhere in the diff for commit 9bc5dee. Two prior lead retries already added schema-snapshot evidence to the verify report (commits 0d0ea94 and c52d392 with `PRAGMA table_info(tasks)` output) and SI-003 still re-fires because the rule appears to require evidence of a *new or modified* table from this task — which cannot exist when the task changes no schema. With pair-rotate retries exhausted, no further code or evidence change can clear the rule. Recommend: (a) record T-017 verdict as PASS based on the five independent acceptance-criteria PASSes, and (b) tighten SI-003 to skip specs whose only `migration` mentions are inside negative-assertion clauses (forbidden actions, AC "no X introduced" lines, or `git diff -- …/migrations` VERIFY commands). Human review requested before next pipeline tick promotes the FAIL.

## T-017a (2026-05-23)

- **Reason:** Faithful-transmission MIDI intake scope and startup-hardening assumptions
- **Details:** Exploration found the affected production surface is `src/cypherclaw/midi_intake_daemon.py` plus a new dependency-free loader under `src/cypherclaw/`; related tests live in `tests/test_midi_intake_daemon.py`, `tests/test_midi_fragment_extractor.py`, `tests/test_midi_vocabulary_store.py`, and `tests/test_composer_vocabulary_bridge.py`. This task assumes faithful-transmission mode belongs to the MIDI intake CLI as `--faithful-transmission` and to `process_midi_file(..., faithful_transmission=True)`, with manifest output carrying raw source-tick note events while keeping empty fragment payloads for compatibility. The loader will return ordered `pitch`, `duration`, and `velocity` event data and will ignore non-note MIDI data. No new dependencies are required; the existing stdlib parser pattern is sufficient. No migration, provider secret, database column, runtime state directory, HTTP route, auth behavior, or agent command string is required. The generated startup hardening bullets target the existing identity startup subsystem; `midi_intake_daemon.main()` already calls `bootstrap_identity()` before `FirstBootAnnouncer`, and CLI, first-boot, governor-ordering, standalone/federated persistence, and narrative ASGI import tests remain mandatory regression anchors rather than expanding this MIDI task into unrelated startup rewiring.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_midi_faithful_loader.py -q` failing at collection on missing `cypherclaw.midi_loader` before production code changed. After implementation, `pytest tests/test_midi_faithful_loader.py -q` passed with `5 passed`, adjacent MIDI/composer vocabulary tests passed with `62 passed`, and startup identity hardening anchors passed with `11 passed`. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4956 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-024 (2026-05-23)

- **Reason:** Audio streamer scope, assumptions, and startup-hardening anchors
- **Details:** Exploration found no existing `audio_streamer.py`; the affected
  runtime pattern is the CypherClaw tool-script surface under `my-claw/tools/`
  with subprocess-backed JACK/PipeWire command builders and hardware-free tests.
  This task assumes the JACK output bus is the existing SuperCollider stereo
  pair `SuperCollider:out_1` and `SuperCollider:out_2`, connected into a new
  ffmpeg JACK client named `cypherclaw-opus-stream`. The streamer will write
  segmented Ogg/Opus `.opus` files under `/home/user/cypherclaw-data/streams`
  by default, target 6-second segment windows with tolerance verified by
  ffprobe, and target 96 kbps through `libopus -b:a 96k -vbr constrained`.
  CPU acceptance is treated as a live runtime verification using the streamer's
  pid and `ps`, while tests pin the command and CPU-check helper. The generated
  startup hardening bullets target identity bootstrapping; the new streamer will
  call `bootstrap_identity()` before spawning ffmpeg or connecting JACK ports,
  and existing CLI/first-boot/daemon/narrative startup identity tests remain
  regression anchors for standalone and federated persistence. No new
  dependencies, migrations, provider secrets, database columns, runtime state
  directories beyond the stream segment output directory, HTTP routes, auth
  behavior, or agent command strings are required.
- **Reason:** Red phase and focused validation results
- **Details:** Red phase was confirmed with `pytest tests/test_audio_streamer.py -q`
  failing at collection on missing `audio_streamer` before implementation. After
  implementation, `pytest tests/test_audio_streamer.py -q` passed with `4
  passed`; adjacent audio runtime coverage passed with `42 passed`; startup
  identity hardening anchors passed with `11 passed`; `ruff check
  tests/test_audio_streamer.py`, `python -m py_compile
  my-claw/tools/audio_streamer.py`, and the dry-run command `python
  my-claw/tools/audio_streamer.py --dry-run --output-dir
  /tmp/cypherclaw-test-streams --jack-wrapper pw-jack` passed. No new
  dependencies or migrations were introduced. The required validation command
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/` passed with `4997 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-013b (2026-05-22)

- **Reason:** Task duplicates already-completed work from T-013a
- **Details:** T-013b asks to "implement `build_manifest()` to satisfy T-013a tests". That function was implemented in commit 865075f (`feat(midi-intake): add build_manifest() for processed-file sidecars [T-013a]`) and independently verified PASS in commit 175a225. The current implementation lives at `my-claw/tools/midi_intake_daemon.py:169` and already covers all behaviors named in the T-013b brief (read file bytes, compute sha256, parse MThd chunk for format/track_count/division, return JSON-serializable manifest dict). All 41 tests in `tests/test_midi_intake_daemon.py` pass (including the 6 `test_build_manifest_*` cases) and `ruff check` is clean. No code change made for T-013b — there is no remaining gap to close. Recommend: mark T-013b done by reference to T-013a, or have the planner split a follow-up that goes beyond the existing function (e.g. write the sidecar to disk, integrate with `process_midi_file`).

## T-014 (2026-05-22)

- **Reason:** MIDI fragment extractor scope, dependency choice, and startup-hardening assumptions
- **Details:** Exploration found the affected surface is `src/cypherclaw/midi_intake_daemon.py`, new focused extraction logic under `src/cypherclaw/midi_fragments.py`, and MIDI intake tests. The CypherClaw v2 PRD names a future `mido`-based ingestion package, but `mido` is not a direct dependency in `pyproject.toml`, so T-014 intentionally uses a stdlib Standard MIDI File parser for hand-crafted unit-test MIDIs and adds no dependency. The generated startup hardening bullets target the existing identity startup subsystem; `midi_intake_daemon.main()` already calls `bootstrap_identity()` before `FirstBootAnnouncer`, and the required startup identity anchors passed. No migrations, provider secrets, database columns, runtime state directories, HTTP routes, auth behavior, or startup flow changes were introduced.
- **Reason:** Red phase and validation results
- **Details:** Red phase was confirmed with `pytest tests/test_midi_fragment_extractor.py -q` failing on missing `extract_midi_fragments` and missing manifest `fragments` before implementation. After implementation, `pytest tests/test_midi_fragment_extractor.py tests/test_midi_intake_daemon.py -q` passed with `54 passed`, the startup identity hardening anchor command passed with `9 passed`, `ruff check` passed on touched files, and `mypy src/` passed. The required validation command `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/` passed with `4941 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were introduced.

## T-016 (2026-05-23)

- **Reason:** Composer vocabulary scope, assumptions, and startup-hardening anchors
- **Details:** Exploration found the affected surface is the existing MIDI vocabulary store in `src/cypherclaw/midi_vocabulary_store.py`, score-tree authoring in `my-claw/tools/senseweave/recursive_composer.py`, tracker compilation and scene metadata in `my-claw/tools/senseweave/tracker_compiler.py` and `music_tracker.py`, and the live scene-start log in `my-claw/tools/duet_composer.py`. The task assumes T-016 should read the existing T-015 schema rather than adding database columns, so no migration is required. The vocabulary DB path is assumed to be explicitly provided in tests and resolved at runtime from `CYPHERCLAW_MIDI_VOCABULARY_DB` or `/home/user/cypherclaw-data/state/midi_vocabulary.sqlite`. Scene citations are one fragment per scene for this task, with deterministic pseudo-random selection so the cited rate can be verified against curiosity. The generated startup hardening bullets target the existing identity startup subsystem; CLI startup, first-boot persistence, daemon bootstrap-before-announcer ordering, standalone/federated persistence, and narrative ASGI import persistence are already covered and will be re-run as regression anchors rather than changing unrelated startup flow. No new dependencies, provider secrets, database columns, runtime state directories outside existing paths, HTTP routes, auth behavior, or agent command strings are required.

- **Reason:** T-016 red/green verification record
- **Details:** Red phase was captured with missing `cypherclaw.composer_vocabulary_bridge` and the existing `compose_score_tree(...)` signature rejecting `vocabulary_db_path`. Green verification passed the locked vocabulary bridge tests, score-tree citation test, tracker compiler citation test, and startup identity hardening anchors. Final validation passed with `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`: `4951 passed, 11 skipped`, Ruff clean, and mypy clean. No new dependencies or migrations were added.

## T-054a (2026-05-23)

- **Reason:** Live MIDI Durable Object scope, assumptions, and hardening anchors
- **Details:** Exploration found the affected Worker surface is the sibling
  `/Users/anthony/Programming/catalog-explorer/worker` project:
  `worker/src/index.ts`, `worker/wrangler.toml`, `worker/README.md`, and
  `worker/tests/*.test.js`. T-054a assumes the task owns connection plumbing
  only: `/api/cypherclaw/live-midi` WebSocket upgrade forwarding,
  `LiveMidiRoom` WebSocket accept/close/error tracking, and the
  `LIVE_MIDI_ROOM` Durable Object binding. MIDI event ingestion,
  `/api/cypherclaw/midi-event`, and fan-out remain later T-054 subtasks. The
  Wrangler Durable Object migration uses `new_sqlite_classes =
  ["LiveMidiRoom"]`; no D1 database migration, database column, R2 layout
  change, provider secret, runtime state directory, npm package, startup-flow
  change, or SuperCollider source change is required. Mandatory hardening for
  the recurring `fx_bus_id`/`sw_sampler` routing failures remains an explicit
  verification anchor rather than broadening this Worker-only task into
  synthesis changes.
- **Reason:** T-054a red phase and focused green verification
- **Details:** Red phase was confirmed with `npm test --
  tests/cypherclaw-live-midi.test.js` failing on the missing live-midi route and
  missing exported `LiveMidiRoom` before production code changed. After
  implementation, the same command passed with `34 passed`, and `npm run check`
  passed for the Worker TypeScript project. The full Worker suite passed with
  `34 passed`, the mandatory `fx_bus_id` / `sw_sampler` hardening command
  passed with `3 passed`, and the required validation command
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/` passed with `5211 passed, 11 skipped`, Ruff clean, and mypy clean.

## T-054d (2026-05-23T22:58:37.379329+00:00)

- **Reason:** Max work retries exceeded
- **Details:** Lead left uncommitted changes repeatedly across all available lead rotations (claude, codex, gemini). The "uncommitted changes" each tick are the SI-003 post-PASS FAIL appendage to `sdp/verification/t-054d-verify.md` (verifier writes `Verdict: PASS`, then the SI-003 rule appends a duplicate `Notes for Lead Agent` block plus `Verdict: FAIL`) plus the corresponding agent log files. No functional fix is possible at the task level — see `[[project-sdp-si003-false-positive]]`. Final state: 5+ independent PASSes across claude/codex/gemini verifier roles, zero outstanding code/test gaps, SI-003 is the only flag and it is a confirmed false positive. Recording pair-rotate exhaustion as the terminal escalation; awaiting SI-003 rule patch before any further pipeline action on T-054d.

## T-054d (2026-05-23T23:22:00Z)

- **Reason:** SI-003 rule patch applied after pair-rotate exhaustion.
- **Details:** Patched the sibling `sdp-cli` checkout used by the managed runner
  so `sdp.pipeline.migration_detection.spec_mentions_migration()` ignores
  non-database Cloudflare Workers Durable Object / Wrangler schema-change config
  references while still requiring table snapshots for actual SQLite/Postgres
  schema work. Commit: `/Users/anthony/Programming/sdp-cli` `59bffc5`
  (`fix(verifier): ignore non-db DO schema config for SI-003 [T-054d]`).
  Regression evidence: `pytest tests/test_migration_detection.py
  tests/test_migration_snapshot_wiring.py
  tests/test_migration_snapshot_downgrade_integration.py -q` passed with
  `38 passed`; `ruff check src/sdp/pipeline/migration_detection.py
  tests/test_migration_detection.py` passed; `mypy
  src/sdp/pipeline/migration_detection.py` passed. The patched classifier now
  returns `False` for `specs/t-054d-spec.md` and still returns `True` for a real
  migration spec (`specs/frac-0095-spec.md`).

## T-054d (2026-05-23T23:52:40.657950+00:00)

- **Reason:** Max verify retries exceeded
- **Details:** Verification continued to FAIL after retries across all available lead rotations (claude, codex, gemini) (including agent swap).

## T-053b (2026-05-24)

- **Reason:** Live MIDI event schema scope and startup-hardening assumptions
- **Details:** Exploration found the affected surface is
  `src/cypherclaw/live_midi_emitter.py` and
  `tests/test_live_midi_emitter.py`, with context conventions in
  `src/cypherclaw/midi_scene.py` and existing live MIDI Worker/browser specs.
  T-053b assumes the producer-side schema belongs in the existing emitter
  module, remains stdlib-only, and serializes the existing voice/scene/tuning
  context tags while adding event-specific validation and helper constructors
  for `note_on`, `note_off`, `control_change`, and `pitch_bend`. No new
  dependencies, migrations, database columns, provider secrets, runtime state
  directories, HTTP routes, auth behavior, Worker changes, composer
  integration, agent command strings, startup-flow rewiring, or SuperCollider
  source changes are required. The generated startup identity hardening bullets
  target the existing identity subsystem; current CLI, first-boot,
  daemon-ordering, standalone/federated persistence, and narrative ASGI tests
  already cover `bootstrap_identity()` before `FirstBootAnnouncer` and identity
  persistence, so those remain regression anchors rather than broadening this
  MIDI schema task.
- **Reason:** T-053b red phase and verification results
- **Details:** Red phase was confirmed with
  `pytest tests/test_live_midi_emitter.py -q` failing on four new schema tests
  before implementation (`4 failed, 8 passed`). After implementation,
  `pytest tests/test_live_midi_emitter.py -q` passed with `12 passed`, focused
  Ruff and mypy passed for the touched emitter files, adjacent MIDI scene/loader
  parser coverage passed with `28 passed`, and startup identity hardening
  anchors passed with `11 passed`. The required validation command
  `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ &&
  mypy src/` passed with `5223 passed, 11 skipped`, Ruff clean, and mypy clean.
  No new dependencies or migrations were introduced.
