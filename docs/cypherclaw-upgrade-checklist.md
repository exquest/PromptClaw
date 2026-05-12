# CypherClaw Upgrade Checklist

## Purpose

This is the execution checklist for the current CypherClaw upgrade program:

- stabilize and improve the music organism
- make cadence and presence authoritative
- unify music, face, gallery, and personality
- reduce CPU pressure so audio remains clean

It is downstream of [cypherclaw-presence-cadence-spec.md](/Users/anthony/Programming/PromptClaw/docs/cypherclaw-presence-cadence-spec.md:1). The spec defines behavior. This checklist defines build order, files, tests, and live rollout gates.

The next compositional layer is defined in
[cypherclaw-musicianship-roadmap.md](/Users/anthony/Programming/PromptClaw/docs/cypherclaw-musicianship-roadmap.md:1).
That roadmap translates the Berklee songwriting curriculum into concrete
CypherClaw subsystems and should be treated as the musicianship program that
follows the current stability/cadence work.
The concrete build target for longer, more varied, recursively composed pieces
now lives in
[cypherclaw-score-tree-composition-spec.md](/Users/anthony/Programming/PromptClaw/docs/cypherclaw-score-tree-composition-spec.md:1),
which defines the new piece commission, narrative brief, score-tree composer,
composition gate, tracker compiler, and repertoire score-tree memory layers.
The production and sound-design complement now lives in
[cypherclaw-emsd-roadmap.md](/Users/anthony/Programming/PromptClaw/docs/cypherclaw-emsd-roadmap.md:1),
which translates the electronic music production curriculum into concrete
course scaffolds, runtime modules, and verification work for CypherClaw's
next sound-design and DSP phase.

## Status Legend

- `done`: implemented locally and deployed on CypherClaw
- `partial`: implemented in part, but not yet complete enough to close
- `todo`: not implemented yet

## Current State

### `done`

- Canonical `presence_engine.py` writes `/tmp/presence_state.json`
- Canonical `cadence_engine.py` writes `/tmp/cadence_state.json`
- `world_model.py` prefers canonical presence and cadence state
- tracker cadence planning can trust canonical cadence
- tracker solo clamps tempo into the cadence band
- live boot path starts `presence_engine.py` and `cadence_engine.py`

### `partial`

- presence quality: the engine exists, but the live sensor inputs are still thin and conservative
- cadence quality: the engine exists, but the music is not yet fully using silence budgets, articulation targets, or loudness envelopes
- weekly modulation: core logic exists in cadence, but it is not yet fully lived through face/gallery/performance behavior
- harmonic variation and key management: tracker solo is still too major-root-oriented, stale key suggestion files can pin the music, and the keyboard grimoire is not yet wired into live harmony control

### `todo`

- silence-aware tracker scheduling
- face/gallery unification around canonical state
- attention/performance overlay across all modalities
- household/guest relationship memory
- CPU reduction pass on visual and monitoring processes
- long soak tuning against real household behavior

## Phase 0: Baseline And Budget

Status: `partial`

Goal:
- keep the audio box stable while new behavior lands

Files:
- `my-claw/tools/server_health.py`
- `my-claw/tools/self_listener.py`
- `my-claw/scripts/cypherclaw_boot.sh`

Tasks:
- record current CPU usage for `face_display.py`, `gallery_x11.py`, `self_listener.py`, `scsynth`, `presence_engine.py`, and `cadence_engine.py`
- record PipeWire health and verify no new `resync` or xrun-like events
- define acceptable CPU budgets:
  - `presence_engine.py < 1%`
  - `cadence_engine.py < 0.5%`
  - new tracker/cadence logic adds no measurable scsynth instability

Tests and checks:
- manual `top` or `ps` sampling on CypherClaw
- `journalctl --user -u pipewire --since "10 minutes ago"`

Exit criteria:
- audio remains clean while the new daemons are running
- no new PipeWire errors attributable to the cadence work

## Phase 1: Presence Quality

Status: `partial`

Goal:
- improve `presence_state.json` so CypherClaw can distinguish `occupied`, `asleep`, and `away` more credibly

Files:
- `my-claw/tools/senseweave/presence_engine.py`
- `my-claw/tools/room_listener.py`
- `my-claw/tools/senseweave/sensor_fusion.py`
- `my-claw/tools/observer_vision.py`
- `my-claw/tools/inner_life/world_model.py`
- `my-claw/scripts/cypherclaw_boot.sh`

