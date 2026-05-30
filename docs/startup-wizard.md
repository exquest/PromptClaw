# Startup Wizard

```text
 /\_/\\
( o.o )  startup wizard 🦀✨🎠
 > ^ <
```

PromptClaw v2.1 adds an interactive wizard for creating a new claw.

## What it does

The wizard asks startup questions **one at a time** and translates the answers into:

- starter prompts
- agent instructions
- project description
- enabled agent roster
- capability tags in `promptclaw.json`
- a startup profile and transcript

## How to run it

### Automatically during init

```bash
promptclaw init my-claw --name "My PromptClaw"
```

### Manually later

```bash
promptclaw wizard my-claw
```

## What the wizard asks

Core topics:

- project mission
- task families
- usual outputs
- agent roster
- routing rules
- verification style
- autonomy level
- ambiguity handling
- hard boundaries

## Smart follow-ups

The wizard adds follow-up questions when it detects missing signal.

Examples:

- vague task families → asks for the top 3 priorities
- code-heavy outputs without testing guidance → asks whether code should include tests
- autonomous workflow → asks what still requires approval
- weak ambiguity policy → asks what the first follow-up question should pin down
- vague boundaries → asks for two hard red lines

## Files it writes

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `prompts/agents/*.md`
- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`
- `.promptclaw/onboarding/startup-session.md`
- `promptclaw.json`

## Design notes

- The wizard is **heuristic-first** so it works in mock mode and before live agents are configured.
- Custom agent names are supported; new prompt files are created automatically.
- Agents not selected in the wizard are disabled in `promptclaw.json`.
- When you later switch an agent to live `command` mode, PromptClaw runs it from the project root and fills `{prompt_file}` with an absolute path to the generated prompt artifact.
- PAL 2026 agent workflows are post-init, opt-in operational workflows. The startup materials may describe PAL's role, but `promptclaw pal agent triage` still uses a local diagnostic allow-list. PAL plan and summary prompts can include a bounded `Knowledge Context` section from the local PAL KB after `promptclaw pal kb build` has run. `promptclaw pal agent actions` is proposal-only unless the operator passes `--approve ACTION_ID`, so infrastructure mutation remains a human approval gate. The slow-inference context and diagnosis paths are also read-only: `promptclaw pal diagnose slow-inference` records health, baseline token/s, optional GPU hints, optional logs, and local findings into run artifacts without exposing action ids or changing infrastructure. `promptclaw pal validate restart` adds a post-restart validation workflow that records health, one direct query, active smoke, Tailscale, and process-check observations with `mutating_actions: []`. `promptclaw pal audit shutdown` adds a read-only shutdown audit that records shutdown enabled state, override state, next shutdown window, cron evidence, and recent logs with `mutating_actions: []` and no shutdown override changes. `promptclaw pal report phase2-readiness` adds a report-only Phase 2 readiness workflow that scores prerequisites and records `phase2_execution_actions: []` without an approval or execution path. `promptclaw pal deploy apply` requires `--approve-apply` and `promptclaw pal deploy rollback` requires `--approve-rollback`; both currently mutate only a supplied local fake remote inventory snapshot, with `live_ssh=false` and no service restarts. The Vast connector is also only a stub boundary by default: `rent`, `destroy`, `start`, and `stop` are blocked metadata, not callable action ids.
- The Deniable Asset Bus producer keeps renderer execution behind the `BoxRunner` boundary. `process_pending_requests_once(...)` snapshots pending requests for one pass, delegates each id to `process_request_if_pending(...)`, and converts per-request failures to `error` manifests so the rest of the batch keeps moving. `run_asset_bus_producer(...)` is the continuous producer run mode: it repeats that pass on a poll interval so newly arrived requests are processed on the next loop. `FakeBoxRunner` stays the unit-test transport, while `SSHBoxRunner` sends renderer argv as JSON stdin to a fixed remote helper and uses argv-list `ssh`/`rsync` calls with `shell=False`, so request text from prompts, scenes, or moods is not interpolated into shell commands.
- CypherClaw live command projects can layer quota-aware routing on top of those rules, redistributing work away from providers with degraded headroom and collapsing to single-agent mode when only one provider remains viable.
- Operators can also force the live daemon into local-only routing with `LOCAL_ONLY=true`. That runtime override collapses agent execution to `ollama` even if the startup materials or routed step payloads mention cloud agents.
- In the live CypherClaw home, those startup materials now feed a preflight-gated runtime: bootstrap prepares a tmpfs workdir, authoritative DBs stay on disk, and the queue runner refuses to start if maintenance mode or integrity checks say the home is not safe.
- Runtime identity is also bootstrapped on startup. Both daemon poll loops and the narrative ASGI `main:app` import path call `bootstrap_identity()` before first-boot announcement/app creation, so standalone and federated homes mint identity once and reuse it across boots.
- Maintenance mode itself is authority-backed at `.sdp/MAINTENANCE`; direct maintenance entry now requires an explicit operator override when the runner is active so queued tasks cannot accidentally shut down their own runtime.
- The same live daemon toolchain is now portable across the MacBook and Linux server homes, so post-init status and runner checks do not assume one service manager or one repo layout.
- In the Linux server home, child CLIs launched by the daemon no longer inherit systemd watchdog variables, so helper processes do not generate spurious `Got notification message from PID ...` journal noise.
- The managed runner now also clears a stale `.sdp/run.lock` before preflight, so normal service restarts do not get stuck behind a dead PID from the previous runner process.
- The managed runner unit is also configured as a true queue supervisor: `Restart=always` restarts clean queue exits automatically, while maintenance-gated launcher exits use code `75` and are treated as intentional non-restarting stops.
- When a live home sits next to a checked-out `sdp-cli` repo, the launcher now auto-exports that sibling `src` tree into `PYTHONPATH` unless the operator already pinned a different value, so runtime behavior follows the checked-out source by default.
- In live CypherClaw homes, operator roadmap/status commands are also queue-backed where possible, so Telegram `/monitor`, `/prd`, and `/tasks` reflect the actual queue state and implementation order from `.sdp/state.db` instead of stale narrative summaries. Their totals count live executable tasks and exclude only split parents. `/monitor` also keeps `needs split` separate from `pending`, exposes queue-state drift if active task records and open run records disagree, and now includes compact `sdp-cli`-style gate/recent/provider lines. `/prd` distinguishes between stages that are truly absent, stages that are frozen, and stages that have only split-parent/decomposed work. `/tasks` defaults to the next actionable queue slices and supports focused backlog views like `/tasks pending 10`, `/tasks frozen`, `/tasks prd 6`, and `/tasks stage clone and home creation`.
- SDP agent templates are task-scoped around dirty worktrees: leads must commit the files they changed for the task, while verifiers treat unrelated pre-existing dirty files as notes rather than cleanup instructions.
- In the live server home, the daemon scheduler also emits a compact Telegram heartbeat at `:00` and `:30` with system vitals, queue progress, and pet XP so the operator can monitor the house without opening a shell.
- In the live CypherClaw music runtime, tracker solo mode now also binds itself to the active character cast: lane voices are hinted from cast roles, and subdued scenes keep a quiet cast-backed foundation lane through the middle movements.
- T-045c scene playback now also carries mood-space routing through startup-owned live playback: scheduled tracker events expose `render_space_*` metadata, and profiled voices keep their sounding synth while their `fx_bus_id` follows `mood_mode`, explicit `active_house`, or the `patch_name` fallback in house-bound mode. This adds no new dependencies and no database migration.
- The live music runtime now also includes a keyboard-grimoire lane: `midi_keyboard_listener.py` discovers the room keyboards, writes canonical harmonic suggestions, and the tracker composer can pivot across modal scene keys instead of flattening everything to one major root.
- The live score generator is no longer contour-only: CypherClaw now seeds melody and rhythm cells from song number, tracker family, cadence state, and recent melodic-memory fragments so similar moods do not keep producing the same phrase in a new key. It also rotates comping styles underneath those phrases so the accompaniment does not keep cycling one fixed pattern.
- That melody memory is now family-aware too: tracker songs are tagged with family, progression profile, cadence state, and house patch before they are stored, and future songs in the same family can recall or answer those tagged motifs instead of sounding like unrelated resets.
- The tracker form now also remembers itself inside a song: once `Theme` is built, `Recap` and concise-form `Release` can reuse that lane-level material with a small answering resolution, so later sections feel like returns instead of just being slower or denser copies of the same score.
- The full M1-M6 musicianship layer is now part of the live runtime too. Tracker songs get section functions and cadence types from a reharmonizer, deterministic song titles and hook text from a hook engine, scene-level groove/density shaping from an arrangement engine, away-mode practice blocks from a deliberate curriculum, note-level self-critique from an ear engine, and long-term song storage in repertoire memory.
- The live songwriter is now two-layered. The tracker still performs the piece, but a score-tree layer above it can now commission a piece, derive a concrete narrative brief, choose a form grammar, recursively compose a full section/motif tree, reject underbuilt sketches, and only then compile the result into tracker scenes. That is the beginning of the move from short tracker-first sketches toward longer committed songs and suites.
- That same commission layer now protects cold-start audibility too. On a fresh restart, the first commissioned piece is biased away from the sparsest `suite` case unless the cadence is already explicitly wind-down or sleep-oriented, so runtime recovery produces a heard piece before it attempts its longest forms.
- Long sections are now built by repeated phrase cycles rather than only by stretching note lengths. That keeps `extended` and `suite` recoveries sounding like moving songs instead of a few isolated tones suspended across the whole scene.
- Those long sections are now also section-written instead of only section-labeled. The score-tree compiler derives separate scene scores and applies section-function transforms before tracker quantization, so `Theme`, `Development`, `Recap`, and late residues can carry different note bodies instead of the same phrase being stretched across a bigger form.
- Development-oriented sections now go one level deeper: the compiler can build internal phrase families like `A`, `A_prime`, and `B` inside the section before tracker repetition starts, and those families now share root/function profiles across melody, bass, counter, and color lanes. That makes long sections less like independent loops and more like coordinated recursive songwriting.
- Section transitions are authored now too. The compiler tags each non-final section with the next section's target scene/function/root, and the tracker retunes only the final repeat cycle's tail notes toward that root so a long scene prepares the following scene instead of simply stopping and restarting.
- Long sections now thicken internally. Tracker lanes can start and stop on different repeat cycles, so development sections can begin with bass/melody and add counter/color later instead of looping the full ensemble from the first row.
- Later scenes that recall earlier motifs now keep their own transition targets. A `Recap` can borrow `Theme` material without accidentally inheriting `Theme`'s old handoff destination.
- The live compiler now labels how each section develops the motif and which local progression it follows. This lets `Theme` state material, `Development` sequence and fragment it, `Bridge` invert/contrast it, and `Recap` answer it while the bass lane follows the section progression instead of one global loop.
- The live compiler now also labels and reshapes section rhythm. `Theme` stays steadier, `Development` gets syncopated fragments, `Bridge` stretches into half-time displacement, and late sections slow or breathe out, so the same motif/progression layer does not sit on one static grid.
- Recalled material keeps the current section's rhythm identity. If `Recap` borrows notes from `Theme`, the live tracker still reports and shapes that recalled lane as `recall_groove`.
- Section rhythm now drives arrangement automation. Tracker scenes expose an `arrangement_curve`, row-based `density` / `master_amp` / `reverb_send` points, and per-step arrangement velocity metadata; the runtime also uses low density to thin optional support events while preserving bass/melody continuity, and the live composer applies those row values to the master bus during playback so long sections develop in event density and mix energy as well as notes.
- Score-tree scenes now receive composer-planned `meter_trajectory_*` metadata from the arc-phase meter trajectory planner, including a JSON `meter_trajectory_entry` for the scene's planned meter value. Generic tracker scene emission can derive those same per-scene keys from the compact trajectory payload. When a piece crosses a procedural arc-cycle boundary, the planner restarts the per-phase drift at the new `Divination` cycle. This is the metadata contract for upcoming active meter morphing; it does not yet change row scheduling or active groove-meter choice.
- CypherClaw also now keeps a small precomposed piece queue at `/home/user/cypherclaw-data/state/piece_queue.json`. The intended live behavior is one active performed piece, one next approved piece waiting in structural form, and repertoire memory that remembers not only titles/hooks but also score-tree summaries like form class, section functions, motif ids, and ending family.
- That repertoire memory now also biases future songs. When the current family and cadence state line up with a strong earlier song, CypherClaw can reuse that song's progression profile, answer its title/hook language, borrow a remembered form bias like `bridge` or `afterglow`, and even push the new song toward a remembered payoff scene instead of always generating the next piece from a blank slate.
- The hook-language path is now safer for face text too. Answer-mode hook rewriting uses phrase-level transforms instead of a generic `again` fallback, so recalled phrases stay grammatical when the new song answers an earlier one. Those answer phrases also vary with family and cadence context, which keeps repertoire recall from sounding like one fixed line every time it returns.
- Face captions now track section role too. When a song moves from `Theme` into `Recap` or `Afterglow`, the visible line can change from a direct statement into a more reflective or quieter variant of the same hook instead of repeating the same text unchanged.
- End-state captions now respond to harmony too. `Resolution` and `Afterglow` can present a different residue depending on whether the cadence lands authentically, plagal, deceptively, or only half-resolves, which makes the face feel more musically literate.
- Early-scene captions now respond to orchestration density too. Sparse monastery/chamber scenes read more quietly and compressed, while dense workshop/procession scenes read more outwardly, so the face can react to texture even before the cadence resolves.
- The hook generator also self-corrects a few older ugly phrases now. If repertoire memory still contains things like `carry the line wide` or `open the room open`, the live runtime repairs them before they reappear as current hook text.
- Titles and hooks are now more semantically aligned too. If the hook is about light or lines, the generated song title is more likely to live in that same image field at both the modifier and noun level, and the live planner now also nudges those titles by cadence, harmony profile, and hook type so quiet settling songs and brighter kinetic songs do not keep getting the same label.
- Very high notes now get a stronger safety layer too. In addition to being softened by gain/release/brightness shaping, the runtime now sends best-effort high-pass and slight drive values for the sharpest notes when the active SynthDefs can consume them, and folds the highest octave down by one octave before playback.
- The repertoire store now self-heals older broken hook text when it is read. That means historical songs written before a hook-language fix no longer keep reintroducing bad phrases into current live output.
- Low-energy tracker songs now also keep a support-role character in the cast so the installation can continue surfacing the broader instrument family instead of orbiting the same melody/rhythm/harmony trio forever, but quiet late-night scenes route through a safety layer so ringing or chirpy voices do not turn the installation into an overnight drone or birdsong machine. The current live build also quarantines tracker `grain` to a softer texture voice because the granular SynthDef was leaking nodes on CypherClaw, and aliases `tabla_ge` to `tabla_tin` until the missing tabla SynthDef is added.
- The live runtime also replaces `gong` playback with a tuned bowed substitute, because the original gong body was not sitting correctly against western/modal harmonic material.
- Tracker solo now also groups those voices into explicit house patches. Occupied listening defaults to western-compatible blends built from `bowed`, `pluck`, `choir`, and `breath`, while the old `bell` / `metal` layer is retired to tuned runtime substitutes instead of remaining in the live playback pool. Those house patches now also carry their own melodic contour, bass/comping, dynamics, and register behavior so the installation does not keep phrasing every song in the same vertical band.
- The live tracker form is no longer locked to one constant arc either. Song number can now select concise, bridge, or afterglow scene variants with different scene counts and length multipliers, patch metadata survives through the planner/runtime boundary so bass stays lower and color voices sit higher, and the top octave is softened at playback time with a gentle saturation-style shaping pass.
- The EMSD study layer is now scaffolded too. `my-claw/curriculum/` contains generated EMSD course directories, and the runtime has dedicated lab modules for sound palette design, environmental sampling, mix planning, procedural arc logic, DSP scenes, artistic identity, and capstone-cycle planning.
- That EMSD layer is now partially live as authority state too. Tracker songs publish arc/mix/sample/DSP/identity fields into `/tmp/composer_state.json`, and `self_listener.py` derives `/tmp/glyph_audio_features.json` from the current audio plus that EMSD state so visuals can follow the same musical plan.
- That same EMSD layer now affects playback too. If the current scene says `garden_mic + spectral_smear + long_convolution`, the notes render softer and bloomier; if it says `theramini_in + parallel_delay`, frontline notes widen and duck more. So EMSD state is now both descriptive and audible.
- EMSD sampling now has stable live capture paths too. The room, contact, Theramini, and self listeners refresh `/tmp/room_capture.wav`, `/tmp/contact_capture.wav`, `/tmp/theramini_capture.wav`, and `/tmp/self_capture.wav`, and `self_listener.py` publishes `/tmp/sample_dsp_activity.json` so downstream sampler/DSP code can tell which source is ready, which activity mode should run, and whether the current source should trigger at all.
- The live boot path now starts `sample_playback_engine.py` as well, so CypherClaw can immediately turn that EMSD sampler plan into audible room-derived events after startup. The daemon reports execution status in `/tmp/sample_playback_state.json`, while the face display reads the sampler plan directly to mirror the current source and mode. On machines with the archive disk mounted, those rendered event WAVs now default to `/mnt/archive/cypherclaw/sample_events`.
- The sampler planner is now room-first in lived-in sparse phases too. If the late arc would otherwise drift onto `self_bus`, CypherClaw can intentionally retarget back to `room_mic` when the room capture is fresh, while still preserving the original requested source in the state files for debugging and operator visibility.
- The room-sampling layer now follows the song form more explicitly as well. Even with the same source, `Development` can render as a denser grain cloud while `Afterglow` and `Resolution` can render as longer, softer room residue, so the EMSD layer behaves more like an arrangement voice and less like one generic ambient effect.
- That sampler activity layer now degrades gracefully too. If the requested capture family is unavailable on the current machine, the planner can resolve onto a fresh room/contact/self alias instead of exposing a dead sample path all night.
- The ambient EMSD default is now the room/Perform-VE mic path. On this installation, Divination no longer assumes an active garden capture; the outdoor source stays optional while the room condenser feed is treated as the primary atmospheric sampler.
- The room listener now advertises how it is capturing too. Startup no longer forces ALSA-only mode; it prefers the Perform-VE JACK route and falls back automatically, and `/tmp/room_speech.json` now tells you which backend and source were actually used.
- If the named Perform-VE JACK port is missing, the room listener now tries live JACK capture fallbacks such as `system:capture_1` before ALSA, so room capture keeps refreshing instead of leaving the sampler stuck on a stale room file or quiet self-bus fallback.
- The capture order is now `PipeWire -> JACK -> ALSA`. That gives the Perform-VE device a real chance to work through PipeWire’s conversion layer before the listener falls back to lower-level raw device probing.
- If JACK is unavailable, ALSA fallback now prefers the Perform-VE interface first. That keeps the room/ambient sampler on the condenser mic instead of silently drifting to a webcam capture path.
- The ALSA fallback path now also retries alternate sample formats per device, which matters for interfaces like Perform-VE that may enumerate correctly but reject the first capture format.
- The audio boot path is now less brittle too. `start_audio.sh` links the live SynthDef bundle into SuperCollider's default synthdef directory, boots `scsynth` with auto-load enabled, and prefers the real Scarlett JACK graph before falling back to `pw-jack`. That preference is now checked at runtime too: if the real-JACK launch never exposes `SuperCollider:out_1`, the script retries on `pw-jack` automatically instead of leaving the box silent, and when the Scarlett JACK path itself has drifted away it now rebuilds `jackdbus` against ALSA `hw:USB` before trying again. `restart_composer.sh` now only restarts the composer and reseeds the master bus if `scsynth` is already up, waits for a healthy steady-state composer process instead of only trusting the first child PID, launches it with `nohup setsid ... </dev/null` so it survives session teardown, and `self_listener.py` is now pinned to the verified JACK monitor path on this host while still keeping the older PipeWire and `pw-jack` recorders as explicit fallback paths. The fallback selector still uses `JACK_NO_START_SERVER=1`, caches the last known-good backend, re-probes real JACK on a slower cadence, discards recorder child output so the live meter loop does not stall on a blocked subprocess pipe, and can fall back to a fresh `/tmp/room_capture.wav` clip when the direct JACK recorder hangs.
- That restart path now also does a second master-node seed after the new composer PID is verified, because the composer's startup clear of the root group would otherwise leave the first live piece effectively silent even though tracker scheduling was already running.
- Tracker playback now also leaves the runtime hotter than the old sketch-era defaults. Melody, bass, and rhythm lanes use a stronger safe amplitude floor, which makes a healthy recovered song easier to hear in the room and easier to confirm through `/tmp/self_listen.json`.
- That louder floor is now balanced rather than just boosted. Texture lanes have a real supporting presence, while bass and melody are no longer pushed so hard that they flatten together at the top of the EMSD amp range.
- For cold boots, the repo now ships `cypherclaw_av_boot.sh` plus `my-claw/systemd/cypherclaw-av-stack.service`. That service is intended to be enabled at `graphical.target` and re-establishes the live AV stack after reboot by calling the hardened audio/composer scripts only when the core stack is still missing, waiting for `SuperCollider:out_1`, relaunching the self-listener on the verified JACK path, force-restarting the face and gallery displays under X with the user runtime dir exported, and deduplicating/backfilling the room listener and sampler so another startup path cannot leave stale late-arriving copies behind. The wrapper now also reapplies the live dual-head geometry after X recovery, keeping the face on `:0.0` / `DP-2` at `1280x1024` and the gallery on `:0.1` / `DP-0` at `3840x2160`. `cypherclaw_boot.sh` now delegates core AV ownership to that wrapper instead of starting overlapping copies of the same daemons itself.
- On the current single-webcam install, let `observer_vision.py` own `/dev/video0` and start `room_presence_daemon.py` with `--observer-frame-only`. That keeps `/tmp/observer_frame.jpg` fresh for monitor diagnostics, mirrors a fresh `/tmp/room_frame.jpg` for archive consumers, and avoids two daemons contending for the same camera during unattended boot.
- The heavy archive/capture paths now prefer the 10TB volume automatically. If `/mnt/archive` is mounted and writable, boot-time porch/side capture rings, archive-daemon outputs, sample-event renders, and Litestream file replicas should live under `/mnt/archive/cypherclaw` instead of filling the NVMe root disk.
- The observer path now prefers a dedicated local Ollama queue on `127.0.0.1:11435` through `cypherclaw-observer-ollama.service`, with the shared `11434` queue as fallback. If both are saturated, `observer_vision.py` still stays readable instead of surfacing the raw HTTP error: it emits a short local fallback description, records `vision_backend` / `vision_error` in `/tmp/observer_state.json`, and waits before retrying the slow multimodal call.
- The standard CypherClaw boot path now launches `theramini_listener.py` and `contact_listener.py` alongside the room listener, so those EMSD sample aliases are populated without a manual operator step.
- The day itself now changes family choice more actively too. Mid-morning, midday, late afternoon, Friday lift, and Sunday settle states each feed different family palettes and progression profiles, so the house can stay coherent without repeating one `bloom` song all day.
- The face layer now has higher-level musical state to surface as well: `keyboard_chat.py` can react to song-title changes from `/tmp/composer_state.json`, and tracker scene starts can publish short captions instead of only raw movement names.
- `/status` is now the first post-startup SenseWeave diagnostic check. It reads the same authority files as the face and sampler stack and reports score tree, section function, arrangement curve, ear metrics, sample source, master bus, self-listener, and the four rollout flags. During staged rollout, toggle `CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE`, `CYPHERCLAW_ENABLE_PREVIEW_RENDER`, `CYPHERCLAW_ENABLE_SELF_CRITIQUE`, and `CYPHERCLAW_ENABLE_LONG_FORM_SUITE` one at a time, then restart only the daemon or composer process that consumes the changed flag.
- Test, drill, and copied task-run subprocesses are prevented from messaging the live operator chat by default. `my-claw/tools/telegram.py` suppresses sends under `pytest`, `PROMPTCLAW_TEST_MODE`, or tmpfs task-run workdirs unless `PROMPTCLAW_ALLOW_LIVE_TELEGRAM=1` is set explicitly.

## Typical loop

```bash
promptclaw init my-claw --name "Research Claw"
cd my-claw
promptclaw doctor .
promptclaw bootstrap .
promptclaw run . --task "Compare orchestration patterns and propose an implementation plan."
```

For live server operations after the project is initialized:

```bash
bash my-claw/tools/init_workdir.sh
python my-claw/tools/preflight.py --project-root .
promptclaw doctor .
```

On a plain starter project, `promptclaw doctor .` stays lightweight and config-focused. On a live CypherClaw runtime root, it now folds in runtime preflight automatically.
