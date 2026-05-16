# Handoff Protocol

PromptClaw v2.1 uses **artifact handoffs** rather than agent-to-agent chat.

## Rule

One agent never directly passes work to another. The orchestrator does.

## Mechanism

For each step, the orchestrator writes:

- the task input
- the route decision
- the handoff brief
- the prompt given to the next agent
- the output returned by that agent
- optional verification output
- the final summary

For live `command` agents, the orchestrator invokes the local CLI from the project root and passes an absolute `{prompt_file}` path for the prompt artifact it just wrote.

The same model objects that move through routing, lead, verify, and finalization
can now be summarized through `promptclaw.models` helpers. Those summaries are
diagnostic only; handoff authority remains the files under
`.promptclaw/runs/<run-id>/`.

In CypherClaw live operations, those handoffs only begin after the bootstrap and preflight gates pass. The runner launcher refuses to start if maintenance mode is active, if the workdir layout is incomplete, or if the authoritative SQLite files fail integrity checks.

Operational notification helpers are also test-aware. Runtime scripts that shell out to `my-claw/tools/telegram.py` will suppress sends automatically during `pytest`, explicit `PROMPTCLAW_TEST_MODE` runs, and copied tmpfs task-run workdirs unless `PROMPTCLAW_ALLOW_LIVE_TELEGRAM=1` is set, so verification work can exercise reboot and recovery flows without messaging the live bot.

Before that preflight runs, the launcher now removes a stale `.sdp/run.lock` when it points at a dead PID. That makes routine systemd restarts self-healing instead of leaving the queue runner in a restart loop.

The maintenance gate is authoritative on disk: `.sdp/MAINTENANCE` under the resolved authority `.sdp` directory. Entering maintenance while the runner is active now requires an explicit operator override, so an in-flight task cannot silently pause its own queue just by invoking `maintenance_mode.py enter`.

The operator-facing health check now follows the same split: `promptclaw doctor` validates PromptClaw config for every project and automatically adds runtime preflight when the project root includes live CypherClaw runtime markers.

## Files

```text
.promptclaw/runs/<run-id>/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── prompts/lead-<agent>.md
├── outputs/lead-<agent>.md
├── handoffs/lead-to-verify.md
├── prompts/verify-<agent>.md
├── outputs/verify-<agent>.md
├── summary/final-summary.md
└── logs/events.jsonl
```

PAL agent workflows use the same transport. For `promptclaw pal agent triage`,
the run records:

```text
.promptclaw/runs/<run-id>/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── prompts/triage-plan.md
├── outputs/triage-plan.raw.txt
├── outputs/triage-plan.json
├── outputs/tool-observations.json
├── prompts/triage-summary.md
├── handoffs/pal-to-operator.md
├── summary/final-summary.md
├── logs/events.jsonl
└── state.json
```

In this PAL path, the model-authored plan is advisory. PromptClaw executes only
the local allow-list and records any unknown or destructive requested tools as
ignored. Infrastructure changes remain operator approvals, not implicit
handoffs. The `triage-plan.md` and `triage-summary.md` prompt artifacts include
a bounded `Knowledge Context` section sourced from the local PAL KB index when
available, or a bounded unavailable-context note when the index has not been
built.

For `promptclaw pal agent actions`, the action layer records the approval gate
explicitly:

```text
.promptclaw/runs/<run-id>/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── prompts/action-plan.md
├── outputs/action-context.json
├── outputs/action-plan.raw.txt
├── outputs/action-plan.json
├── outputs/action-results.json
├── prompts/action-summary.md
├── handoffs/pal-action-request.md
├── summary/final-summary.md
├── logs/events.jsonl
└── state.json
```

`action-results.json` is the authority for what happened: proposed action ids,
approved action ids, ignored approvals, executed action results, and pending
approvals. A proposed action with no matching `--approve ACTION_ID` remains
`pending_approval`. The `action-plan.md` and `action-summary.md` prompt
artifacts carry the same bounded `Knowledge Context` section as triage prompts,
without expanding the action allow-list.

Action planning also records provider boundaries that are intentionally not
handoff authority. The Vast connector is a non-executing stub: `rent`,
`destroy`, `start`, and `stop` are blocked lifecycle metadata with no default
callable action ids, so PAL proposals for those operations stay in
`ignored_actions` unless future work explicitly adds a tested action.