Tasks:
- feed `room_listener.py` into presence resolution instead of relying mainly on room motion and inactivity
- add explicit freshness handling for room camera, observer, speech, and instrument inputs
- improve `observer_vision.py` so room brightness alone does not imply presence
- add direct face/Telegram interaction hooks into presence
- tune `likely_asleep` so late-night quiet home occupancy wins over accidental `away`

Tests:
- `tests/test_presence_engine.py`
- `tests/test_sensor_fusion.py`
- add `tests/test_world_model.py` or continue extending `tests/test_inner_life.py`

Exit criteria:
- late-night occupied homes no longer collapse into `likely_away` by default
- first interaction in the morning flips reliably into `wake_ramp`
- stale sensor files degrade gracefully instead of creating false occupancy

## Phase 2: Cadence Engine Completion

Status: `partial`

Goal:
- make cadence the full artistic control plane, not just a tempo clamp

Files:
- `my-claw/tools/senseweave/cadence_engine.py`
- `my-claw/tools/inner_life/world_model.py`
- `docs/cypherclaw-presence-cadence-spec.md`

Tasks:
- finish mapping loudness, onset density, articulation, pulse clarity, harmonic rate, phrase arcs, and silence budgets into stable runtime outputs
- add explicit override-state reading if face/Telegram begins writing cadence overrides
- tune day-phase and weekly-phase values from live experience
- expose enough metadata for face/gallery logic to respond coherently

Tests:
- `tests/test_cadence_engine.py`

Exit criteria:
- cadence output is stable and believable across the day
- Monday, Friday, weekend, and Sunday behavior differ in the intended ways
- cadence fields are rich enough that downstream systems no longer need ad hoc time-of-day guesses

## Phase 3: Composer And Tracker Completion

Status: `partial`

Goal:
- make the music engine actually sound like it is obeying cadence, not just wearing a cadence label

Files:
- `my-claw/tools/duet_composer.py`
- `my-claw/tools/senseweave/tracker_cadence.py`
- `my-claw/tools/senseweave/music_tracker.py`
- `my-claw/tools/senseweave/music_tracker_runtime.py`
- `my-claw/tools/senseweave/generative_scores.py`
- `my-claw/tools/midi_keyboard_listener.py`
- `my-claw/tools/senseweave/pedals_to_key.py`

Tasks:
- replace remaining mood-only heuristics with cadence-driven control where appropriate
- make tracker family selection trust `day_phase`, `weekly_phase`, and `attention_state`
- thread cadence loudness, density, and articulation into actual score and scheduling behavior
- ensure `away_practice` and `sleep` sound materially different in density and attack profile, not just tempo
- stop stale context files from pinning harmony:
  - add freshness checks to `garden_state` and any other key suggestion source
  - do not let stale `music_key` collapse the whole system to `C`
- preserve harmonic quality instead of flattening everything to a root note:
  - keep major / minor / mode family information through tracker planning
  - stop overwriting mood-selected minor keys with bare major roots
- add a Keyboard Grimoire harmonic planner:
  - tonic
  - mode family
  - chord palette
  - voicing profile
  - modulation intent
- seed the harmonic planner from the grimoire families visible in the source book:
  - major / melodic minor / harmonic minor
  - pentatonic and blues variants
  - whole tone / augmented / diminished / eight-tone color systems
  - bebop families
  - extended / altered / polychord chord palettes
- wire live keyboard influence beyond nearest-major-key snapping:
  - keyboard note-sets suggest tonic and mode
  - pedal gestures suggest pedal point, harmonic tension, or modulation
  - write a canonical `/tmp/keyboard_grimoire_state.json`
- add scene-level modulation so `Development` and `Recap` can pivot or borrow color instead of staying in one static song key

Tests:
- `tests/test_tracker_cadence.py`
- `tests/test_music_tracker.py`
- `tests/test_music_tracker_runtime.py`
- add `tests/test_duet_composer_cadence.py`
- add `tests/test_observer_vision_runtime.py`
- add `tests/test_midi_keyboard_listener_runtime.py`
- add `tests/test_pedals_to_key.py`
- add `tests/test_duet_composer_harmony.py`

Exit criteria:
- pre-sleep and late-night music stays restrained even when the fallback mood is lively
- away-practice sounds stranger and more exploratory than occupied listening
- tracker output respects cadence tempo bounds in all scenes
- live solo mode is no longer pinned to one major key for many songs in a row
- keyboard and pedal gestures can steer harmony in a musically legible way