The slow-inference context workflow uses the same artifact transport, but it is
read-only context collection rather than a PAL-authored plan. It records:

```text
.promptclaw/runs/<run-id>/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── outputs/slow-inference-context.json
├── handoffs/slow-inference-context.md
├── summary/final-summary.md
├── logs/events.jsonl
└── state.json
```

`slow-inference-context.json` captures router health, smoke baseline token/s,
GPU hints, and PAL router/Ollama logs when available. The GPU and log tools are
fixed read-only SSH diagnostics; if SSH is not configured they record `skipped`
observations instead of failing or prompting for credentials.

The slow-inference diagnosis CLI uses the same artifact transport:

```text
.promptclaw/runs/<run-id>/
├── input/task.md
├── routing/route.json
├── routing/route.md
├── outputs/slow-inference-diagnosis.json
├── handoffs/slow-inference-diagnosis.md
├── summary/final-summary.md
├── logs/events.jsonl
└── state.json
```

`promptclaw pal diagnose slow-inference PROJECT_ROOT` reuses fixed read-only
health, baseline, GPU, and log diagnostics, then derives local findings for
baseline token/s, live log token/s, router health, and GPU utilization. The
diagnosis payload and route metadata both record `mutating_actions: []`; the
command writes only local PromptClaw run artifacts and does not approve or
execute infrastructure changes.

## Benefits

- deterministic transfer point
- reproducible history
- resumable runs
- better debugging
- compatible with mixed local tools

## Startup handoff

Before runtime handoffs begin, the startup wizard can generate the initial routing documents and agent lanes. That gives the orchestrator a cleaner starting point than raw placeholder prompts.

## Clarification flow

If the route decision marks the task as ambiguous, the orchestrator writes:

```text
summary/clarification-request.md
```

Then run status becomes `awaiting_user`.

To continue:

```bash
promptclaw resume . --run-id <run-id> --answer "your answer"
```

## Verification contract

Verification prompts instruct the chosen verifier to emit:

```text
VERDICT: PASS
```

or

```text
VERDICT: PASS_WITH_NOTES
```

or

```text
VERDICT: FAIL
```

PromptClaw parses that marker and decides whether to complete, retry, or fail.

When SDP verification runs in a dirty repository, the verifier must distinguish
task-scoped dirt from pre-existing unrelated workspace state. Uncommitted changes
introduced by the lead remain blocking, but unrelated baseline files are recorded
as notes so the retry loop does not ask an agent to clean or revert another
operator's work.

## Retry policy

By default:

- one lead pass
- one verifier pass
- one retry after fail

You can change this in `promptclaw.json`.

For CypherClaw live command runs, provider availability can also change the handoff path. When quota telemetry marks a provider as degraded or paused, the orchestrator can swap to another provider for lead/verify work, and in single-agent degraded mode it can temporarily assign the same available agent to both roles until headroom recovers.

When the daemon is started with `LOCAL_ONLY=true`, that runtime override takes precedence over normal provider rotation. Lead, verify, router-fallback, and explicit agent-step handoffs are all forced onto `ollama`, and the daemon does not invoke the cloud router CLIs while that mode is active.

The runtime transport itself is also guarded now:

- `my-claw/tools/init_workdir.sh` prepares the tmpfs workdir and symlinks authority DBs back to disk.
- `my-claw/tools/sdp_runner_launcher.sh` runs preflight before `sdp-cli run`.
- `my-claw/tools/sdp_runner_launcher.sh` also auto-exports a sibling `sdp-cli/src` checkout into `PYTHONPATH` when present, unless the operator already set `PYTHONPATH`.
- `my-claw/tools/safe_reboot.sh prepare` checkpoints and enters maintenance mode before shutdown.
- `my-claw/tools/safe_reboot.sh resume` validates the latest checkpoint before reopening the runner.
- `my-claw/systemd/cypherclaw-sdp-runner.service` uses `Restart=always` so clean queue-run exits restart automatically; maintenance-gated launcher exits use code `75`, which is marked successful and excluded from restart.