Musicianship follow-on:
- once Phase 3 is stable enough, start `Phase M1` and `Phase M2` from
  `cypherclaw-musicianship-roadmap.md`
- those phases should become the default next music-depth work after the
  remaining audio-risk regressions are under control
- once the existing tracker/harmony work is stable enough, use
  `cypherclaw-score-tree-composition-spec.md` as the canonical build order for
  replacing the current tracker-first song-construction path

## Phase 4: Silence-Aware Scheduling

Status: `todo`

Goal:
- make silence an actual compositional mechanism

Files:
- `my-claw/tools/senseweave/music_tracker_runtime.py`
- `my-claw/tools/senseweave/music_tracker.py`
- `my-claw/tools/duet_composer.py`

Tasks:
- add silence-budget consumption per hour
- schedule both micro-gaps and macro-gaps
- let sleep and wind-down drift toward near-silence
- let performance or direct interaction temporarily suspend silence budgets

Tests:
- add `tests/test_music_tracker_runtime_silence.py`
- extend `tests/test_cadence_engine.py`

Exit criteria:
- overnight music audibly breathes and fades instead of running as a constant bed
- daytime occupied mode includes pauses that make the room feel livable

## Phase 5: Face / Gallery / Personality Unification

Status: `todo`

Goal:
- make the visible and social organism read the same state as the music organism

Files:
- `my-claw/tools/face_display.py`
- `my-claw/tools/gallery/gallery_display.py`
- `my-claw/tools/gallery/gallery_x11.py`
- `my-claw/tools/tamagotchi.py`
- `my-claw/tools/telegram.py`
- `src/cypherclaw/daemon.py`

Tasks:
- make face and gallery consume `/tmp/presence_state.json`, `/tmp/cadence_state.json`, and `/tmp/active_characters.json`
- unify daemon state paths so the live face is not reading stale state
- add canonical face intentions like `calmer`, `livelier`, `stay awake`, `practice`, `perform`
- ensure Telegram remains the steward/operator override surface

Tests:
- extend `tests/test_telegram_runtime.py`
- extend `tests/test_tamagotchi_runtime.py`
- extend `tests/test_gallery.py`

Exit criteria:
- face, gallery, and music agree about occupancy and cadence
- in-room interaction changes all three layers coherently

## Phase 6: Attention, Performance, And Identity

Status: `todo`

Goal:
- make CypherClaw become clearer and more intentional when attended to, and warmer or more legible around guests

Files:
- `my-claw/tools/senseweave/presence_engine.py`
- `my-claw/tools/senseweave/cadence_engine.py`
- `my-claw/tools/duet_composer.py`
- `my-claw/tools/face_display.py`
- `my-claw/tools/gallery/gallery_x11.py`

Tasks:
- add stronger attention scoring from direct interaction, instrument activity, and face/gallery zone presence
- add `attending` and `performance` overlays
- add household-member enrollment and soft guest inference
- bias motif recall and friendliness by identity confidence

Tests:
- add `tests/test_override_engine.py`
- add `tests/test_presence_attention.py`
- extend `tests/test_inner_life.py`

Exit criteria:
- passive pass-through traffic does not trigger performance mode
- real attention or direct interaction does
- guest mode feels more welcoming without flattening CypherClaw’s identity

## Phase 7: Weekly Memory And Practice Promotion

Status: `todo`

Goal:
- let the piece develop habits and relationships over days, not just songs

Files:
- `my-claw/tools/duet_composer.py`
- `my-claw/tools/senseweave/music_tracker.py`
- `my-claw/tools/senseweave/tracker_cadence.py`
- `my-claw/tools/inner_life/` modules related to memory and practice

Tasks:
- store away-practice discoveries that recur and survive filtering
- promote surviving motifs into occupied listening
- add cross-day relationship warmth that cools off over time

Tests:
- add `tests/test_tracker_memory.py`
- extend `tests/test_music_tracker.py`

Exit criteria:
- away mode produces future public material in a subtle, traceable way
- recurring people cause subtle motif or mood recall across days

## Phase 8: CPU Reduction

Status: `todo`

Goal:
- free headroom for audio and sensing

Files:
- `my-claw/tools/face_display.py`
- `my-claw/tools/gallery/gallery_x11.py`
- `my-claw/tools/self_listener.py`
- `my-claw/scripts/cypherclaw_boot.sh`

Tasks:
- reduce display redraw rates or expensive loops
- reduce self-listener cadence or move expensive analysis off the hot loop
- stop stale or duplicate daemons from accumulating
- audit camera polling intervals

Tests and checks:
- runtime process sampling on CypherClaw
- verify no increase in click detector events after reductions

Exit criteria:
- display and monitoring processes no longer dominate CPU relative to scsynth
- audio remains clean under normal live operation

## Phase 9: Soak, Tune, And Ratify

Status: `todo`

Goal:
- make the whole organism believable in the actual house

Files:
- no single file; this is tuning across the system

Tasks:
- run overnight, workday, evening, and weekend soaks
- compare inferred occupancy to real household activity
- tune away timeout, asleep thresholds, wake ramp, and silence ratios
- verify that people can converse comfortably over the installation

Tests and checks:
- live logs on CypherClaw
- `/tmp/presence_state.json`
- `/tmp/cadence_state.json`
- `/tmp/duet_composer.log`
- PipeWire journal

Exit criteria:
- the daily cadence feels believable and livable
- no recurring clicks are introduced by the new control logic
- CypherClaw feels like one organism across sound, visuals, and interaction

## Deployment Order

Use this live rollout order for each major phase:

1. Write or extend tests locally.
2. Implement locally.
3. Run only the targeted and related suites.
4. Run `py_compile` on the changed runtime files.
5. If shell scripts changed, run `bash -n`.
6. Back up the live files on CypherClaw.
7. Deploy only the changed files.
8. Restart only the minimal live processes needed.
9. Check:
   - process list
   - authority state files
   - `duet_composer.log`
   - PipeWire journal
10. Soak before moving to the next phase.

## SenseWeave SDP Rollout Controls

The operator `/status` surface now includes a SenseWeave diagnostic block built
from the live authority files. It identifies the active score tree, current
section function, arrangement curve, ear metrics, sample source, master bus, and
self-listener state before an operator has to SSH into the host.

Safe rollout order:

1. Leave defaults enabled in staging and confirm `/status` shows the diagnostic
   block with real `/tmp` state.
2. Roll out diagnostics first: `my-claw/tools/senseweave/operator_diagnostics.py`,
   `my-claw/tools/cypherclaw_daemon.py`, `my-claw/tools/daemon.py`, and
   `my-claw/tools/glyphweave/scenes.py`.
3. Roll out behavior flags second:
   `my-claw/tools/senseweave/rollout_controls.py`,
   `my-claw/tools/senseweave/practice_curriculum.py`,
   `my-claw/tools/senseweave/self_critique.py`, and
   `my-claw/tools/senseweave/piece_commission.py`.
4. Toggle one flag at a time only after `/status` is healthy:
   `CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE`,
   `CYPHERCLAW_ENABLE_PREVIEW_RENDER`,
   `CYPHERCLAW_ENABLE_SELF_CRITIQUE`, and
   `CYPHERCLAW_ENABLE_LONG_FORM_SUITE`.
5. Restart only the affected process: the Telegram daemon for status-only
   changes, and `duet_composer.py` for composition-behavior flag changes.
6. Soak one song cycle after each toggle and confirm `/tmp/composer_state.json`,
   `/tmp/tracker_runtime_state.json`, `/tmp/sample_dsp_activity.json`,
   `/tmp/sample_playback_state.json`, `/tmp/master_bus_state.json`, and
   `/tmp/self_listen.json` are still updating.

Rollback files:

- `my-claw/tools/senseweave/operator_diagnostics.py`
- `my-claw/tools/senseweave/rollout_controls.py`
- `my-claw/tools/senseweave/practice_curriculum.py`
- `my-claw/tools/senseweave/self_critique.py`
- `my-claw/tools/senseweave/piece_commission.py`
- `my-claw/tools/cypherclaw_daemon.py`
- `my-claw/tools/daemon.py`
- `my-claw/tools/glyphweave/scenes.py`

Fast rollback is env-only when code is healthy: set the specific
`CYPHERCLAW_ENABLE_*` variable to `0`, restart `duet_composer.py` for behavior
flags or the daemon for status rendering, and verify `/status` shows the flag
as `off`. File rollback is only needed if the new diagnostics code itself is
faulting.

## Recommended Next Three Tasks

1. Improve live `presence_engine.py` inputs so quiet-at-home late nights resolve to `likely_asleep` more often than `likely_away`.
2. Add silence-aware scheduling to the tracker runtime so cadence silence budgets become audible behavior.
3. Make face and gallery read canonical presence and cadence state, not stale daemon-local files.