For live CypherClaw daemon executions, the transport also records concurrency semaphore transitions (`acquired`, `released`, `rejected`) to Observatory and keeps daemon status probes platform-aware so the same code path can run on macOS launchd and Linux systemd hosts without crashing.
The daemon also strips systemd watchdog variables from child-process environments before invoking agents or helper CLIs, so only the daemon main process can send watchdog notifications.

Operator roadmap/status queries should prefer queue-backed built-ins over routed summaries when possible. In the live daemon, `/monitor`, `/prd`, and `/tasks` are expected to read the authority queue DB directly, so queue progress, implementation order, and actionable task lists are based on the same dependency graph the runner uses. Progress totals should use the live executable-task count and exclude only split parents. `needs_split` should remain a first-class queue bucket instead of being folded into `pending`, any active-run drift between `tasks` and `task_runs` should be surfaced explicitly to the operator, and `/prd` should call out frozen-only or decomposed-only roadmap stages instead of collapsing them into a generic `not loaded` label. `/monitor` should include the compact high-signal status lines operators actually use from `sdp-cli status`: completion gate, recent completed run, and live provider/quota state. `/tasks` should default to the next actionable queue slices rather than a raw task dump, with filtered views available for frozen, attention, blocked, and all-task inspection. Stage-targeted forms like `/tasks prd <n>` and `/tasks stage <name>` should resolve through the same roadmap/batch mapping as `/prd`.

The same scheduler now owns the half-hour Telegram heartbeat. It fires at `:00` and `:30`, summarizes server vitals plus queue progress and pet XP, and records a `half_hour_heartbeat_sent` event in Observatory so operator-visible status has an audit trail.

CypherClaw's live music transport now also preserves tracker provenance from the active character cast. Tracker solo scenes carry lane roles derived from the current cast, and scene-level role floors keep subdued sections anchored to a character-backed foundation lane so self-listener correlation has stable scene/lane context instead of free-floating note streams.
The same transport now preserves harmonic provenance too. `/tmp/midi_keyboard_state.json` carries keyboard-grimoire suggestions including tonic, mode, pedal-derived tension, and modulation intent, and tracker scene handoffs can carry per-scene key overrides so `Development` or `Recap` can pivot without losing the main song context.
Melodic provenance now rides along with that handoff as well. The live composer seeds score generation with `song_num`, tracker family, cadence state, and recent melodic-memory fragments, so repeated household moods can still yield fresh motif and rhythm cells while occasionally recalling transformed material from earlier songs. The same score seed now also selects a comping style, so the bass/foundation lane is not locked to one accompaniment figure.
That melodic handoff is now family-aware too. Recent tracker songs are tagged with family, progression profile, cadence state, and house patch before they are committed to melodic memory, and the next tracker song can ask for fragments that match those tags so returning to a family can feel like recall or response instead of starting from neutral material every time.
Within a song, the handoff is now scene-aware too. When `Theme` has already been built, `Recap` and `Release` can inherit lane-level motif shapes from it and mark that provenance in scene/lane metadata, so the scheduler can treat those sections as deliberate recalls rather than just another rendering of the source score.
Instrument provenance is preserved there too, but it is no longer naive: tracker lanes keep explicit cast-derived synth choices when they fit the lane role, long texture/counter lanes normalize overly ringing cast hints before runtime scheduling, `wind_down` handoffs soften chirpy melody/texture voices before they reach the live scheduler, and quarantined leak-prone or unavailable voices such as tracker `grain` and `tabla_ge` can be remapped at runtime without erasing the cast metadata, even when the runtime path is still carrying raw `sw_*` synth names.
The tracker handoff now also carries a coherent instrument-patch policy. Normal occupied songs resolve into named house patches with western-compatible ensemble blends, and those patches now influence contour, comping, dynamics, and register spacing in addition to voice choice. The old detuned `bell` / `metal` voices are retired at runtime instead of being allowed to slip back into the live playback path.
That handoff also now keeps enough patch/form metadata for the live scheduler to vary actual scene shape. Song number can select different tracker forms and scene lengths, patch metadata survives through cadence/family shaping, bass-role material is kept in a lower register, and playback applies a small high-note softening pass instead of letting the sharp top octave dominate.
The cadence handoff now also carries a progression profile alongside family selection. Day phase and weekly phase feed both a family palette and a harmonic profile, so repeated occupied-day states can rotate through different musical identities and chord motion instead of staying inside one `bloom`-shaped harmonic loop.
The handoff now also carries full musicianship metadata. Tracker songs now include section functions and cadence types from the reharmonizer, title and hook text from the hook engine, per-scene groove/entry intent from the arrangement engine, practice-block intent from the away-mode curriculum, and ear metrics plus promoted-song candidates from repertoire memory. `/tmp/composer_state.json` can therefore expose `song_title`, `text_hook`, `practice_block`, `scene_caption`, and `reharm_strategy` alongside the key and movement, which gives the face and operator tools a higher-level musical contract than raw transport state alone.
Above that handoff, CypherClaw now has a score-tree composition contract. The live composer can assemble a `PieceCommission`, derive a concrete `PieceBrief`, expand it into a `FormPlan`, and build a complete `ScoreTree` before tracker playback starts. Approved trees are the canonical composition object for a piece: they carry form class, composition mode, motif ids, section-function sequence, narrative beats, harmonic/cadence intent, and ending family. The tracker is now the renderer for that object, not the source of authorship. When the current context is stable enough, a second approved score tree is persisted into `/home/user/cypherclaw-data/state/piece_queue.json` so the next committed piece can already exist before the current one ends. That handoff now has a recovery-oriented audibility rule too: the first post-boot commission is bounded away from the most extreme suite scale unless the cadence is already explicitly night/sleep-oriented, so recovery does not strand the room inside a nearly silent maximal-form opener. The score-tree to tracker handoff also now preserves articulated motion in long sections: `tracker_compiler.py` splits long target durations into scene repeat counts plus only modest note-length scaling, so section length is earned by repeated phrase cycles instead of turning the whole section into a few stretched sustained notes. The same handoff now also preserves section authorship: the compiler derives a fresh section score per scene, re-enriches its lane body, and applies section-function and motif transforms before tracker rows are emitted, so section names correspond to real note changes rather than only scene metadata. Inside longer scenes, the compiler now emits internal phrase-family provenance (`A`, `A_prime`, `B`, etc.) on tracker steps, and those families carry shared root/function profiles so melody, bass, counter, and color lanes move through the same section-level harmonic turns instead of varying independently. Adjacent scenes now have an authored transition handoff too: each non-final section publishes `transition_target_scene`, `transition_target_function`, `transition_target_root_degree`, and `transition_motion`, and the tracker marks the final-cycle tail notes as `transition_role=preparation` while retuning them toward the next section's root.
Long-section lane handoff is now staged as well. Tracker lanes can carry `entry_cycle` and `exit_cycle` metadata, and long development-oriented scenes keep bass/melody anchored from the start while counter and color lanes enter on later phrase cycles. That gives the scheduler a real thickening curve inside one scene instead of launching every role at row 0 for the full duration.
Motif-recall handoffs preserve that transition context. When `Recap` or `Release` borrows material from `Theme`, recalled steps drop the source scene's stale transition fields and receive the current scene's own transition target on the final preparation tail.
Section-level motif development now rides through the same handoff. Each compiled scene carries `motif_development` metadata such as `statement`, `sequence_fragment`, `contrast_inversion`, or `recall_answer`, and each tracker step can also carry `section_progression_root` / `section_progression_role` so diagnostics can see both the motivic transform and the local harmonic progression that shaped the emitted notes.
Rhythmic development is now part of that contract too. Compiled scenes and steps can carry `rhythm_development` and `rhythm_cell`, allowing sections to distinguish steady statements, forward pushes, arrival drives, syncopated fragments, half-time bridge displacements, recall grooves, and residual breath patterns instead of inheriting one incidental duration grid.
When a later scene recalls earlier motif material, the recalled steps now inherit the current scene's rhythm/progression profile as well as its transition target. That prevents `Recap` from borrowing `Theme` notes while falsely reporting `Theme`'s old rhythm cell.
Arrangement automation now rides through the tracker handoff too. Scenes publish an `arrangement_curve`, automation lanes carry row points rather than only defaults, tracker steps carry `arrangement_position` and velocity-scale provenance, and `/tmp/tracker_runtime_state.json` exposes current interpolated automation under `automation`. The scheduler uses low density to suppress optional support-lane events without dropping bass/melody continuity, and the live composer uses the same row state to refresh the master bus at musical intervals, so downstream diagnostics and the summed audio path agree about whether the section is rising, suspending, releasing, or fading.
The repertoire handoff now also stores structural memory. When a completed score-tree piece finishes, `repertoire_memory.py` writes a `score_tree_summary` containing the piece id, form class, composition mode, ending family, motif ids, section functions, and narrative beats. Future repertoire recall can therefore bias not only title/hook surface language but also structural choices like form family, recurrence pressure, and payoff placement.
The EMSD handoff layer is now active in the live scheduler too. Course scaffolds under `my-claw/curriculum/EMSD-*` map the degree into runtime modules, `practice_curriculum.py` now points each away-mode study block at concrete EMSD course codes, and `emsd_runtime.py` turns the palette/sample/mix/arc/DSP/capstone helpers into one typed live context. Tracker scene starts now write that EMSD context into `/tmp/composer_state.json` as `arc_phase`, `arc_transition_intent`, `mix_target_lufs`, `sample_source`, `sample_transforms`, `dsp_blocks`, `dsp_source_focus`, `glyph_visual_bias`, and artistic-identity fields, so other daemons do not need to recompute the same production state.
The self-listener now also republishes that contract for the visual side. Each capture pass writes `/tmp/glyph_audio_features.json` with brightness/motion/texture/density derived from live audio plus the active EMSD arc/sample/DSP metadata, which gives GlyphWeave a stable bridge from sound analysis to visual behavior instead of only ad hoc audio amplitude cues.
The EMSD sampling handoff now has its own authority file too. The room, contact, Theramini, and self listeners each mirror their freshest clip into `/tmp/room_capture.wav`, `/tmp/contact_capture.wav`, `/tmp/theramini_capture.wav`, and `/tmp/self_capture.wav`, and `self_listener.py` combines those stable paths with live composer/cadence/sensor state into `/tmp/sample_dsp_activity.json`. Downstream sampler or DSP code can read that file to know whether the chosen source is fresh enough to use, whether it should trigger now, and which concrete activity profile to apply. That planner can also resolve away from an unavailable requested source onto a fresh fallback capture, so the handoff remains usable even when one source family is not live on the current box.
For unavailable Theramini sampling, that fallback now prefers `contact_mic` and then `room_mic` before `self_bus`. This keeps missing external-instrument capture from collapsing immediately onto a quiet self-monitor clip when another live environmental capture is fresher.
When the live sampler layer is running, `sample_playback_engine.py` consumes that handoff and publishes a second authority file at `/tmp/sample_playback_state.json`. That file records the last playback decision, whether a rendered sample event is still playing, the resolved source path, the rendered output path, and any render/playback failure reason. Operator surfaces should treat `sample_dsp_activity.json` as the sampler plan and `sample_playback_state.json` as the sampler execution state.
The rendered output path is now archive-aware too. On a host with the large archive volume mounted, sample-event WAVs default under `/mnt/archive/cypherclaw/sample_events`; otherwise they fall back through the legacy `cypherclaw-data` layout or a project-local archive directory. This keeps the sampler's render cache from filling the root filesystem during long unattended runs.
`sample_dsp_activity.json` also now preserves the original requested sample source even when the planner intentionally retargets to a different live source, such as a sparse late-phase `self_bus` request being redirected to `room_mic`. That keeps operator surfaces and debugging tools honest about what the EMSD layer asked for versus what the runtime chose to perform.
That handoff now also carries scene-shaping intent for the sampler, not just source and trigger information. Downstream sampler code can read fields like `scene_profile`, `render_duration_s`, and `peak_target` to know whether it should behave like a `Development` grain study, a `Theme` accent layer, a `Recap` echo, or an `Afterglow` residue.
The capstone/EMSD planners now hand off `room_mic` as the default ambient source for Divination on this installation. `garden_mic` remains a valid optional source in the catalog, but the live runtime no longer assumes it is the primary ambient capture surface.
The room-speech handoff now also carries capture provenance. When `room_listener.py` succeeds, it can publish `capture_backend` (`jack` or `alsa`) and `capture_source` into `/tmp/room_speech.json`, so downstream diagnostics can tell whether the ambient sampling path is actually using the Perform-VE condenser route or an automatic fallback.
The self-monitor handoff now carries capture provenance for the same reason. `self_listener.py` still supports PipeWire and `pw-jack` fallback capture strategies, but the AV boot wrapper now pins it to the verified JACK path on the live host so the meter follows the same graph that is actually feeding Scarlett. It still sets `JACK_NO_START_SERVER=1` for those JACK probes, publishes `capture_backend` alongside `capture_port` in `/tmp/self_listen.json`, caches the last known-good fallback backend, and resets that cache after failed capture passes, so a blocked subprocess pipe or bad boot-era backend guess does not leave `/tmp/self_listen.json` stale for the rest of the session. If the direct recorder times out anyway, the listener can now analyze a fresh `/tmp/room_capture.wav` clip as an audio-derived fallback instead of collapsing to silence-only monitor state. The listener now also derives glyph-facing brightness and motion from the captured audio itself rather than from target-only spectral metadata, so `/tmp/glyph_audio_features.json` is closer to playback truth.
There is now a system-level cold-boot handoff for that same stack. `cypherclaw-av-stack.service` can call `cypherclaw_av_boot.sh` at `graphical.target`, and that wrapper re-establishes the same live invariants the manual recovery used: audio first, then composer, then the meter, then room/sampler backfill if needed, plus explicit face/gallery restarts under X so stale display clients do not survive reboot recovery. That wrapper now also exports the user `XDG_RUNTIME_DIR` before launching those display clients, which matters on the live box because SDL/X can stay blank even with `DISPLAY=:0` when the user session runtime dir is missing. It chooses the self-listener backend up front, runs a second delayed dedupe pass so stale late-start copies from other hooks are collapsed back to a single surviving daemon, and `cypherclaw_boot.sh` now delegates core AV ownership to that wrapper instead of racing it with its own copies of the same daemons.
That cold-boot handoff now also repairs the known dual-head layout on the live box: after X comes back, `cypherclaw_av_boot.sh` normalizes `DP-2` to the face screen's `1280x1024` mode and `DP-0` to the gallery screen's `3840x2160` mode, then relaunches the face on `:0.0` and the gallery on `:0.1`. This matters because the gallery used to restart into the correct X server but the wrong coordinate space, which left a large black region on the 4K monitor.
The playback handoff now consumes EMSD state as well as publishing it. `play_voice()` can read the active EMSD context and use it to adjust level, release, brightness, detune, delay, high-pass, and drive at the note boundary, and tracker scene starts now also translate `mix_*`, `master_amp`, and `reverb_send` into live `sw_master_smooth` master-bus updates. That means the same `sample_source`, `sample_transforms`, `dsp_blocks`, and `mix_*` fields that appear in `/tmp/composer_state.json` are no longer descriptive only; they now change both note rendering and the summed output path.
The operator handoff now has a matching diagnostic view. `my-claw/tools/senseweave/operator_diagnostics.py` reads `/tmp/current_score_tree.json`, `/tmp/tracker_runtime_state.json`, `/tmp/composer_state.json`, `/tmp/sample_dsp_activity.json`, `/tmp/sample_playback_state.json`, `/tmp/master_bus_state.json`, and `/tmp/self_listen.json`, then daemon `/status` reports the current score tree, section function, arrangement curve, ear metrics, sample source, master bus, and self-listener state. The same output includes rollout flags from `my-claw/tools/senseweave/rollout_controls.py` so operators can confirm whether `CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE`, `CYPHERCLAW_ENABLE_PREVIEW_RENDER`, `CYPHERCLAW_ENABLE_SELF_CRITIQUE`, and `CYPHERCLAW_ENABLE_LONG_FORM_SUITE` are active before changing behavior.
That master-bus handoff now has a recovery rule too. Because `duet_composer.py` clears the root group on startup, `restart_composer.sh` reseeds `sw_master_smooth` once before launch and once after the new composer PID is confirmed alive, so the live scene-start `/n_set` messages do not target a missing node during the first piece. The tracker-runtime handoff carries a matching loudness floor: primary melody/bass/rhythm events leave the compiler with a higher safe amplitude floor than the old sketch defaults, so a healthy running piece still reads as present on the Scarlett monitor path and in `/tmp/self_listen.json`. That handoff is now mix-aware too: texture lanes carry a nontrivial floor, bass is slightly de-emphasized relative to melody, and EMSD note-level amp shaping uses a softer scaling curve so normal `away_practice` songs do not pin bass and melody against the same amp ceiling.
The camera handoff is stricter now too. `observer_vision.py` writes `video_device` into `/tmp/observer_state.json` and only marks a frame capture successful when the underlying `ffmpeg` call returns success, so an old `/tmp/observer_frame.jpg` can no longer pretend to be live video after a webcam fault. On single-camera installs, `room_presence_daemon.py --observer-frame-only` can derive `/tmp/room_presence.json` from that shared observer frame instead of racing `observer_vision.py` for `/dev/video0`; in that mode it reports `capture_source: "observer_frame"` and mirrors the shared frame into `/tmp/room_frame.jpg` so downstream consumers still get a fresh room image path.
The boot-owned porch and side capture rings now follow the same storage rule. When `cypherclaw_boot.sh` sees the 10TB archive mount, it writes those camera capture directories under `/mnt/archive/cypherclaw/camera/...` instead of `/tmp`, and `archive_daemon.py` reads from the same resolved paths when it snapshots those camera feeds into the long-term archive.
The slow observer description handoff now exposes degradation honestly too. The boot path points `observer_vision.py` at `OBSERVER_OLLAMA_URLS=http://127.0.0.1:11435/api/chat,http://127.0.0.1:11434/api/chat`, so the dedicated observer queue on `11435` gets first chance before the shared local model queue. When either multimodal call succeeds, `/tmp/observer_state.json` carries the model-written description. When both endpoints are saturated, the observer emits a compact local fallback description, records `vision_backend: "local_fallback"`, preserves the full `vision_error`, and backs off before retrying the slow call. That keeps the handoff semantically useful without pretending the local model was actually available.
The repertoire handoff now also runs in the forward direction. Before score generation starts, the live composer can read a repertoire influence keyed by family and cadence state, use it to bias the current progression profile, pass the same influence into title and hook generation, and now also steer tracker-form selection, section-density shape, and payoff-scene emphasis. That lets repertoire memory shape the next song instead of only summarizing the previous one. The hook answer path now uses phrase-level transforms so recalled lyrical material stays grammatical when the next song answers an earlier one, and those transforms can vary by family/cadence/song context instead of always returning a single stock answer. The hook path now also normalizes a small set of known awkward historical phrases before they enter live song state, so rough recalled material gets pulled back toward the current house vocabulary instead of resurfacing verbatim. Title generation now follows the same image field as the hook at the modifier and noun level, and the live planner also weights cadence state, progression profile, and hook type when picking among valid title phrases. That keeps live song names and hook text inside one symbolic neighborhood while still letting a quiet settling song say `Low Light` and a more rhythmic daytime callback say `Electric Circuits` instead of reusing one stock label. The title handoff also now avoids exact repeats from repertoire source titles when alternatives exist. The scene-caption handoff is now section-aware as well, so the face layer can show a direct statement in `Theme`, a reflective variant in `Recap`, and a quieter residue in `Afterglow` from the same underlying hook. Those end-state captions are now harmonic-function-aware too, so `Resolution` and `Afterglow` can reflect whether the cadence is authentic, plagal, half, or deceptive. They are now orchestration-aware too: `patch_name` and lane count can compress sparse monastery/chamber scenes or widen dense workshop/procession scenes before the piece reaches its harmonic landing. Legacy broken hook text is also normalized at repertoire load time, so older bad entries do not keep contaminating future caption and hook generation.

The playback handoff now also carries stronger top-octave shaping. `voice_shaping.py` emits best-effort per-note `highpass_hz` and `saturation_mix` alongside the older gain/release/brightness shaping, and `play_voice()` forwards those controls when the runtime SynthDef can consume them. Notes above roughly `C6` are now folded down one octave, and the sharpest top band is folded down two octaves at the final playback boundary, so very high notes are both softened and moved decisively out of the ear-splitting register instead of only being played quieter.
The startup handoff now includes the upstream sample sources too. `cypherclaw_boot.sh` still launches `theramini_listener.py` and `contact_listener.py` in the same boot pass, so the EMSD sampler surface can rely on live capture aliases instead of watching permanently missing Theramini or contact-mic paths.
