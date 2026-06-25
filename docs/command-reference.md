# Command Reference

## `promptclaw init`

Create a new project scaffold.

```bash
promptclaw init PATH [--name NAME] [--no-wizard]
```

Creates:

- `promptclaw.json`
- `prompts/`
- `docs/`
- `.promptclaw/`
- example tasks

When running in an interactive terminal, `init` launches the startup wizard unless `--no-wizard` is passed.

## `promptclaw wizard`

Run the startup wizard again for an existing project.

```bash
promptclaw wizard PROJECT_ROOT
```

Use this when:

- the claw’s purpose has changed
- you want to refine routing
- you want to change the agent roster
- you want a fresh startup transcript

## `promptclaw doctor`

Validate a project.

```bash
promptclaw doctor PROJECT_ROOT
```

Checks:

- config file exists
- prompts directory exists
- artifact root exists
- agents are configured
- command agents have executable commands
- control plane agent exists if `mode=agent`
- if the project root also contains live CypherClaw runtime markers, runtime preflight is run too

For CypherClaw live deployments, the repo also ships runtime safety tools that sit beneath `promptclaw doctor` until the unified doctor/preflight path lands:

- `python my-claw/tools/preflight.py --project-root PROJECT_ROOT`
- `python my-claw/tools/runtime_checkpoint.py --project-root PROJECT_ROOT`
- `python my-claw/tools/maintenance_mode.py --project-root PROJECT_ROOT status`
- `bash my-claw/tools/safe_reboot.sh prepare --actor operator --dry-run`
- `bash my-claw/tools/safe_reboot.sh resume --checkpoint PATH --actor operator --dry-run`
- `python my-claw/tools/live_reference_capture.py --duration-seconds 60`

If `PROJECT_ROOT` looks like a live CypherClaw runtime, `promptclaw doctor PROJECT_ROOT` now runs the same preflight automatically and reports it as a separate doctor check.

Run `live_reference_capture.py` on the CypherClaw Linux host for the CC-102
streaming checkpoint. It saves
`/home/user/cypherclaw/var/reference-renders/feature-3-stream-{timestamp}.opus`
and appends a SHA-256 record to `checksums.jsonl`. Use `--dry-run` first to
inspect the planned HLS URL, output path, checksum log, and ffmpeg command.

## `promptclaw bootstrap`

Run the bootstrap task using the startup materials.

```bash
promptclaw bootstrap PROJECT_ROOT
```

Equivalent to composing a task from:

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `docs/STARTUP_PROFILE.md` if present

## `promptclaw upgrade`

Add coherence assets to an existing PromptClaw project without overwriting local
configuration or prompt work.

```bash
promptclaw upgrade PROJECT_ROOT
promptclaw upgrade PROJECT_ROOT --dry-run
promptclaw upgrade PROJECT_ROOT --force
```

The command merges missing coherence defaults into `promptclaw.json`, preserves
other config keys, writes `constitution.yaml` only if it is absent, and creates
the scaffolded `prompts/agents/*.md` files only when they are missing. `--dry-run`
prints the planned writes without mutating files. `--force` refreshes only the
coherence protocol section of existing agent prompts; local prompt content above
that section is left intact.

## `promptclaw run`

Run a task.

```bash
promptclaw run PROJECT_ROOT --task-file FILE
promptclaw run PROJECT_ROOT --task "free text"
```

For live `command` agents, PromptClaw executes from `PROJECT_ROOT` and renders `{prompt_file}` and `{project_root}` as absolute paths.

In CypherClaw live command deployments, `run` can also honor `sdp-cli` quota telemetry. Healthy and warn providers stay eligible for routing, degraded providers stop receiving new work, and full exhaustion falls back to the provider with the best remaining headroom so runs continue in degraded mode.

For SDP-backed queue runs in a dirty workspace, local agent templates use
task-scoped verification. A verifier should fail uncommitted work introduced by
the current task, but should report unrelated pre-existing dirty files as notes
instead of asking the lead to clean the repository.

Before the long-running queue starts, the runtime launcher also enforces:

- maintenance mode must be inactive
- preflight must pass
- a stale `.sdp/run.lock` from a dead runner PID is cleared automatically before preflight
- the tmpfs workdir must be present and correctly linked to disk-authoritative DBs
- child CLI processes spawned by the live daemon run without inherited systemd watchdog variables

For fully local daemon operation, export `LOCAL_ONLY=true` before starting `my-claw/tools/cypherclaw_daemon.py` or the managed runner. In that mode the daemon exposes only the `ollama` agent, bypasses cloud router CLIs, and coerces any explicit cloud-agent execution step back to `ollama`.

## `promptclaw resume`

Resume an ambiguous task.

```bash
promptclaw resume PROJECT_ROOT --run-id RUN_ID --answer "clarification answer"
```

## `promptclaw status`

Show project status.

```bash
promptclaw status PROJECT_ROOT
promptclaw status PROJECT_ROOT --run-id RUN_ID
```

Status and future operator surfaces can use the shared `promptclaw.models`
summary helpers for stable JSON-safe config, route, and run-state diagnostics;
the command contract itself remains unchanged.

## `promptclaw show-config`

Print resolved config.

```bash
promptclaw show-config PROJECT_ROOT
```

The resolved config still comes from `promptclaw.json`; the model summary path
is an internal diagnostic projection and does not replace the source file.

## Deniable Asset Bus Runner

The asset-bus producer code uses `promptclaw.asset_bus.BoxRunner` rather than a
shell command string. Unit tests use `FakeBoxRunner`; production can use
`SSHBoxRunner(host=..., remote_output_root=...)` to invoke deployed CypherClaw
renderers over SSH and pull output files back with `rsync`.

The programmatic batch entry point is
`promptclaw.asset_bus.process_pending_requests_once(...)`. It snapshots pending
request ids and processes each independently, so a renderer or dispatch failure
for one request writes an `error` manifest and does not prevent later pending
requests from getting manifests in the same pass. The lower-level
`process_request_if_pending(...)` helper remains available for one request id:
existing callers may still supply a direct `render` callback; producer callers
can supply a `RendererMatrix` and `RendererRegistry` so the function reads the
request file, uses matrix/registry dispatch, and atomically writes the returned
result manifest.

The programmatic continuous run mode is
`promptclaw.asset_bus.run_asset_bus_producer(...)`. It performs one immediate
batch pass, sleeps for the configured poll interval, and then polls again so
newly arrived requests are processed without restarting the producer. Tests and
smoke harnesses can pass `max_polls` plus an injected clock; production callers
leave `max_polls` unset and stop the loop through process control or a supplied
stop predicate. The future `promptclaw asset-bus run` CLI is a separate command
slice.

`SSHBoxRunner.run(argv, output_dir=...)` expects a renderer argv list, sends
that argv as JSON stdin to the fixed remote
`promptclaw.asset_bus.remote_exec` helper, and calls both local `ssh` and
`rsync` through argv-list `subprocess.run(..., shell=False)` invocations. The
request prompt, scene, mood, and other request-derived strings do not appear in
the SSH or transfer command line.

## `promptclaw pal`

Call a configured PAL 2026 router from local tools.

```bash
promptclaw pal health PROJECT_ROOT
promptclaw pal query PROJECT_ROOT --prompt "Confirm reachability."
promptclaw pal query PROJECT_ROOT --prompt "Confirm reachability." --text
promptclaw pal smoke PROJECT_ROOT
promptclaw pal baseline PROJECT_ROOT
promptclaw pal kb build PROJECT_ROOT
promptclaw pal kb build PROJECT_ROOT --max-chars 4000 --json
promptclaw pal kb query PROJECT_ROOT --query "router restart"
promptclaw pal kb query PROJECT_ROOT --query "router restart" --limit 3 --json
promptclaw pal diagnose slow-inference PROJECT_ROOT
promptclaw pal diagnose slow-inference PROJECT_ROOT --json
promptclaw pal validate restart PROJECT_ROOT
promptclaw pal validate restart PROJECT_ROOT --json
promptclaw pal audit shutdown PROJECT_ROOT
promptclaw pal audit shutdown PROJECT_ROOT --json
promptclaw pal deploy plan PROJECT_ROOT
promptclaw pal deploy plan PROJECT_ROOT --remote-inventory remote-inventory.json --json
promptclaw pal deploy apply PROJECT_ROOT --remote-inventory remote-inventory.json --approve-apply
promptclaw pal deploy apply PROJECT_ROOT --remote-inventory remote-inventory.json --approve-apply --json
promptclaw pal deploy rollback PROJECT_ROOT --remote-inventory remote-inventory.json --backup-id apply-20260516T000000Z --approve-rollback
promptclaw pal deploy rollback PROJECT_ROOT --remote-inventory remote-inventory.json --backup-id apply-20260516T000000Z --approve-rollback --json
promptclaw pal agent triage PROJECT_ROOT
promptclaw pal agent actions PROJECT_ROOT
promptclaw pal agent actions PROJECT_ROOT --approve inspect_logs_deep
```

The command reads the `pal` section from `promptclaw.json`, calls `/health` or
`/query`, and prints JSON unless `--text` is passed to `pal query`.
When `pal.enabled` is true, `promptclaw doctor PROJECT_ROOT` also checks router
health.

`pal smoke` runs a fixed restart validation suite: health check, reachability
prompt, configuration prompt, and operational-triage prompt. It records latency,
router timing metadata, responses, and any errors to
`.promptclaw/pal-smoke/pal-smoke-<timestamp>.json`.
`pal baseline` summarizes those saved smoke reports so stabilization runs can be
compared across restarts and days.

`pal kb build` reads local files from the configured `pal.knowledge_sources`
patterns, chunks them deterministically, and writes
`.promptclaw/pal-kb/index.jsonl`. The command does not call the PAL router. Use
`--max-chars` to adjust the chunk bound, `--output` to write a diagnostic index
elsewhere, and `--json` for a machine-readable build summary.

`pal kb query` reads the local JSONL index, ranks matching chunks
deterministically, and prints source paths, line ranges, scores, chunk ids, and
bounded snippets. It does not call the PAL router. Use `--limit` to bound the
number of matches, `--index` to point at a diagnostic index, and `--json` for a
machine-readable result list.

`pal agent triage` is the first bounded PAL agent workflow. PAL proposes a
diagnostic plan, PromptClaw executes only the local allow-listed tools
(`pal_health`, `pal_smoke_baseline`, `tailscale_status`, and optionally
`ssh_process_check` when `PAL_SSH_HOST`, `PAL_SSH_PORT`, and `PAL_SSH_KEY` are
set), then PAL summarizes the observations. The workflow writes a normal run
under `.promptclaw/runs/<run-id>/` and treats restarts, shutdowns, rental
changes, key changes, firewall edits, and config writes as human-approval gates.
Its plan and summary prompt artifacts include a bounded `Knowledge Context`
section from `.promptclaw/pal-kb/index.jsonl` when the local KB exists; missing
KB context is recorded as a non-blocking note.

`pal agent actions` adds the approval-gated action layer. It first gathers the
same read-only diagnostic context, asks PAL to propose fixed playbook actions,
and writes an action plan plus results into `.promptclaw/runs/<run-id>/`. By
default it executes no proposed actions. To execute an action, pass
`--approve ACTION_ID`; repeat the flag to approve more than one action. Action
plan and summary prompts carry the same bounded local `Knowledge Context`
section without changing what actions may execute.

The slow-inference context workflow currently exists as a read-only internal PAL
workflow primitive. It writes
`.promptclaw/runs/<run-id>/outputs/slow-inference-context.json` with health,
baseline token/s, optional GPU hints, and optional router/Ollama logs; PAL-019
adds the operator-facing diagnosis CLI.

`pal diagnose slow-inference` runs the same fixed read-only evidence collectors
and writes a diagnosis run under `.promptclaw/runs/<run-id>/`, including
`outputs/slow-inference-diagnosis.json`, route metadata, events, a summary, and a
handoff. The command derives local findings such as low saved token/s baseline,
log-observed throughput regression, non-green router health, or GPU saturation
when those signals are available. It exposes no action ids and records
`mutating_actions: []`; any restart, shutdown, rental, key, firewall, or config
change remains outside this command and requires a separate approval-gated
workflow.

`pal validate restart` runs the restart-validation workflow for post-restart or
post-boot checks. It actively calls router health, sends one fixed direct query,
runs and saves a fresh PAL smoke report, checks local Tailscale visibility, and
runs the fixed read-only SSH process check when PAL SSH variables are configured.
It writes `.promptclaw/runs/<run-id>/outputs/restart-validation.json`,
route/event/state artifacts, a handoff, and a final summary with
`workflow_id: restart_validation`, `validation_status`, the executed tool list,
and `mutating_actions: []`.

`pal audit shutdown` runs the shutdown-audit workflow. It uses one fixed
read-only SSH diagnostic to inspect `/opt/pal/config/shutdown.conf`, the cron
entry for `/opt/pal/scripts/auto_shutdown.sh`, the configured override flag, the
current local shutdown time context, and recent `/opt/pal/logs/shutdown.log`
lines. It writes `.promptclaw/runs/<run-id>/outputs/shutdown-audit.json`,
route/event/state artifacts, a handoff, and a final summary with
`workflow_id: shutdown_audit`, `audit_status`, `shutdown_enabled_state`,
`override_state`, `next_shutdown_window`, the executed tool list, and
`mutating_actions: []`. Missing SSH diagnostics are recorded as unknown state
instead of prompting for credentials or changing shutdown behavior.

`pal report phase2-readiness` runs the Phase 2 readiness report workflow. It
uses fixed read-only diagnostics for PAL health, saved smoke baselines, shutdown
safety, local runbook/session-state evidence, and the Vast connector boundary.
It writes `.promptclaw/runs/<run-id>/outputs/phase2-readiness.json`,
route/event/state artifacts, a handoff, and a final summary with
`workflow_id: phase2_readiness_report`, per-prerequisite scores,
`overall_score`, `readiness_status`, the executed tool list,
`mutating_actions: []`, and `phase2_execution_actions: []`. The command has no
`--approve` flag and cannot rent, start, stop, destroy, resize, migrate, or load
Phase 2 hardware/model work.

`pal deploy plan` prints a dry-run deployment plan for the repo-managed PAL
manifest. The default manifest is `PROJECT_ROOT/ops/deployment-manifest.json`,
which lists intended `/opt/pal` files for the host-managed Phase 1 runtime,
including startup scripts, the router app, shutdown config/script, deployment
info, and Docker fallback files. By default the command compares against an
empty remote snapshot; `--remote-inventory PATH` can point at a local JSON
snapshot for deterministic diagnostics without SSH. Human output shows summary
counts, planned file changes, unmanaged remote files, and service impacts.
`--json` includes the same diff data plus `dry_run: true` and
`remote_writes: false`. The command writes no run artifact, performs no SSH
writes, and exposes no apply, approval, restart, backup, or rollback flag.

`pal deploy apply` is the approval-gated fake-remote apply path. It requires
`--remote-inventory PATH --approve-apply`; without that approval flag it returns
nonzero and does not create backups or mutate the snapshot. With approval, it
loads the manifest and local fake remote inventory, backs up changed managed
remote file content under `.promptclaw/pal-deploy/backups/<backup-id>/`, writes
added and changed managed files into the supplied inventory JSON, preserves
unmanaged files, and reports missing local source files as skipped. JSON output
uses `workflow_id: pal_deploy_apply`, `approved: true`,
`remote_transport: fake-remote-inventory`, `remote_writes: true`,
`live_ssh: false`, and `service_restarts: false`. This command does not perform
live SSH deployment, rollback, or service restarts.

`pal deploy rollback` is the approval-gated fake-remote rollback path. It
requires `--remote-inventory PATH --backup-id ID --approve-rollback`; without
that approval flag it returns nonzero and does not mutate the snapshot. With
approval, it loads
`.promptclaw/pal-deploy/backups/<backup-id>/backup-manifest.json`, restores the
backed-up managed files and metadata into the supplied inventory JSON, and
preserves unmanaged entries. JSON output uses `workflow_id:
pal_deploy_rollback`, `approved: true`,
`remote_transport: fake-remote-inventory`, `remote_writes: true`,
`live_ssh: false`, and `service_restarts: false`. This command does not perform
live SSH rollback or service restarts.

Current action ids:

- `rerun_smoke`: run the PAL smoke suite and save a fresh local report
- `inspect_logs_deep`: run a fixed read-only SSH log/resource inspection
- `restart_router`: restart only the PAL FastAPI router service
- `pause_shutdown_once`: create `/opt/pal/config/override.flag`
- `resume_shutdown`: remove `/opt/pal/config/override.flag`

The Vast connector is a stub boundary, not a cloud lifecycle client. It records
`rent`, `destroy`, `start`, and `stop` as blocked lifecycle operations with no
default callable action ids, so those operations cannot be invoked through
`pal agent actions` unless future work explicitly adds a tested action.

Unknown proposed actions and unknown approvals are ignored and recorded.

## CypherClaw runtime utilities

These are repo-managed operational tools for the live CypherClaw home:

```bash
bash my-claw/tools/init_workdir.sh
python my-claw/tools/preflight.py --project-root .
python my-claw/tools/runtime_checkpoint.py --project-root .
python my-claw/tools/maintenance_mode.py --project-root . enter --reason "planned reboot" --actor anthony --allow-runner-stop
bash my-claw/tools/safe_reboot.sh prepare --actor anthony
bash my-claw/tools/safe_reboot.sh resume --checkpoint .sdp/recovery/checkpoint-<stamp>.json --actor anthony
```

`maintenance_mode.py enter` now writes the canonical authority flag at `.sdp/MAINTENANCE`. If the queue currently has a running task or an active runner process, direct maintenance entry refuses unless `--allow-runner-stop` is passed. `safe_reboot.sh prepare` uses that explicit override automatically.

`my-claw/tools/telegram.py` suppresses sends automatically while `pytest` or `PROMPTCLAW_TEST_MODE` is active, and also when the helper is running from the tmpfs task-run workdir under `/run/cypherclaw-tmp/workdir/`. Set `PROMPTCLAW_ALLOW_LIVE_TELEGRAM=1` only when you intentionally want a test or drill to hit the real bot.

Systemd units shipped with this repo:

- `my-claw/systemd/cypherclaw-bootstrap.service`
- `my-claw/systemd/cypherclaw-sdp-runner.service`

The runner unit is intended to be long-lived. It uses `Restart=always` so a clean `sdp-cli run` exit immediately re-enters the queue loop, while maintenance-gated launcher exits use code `75` and are treated as successful non-restarting stops.
The launcher also prefers a sibling `sdp-cli/src` checkout when one exists, exporting it through `PYTHONPATH` automatically unless an operator override is already present.
Narrative API ASGI startup also bootstraps identity when `cypherclaw.narrative_api.main:app` is imported, so service managers that target the module-level app get the same first-boot persistence guarantee as `python -m cypherclaw.narrative_api`.
In the live music runtime, tracker solo orchestration also now selects a named house patch per song. Normal listening states bias toward western-compatible `bowed` / `pluck` / `choir` / `breath` ensembles, and the selected patch also changes melody contour, bass vocabulary, dynamics, and register spread. Older inharmonic `bell` / `metal` playback is retired to tuned runtime substitutes.

Daemon status utility:

```bash
python my-claw/tools/cypherclaw_daemon.py --status
```

This probe is platform-aware: it checks `launchctl` on macOS homes and `systemctl` on Linux homes so status checks do not crash when the local service manager is absent.

Contact-mic calibration utility:

```bash
python my-claw/tools/contact_mic_calibration.py list-devices
python my-claw/tools/contact_mic_calibration.py run --device hw:0,0
python my-claw/tools/contact_mic_calibration.py analyze artifacts/contact-mic-calibration/<session>/quiet_ambient_180s.wav
```

`contact_mic_calibration.py run` captures the baseline contact-mic scenarios, writes one WAV plus one JSON analysis per scenario, and emits a `summary.json` bundle for the whole session. If `--device` is omitted, the tool tries to auto-select the Scarlett 4i4 ALSA device.

Tracker-solo runtime note:

- In live CypherClaw music mode, `/tmp/tracker_runtime_state.json` reflects the active tracker scene and row.
- Tracker solo now derives lane voices from the current active character cast and enforces a quiet foundation lane through `Theme`, `Development`, and `Recap` even during subdued moods.
- T-045c scene playback now also routes profiled voices through the mood-space resolver: tracker events carry `render_space_voice`, `render_space_id`, and `render_fx_bus_id`, and house-bound mode resolves house context from explicit `active_house` or the scene `patch_name` fallback. No new dependencies or database migration are required for this runtime path.
- `/tmp/midi_keyboard_state.json` is also now the live keyboard-grimoire contract: it records notes, sustain/expression state, harmonic suggestions, and modulation intent for the composer.
- Live score generation is now motif-driven too: `score_from_mood()` is seeded by song number, tracker family, cadence state, and recent melodic-memory fragments so similar moods can still produce different melodic and rhythmic cells across songs while occasionally recalling transformed motifs. It also rotates comping styles, so the accompaniment line does not keep repeating one default root-walk figure.
- The live songwriter stack is now present end to end: `reharmonizer.py` supplies section functions and cadence types, `hook_engine.py` adds deterministic titles/hooks/phrase-pairs, `arrangement_engine.py` shapes scene-level groove and density, `practice_curriculum.py` chooses the current away-mode lab, `ear_engine.py` scores performed notes at the end of each song, and `repertoire_memory.py` stores promoted song-level memories instead of only short fragments.
- The tracker is no longer the only place a song is formed. `piece_commission.py`, `piece_brief.py`, `form_grammar.py`, `recursive_composer.py`, `composition_gate.py`, and `tracker_compiler.py` now form a score-tree composition layer above tracker playback. In practice this means the live runtime can commit to a form class, composition mode, section budgets, narrative beats, and ending family before it compiles scenes.
- That commission layer now protects runtime recovery too. On a fresh restart, the first commissioned piece is biased away from the most diffuse `suite` case unless the cadence is already explicitly late-night or sleep-oriented, so the room hears a committed piece quickly instead of a nearly silent maximal-form intro.
- Long compiled sections now keep note motion too. `tracker_compiler.py` converts large section budgets into phrase repeats plus small duration scaling, and `music_tracker.py` records that repeat count in scene metadata, so long pieces no longer collapse into a handful of over-stretched sustain events.
- Section compilation is now scene-specific rather than one-score-for-all. `tracker_compiler.py` derives a fresh score per section, re-enriches it for tracker floors, and applies section-function plus motif transforms before `music_tracker.py` quantizes it, so long pieces can move from statement to development to recap without merely looping the same phrase at a different density.
- Longer sections now contain coordinated internal phrase families too. Tracker steps can carry `internal_phrase_family`, `internal_family_root_degree`, and `internal_family_function` metadata (`A`, `A_prime`, `B`, etc.), which lets development sections unfold recursively while bass, counter, texture, and melody share the same harmonic-function profile before repeat-cycle variation extends them.
- Section endings now carry transition authorship. Non-final scenes expose `transition_target_scene`, `transition_target_function`, `transition_target_root_degree`, and `transition_motion`, and final-cycle tail steps add `transition_role=preparation` so diagnostics can see how the current section is aiming at the next one.
- Long repeated scenes can stage lane entrances and exits. Lane metadata may include `entry_cycle` and `exit_cycle`; in development-style sections, bass/melody usually begin on cycle 0 while counter/color support arrives later.
- Recalled motif lanes preserve current transition targets. If a later scene borrows from `Theme`, its final recalled tail uses that later scene's own `transition_target_*` metadata rather than the source scene's transition.
- Compiled score-tree scenes now expose motif and progression authorship. Scene metadata can include `motif_development` and `section_progression`; note steps can include `section_progression_root`, `section_progression_index`, and `section_progression_role` so bass/counter/color can be checked against the section-local harmonic plan.
- Compiled score-tree scenes also expose composer-planned `meter_trajectory_*` metadata from `MeterTrajectory`, including a JSON `meter_trajectory_entry` for the scene's planned meter value. Generic tracker scene emission can derive those same per-scene keys from the compact trajectory payload. If a plan crosses from `Crystallization` into a new `Divination` arc cycle, phase drift restarts before those metadata keys are emitted. These keys describe the arc-phase meter path and each scene's intended meter but remain informational until later runtime slices consume them.
- Compiled scenes also expose rhythmic authorship. Scene/lane/step metadata can include `rhythm_development` plus `rhythm_cell`, with `Development` using syncopated fragments, `Bridge` using half-time displacement, and late sections thinning into slowdown or residue patterns.
- Motif-recalled steps are rewritten with the current scene's rhythm/progression metadata, so a recalled `Recap` lane reports `recall_groove` rather than the source `Theme`'s `steady_statement`.
- Approved score trees can be queued at `/home/user/cypherclaw-data/state/piece_queue.json`, so the current piece can play while the next piece already exists as a committed structure instead of being improvised from nothing at handoff time.
- `repertoire_memory.py` now stores structural recall as well as surface recall. Completed score-tree pieces carry a `score_tree_summary` with motif ids, section functions, narrative beats, form class, composition mode, and ending family, which future songs can use when they need form memory instead of only title/hook memory.
- `repertoire_memory.py` now also supplies forward-looking influence, not only archival hints. In tracker solo mode, the next song can inherit a prior strong song's progression profile, bias title/hook generation toward recall or answer behavior, and optionally borrow a preferred form variant, a section-density bias, and a payoff-scene emphasis when the family and cadence context match.
- `hook_engine.py` now answers remembered hook lines with phrase-level transforms such as `keep the line open -> leave the line open` and `answer the room -> keep the room open`, instead of the older generic suffix fallback that could create awkward language. Those answer transforms are now contextual too, so the same remembered line can resolve to a few grammatical variants depending on family, cadence, and song context rather than always producing the same literal reply.
- `prosody_engine.py` now makes scene captions section-aware. The same hook can appear as a direct line in `Theme`, a reflective answer in `Recap`/`Release`, and a thinner after-image in `Resolution`/`Afterglow`, which keeps the face text aligned with the musical arc instead of repeating one caption verbatim through the whole song.
- `prosody_engine.py` now also uses `cadence_type` for `Resolution` and `Afterglow`, so the same hook can end as `line still reaching`, `line settling open`, `room at rest`, or `room turned aside` depending on the harmonic landing rather than only the scene label.
- `prosody_engine.py` now also uses `patch_name` and lane count for early-scene captions. Sparse monastery/chamber scenes can compress a hook like `keep the line open` into `line open`, while dense workshop/procession scenes can widen a hook like `keep the room open` into `keep the whole room open`.
- `hook_engine.py` now normalizes a small set of rough historical hook phrases before they can propagate through new songs. Phrases like `carry the line wide` and `open the room open` are repaired back into the current house vocabulary before answer/recall logic uses them.
- `hook_engine.py` now also ties title modifiers and nouns to the hook image field, cadence state, progression profile, and hook type. If the live hook points at `light`, `line`, `room`, `wire`, or `pattern`, the title phrase is pulled from that same field and weighted by the current musical state instead of mixing a coherent hook with a generic cadence noun or an unrelated adjective.
- `voice_shaping.py` now emits best-effort `highpass_hz` and `saturation_mix` controls for very high notes, and `play_voice()` forwards them alongside the existing top-octave gain/brightness/detune shaping. The same shaping layer also folds the highest live octave down by one octave before the synth is triggered.
- The EMSD package now also exists in code, not just in notes: `my-claw/curriculum/` contains a full course catalog and scaffold generator, and the new production-side helpers are `sound_palette_lab.py`, `sample_lab.py`, `mix_engine.py`, `procedural_arc.py`, `dsp_scene_lab.py`, `artistic_identity.py`, and `capstone_engine.py`.
- `emsd_runtime.py` now turns those EMSD helpers into live song context. In tracker solo mode, the composer can derive arc phase, mix targets, sampling intent, DSP blocks, and artistic-identity fields from the current cadence/family/patch/repertoire situation and publish them into `/tmp/composer_state.json`.
- `emsd_performance.py` now turns that same EMSD context into live render adjustments. Tracker playback can use the active mix profile, sample source, sample transforms, and DSP block list to change note level, release, brightness, delay, detune, filtering, and drive instead of leaving the EMSD layer as metadata only.
- `self_listener.py` now also writes `/tmp/glyph_audio_features.json`, combining live audio analysis with `/tmp/composer_state.json` and `/tmp/cadence_state.json` so visual consumers can read brightness, motion, density, sample source, DSP blocks, and arc phase from one fresh file.
- `self_listener.py` now also writes `/tmp/sample_dsp_activity.json`, a concrete EMSD sampler/DSP plan derived from the current composer state, cadence state, listener captures, and sensor triggers. It reports whether the selected sample source is fresh, whether it should trigger now, and what activity mode, wetness, grain density, stretch, filter, and reversal settings are appropriate.
- `sample_dsp_activity.py` now also resolves unavailable requested sample sources onto fresh fallback captures when possible. If a scene asks for `garden_mic` on a box with no live garden capture, the activity file can fall back to `room_mic`, `contact_mic`, or `self_bus` instead of publishing a permanently dead source.
- If Theramini input is requested but no Theramini capture exists, the sampler now prefers fresh `contact_mic` and `room_mic` captures before falling back to `self_bus`, so a quiet self monitor does not become the default source for missing external audio.
- `sample_playback_engine.py` now turns that plan into actual audio. It renders short WAV events from the resolved capture source, plays them through PipeWire with `pw-play`, refreshes stable ambient beds after cooldown, and writes `/tmp/sample_playback_state.json` with the live playback decision and output path.
- Heavy sample-render output now prefers the archive disk too. `sample_playback_engine.py` resolves its render directory through the shared archive-root helper, so on CypherClaw it writes event WAVs to `/mnt/archive/cypherclaw/sample_events` instead of growing `/tmp/cypherclaw_sample_events` on the root filesystem.
- `sample_dsp_activity.py` now also emits scene-level render hints like `scene_profile`, `render_duration_s`, and `peak_target`. The renderer uses those to make `Development`, `Recap`, `Resolution`, and `Afterglow` room-sampling behavior materially different instead of only switching among generic effect labels.
- The EMSD capstone and DSP planners now prefer `room_mic` as the default Divination/ambient source on CypherClaw. `garden_mic` remains available for explicit use, but it is no longer the baseline assumption for the live installation.
- The late EMSD arc now prefers `room_mic` too in lived-in states. `Convergence` and `Crystallization` only stay on `self_bus` by default during `away_practice`; otherwise the planner will steer those sparse late phases back toward the room so CypherClaw keeps composing with the space instead of reflexively remixing itself.
- `room_listener.py` now reports `capture_backend` and `capture_source` in `/tmp/room_speech.json` when capture succeeds, and the boot script now starts it without `--no-jack` so the Perform-VE path gets first priority before ALSA fallback.
- `room_listener.py` now prefers a PipeWire `pw-record` target for Perform-VE before trying JACK or ALSA directly. On this hardware that is the most reliable way to make the Perform-VE audio device usable from Linux userland.
- The ALSA fallback order inside `room_listener.py` now prefers the Perform-VE interface over webcam or generic analog capture, so even a JACK miss still lands on the condenser path by default.
- `room_listener.py` now retries alternate ALSA sample formats per device before moving on, which lets interfaces with stricter format requirements stay in play instead of being rejected after one `S16_LE` failure.
- The live listeners now keep stable capture aliases at `/tmp/room_capture.wav`, `/tmp/contact_capture.wav`, `/tmp/theramini_capture.wav`, and `/tmp/self_capture.wav`, so EMSD sampling and later archive/remix passes can read durable paths instead of volatile per-cycle clip files.
- `start_audio.sh` now links the repo SynthDef bundle into `~/.local/share/SuperCollider/synthdefs`, starts `scsynth` with `-D 1`, prefers a real JACK/Scarlett graph when one is already available, and only falls back to `pw-jack` when that graph is absent. If the real-JACK launch fails to expose `SuperCollider:out_1`, it now kills that failed server and retries on `pw-jack` automatically. When it has to rebuild real JACK, it relaunches `jackdbus` and configures ALSA `hw:USB` so Scarlett can come back as the monitor path.
- `restart_composer.sh` now assumes the audio server is a dependency instead of rebuilding it indirectly: it restarts the composer with a graceful `TERM` first, reseeds the `sw_master_smooth` node, verifies the new PID with `kill -0`, and only calls `start_audio.sh` when `scsynth` is actually missing.
- `restart_composer.sh` now also performs a second non-destructive `sw_master_smooth` seed after the new composer PID is confirmed alive. That compensates for the composer's startup `/g_freeAll`, which would otherwise leave early scene-level master-bus `/n_set` traffic writing to a dead node.
- `music_tracker_runtime.py` now keeps a hotter live floor for primary roles. Melody, bass, and rhythm lanes leave the tracker runtime with stronger safe amplitudes than the earlier sketch-era defaults, so a healthy running song is more likely to clear the monitor path without waiting for a late dense section.
- That live floor is now better balanced too. Texture lanes no longer vanish into the floor, and EMSD note-level gain shaping uses a gentler scaling curve so the live bass/melody path is less likely to feel pinned and top-heavy during ordinary daytime pieces.
- `self_listener.py` still supports PipeWire and `pw-jack` fallback capture, but `cypherclaw_av_boot.sh` now pins it to the verified JACK monitor path on the live host. It still publishes `capture_backend` in `/tmp/self_listen.json`, keeps `JACK_NO_START_SERVER=1` on its JACK probes, caches the last known-good fallback backend so a slow direct-JACK probe right after boot does not falsely fall back to `pw-jack`, and runs child recorders with discarded output so the live meter loop cannot stall behind a full subprocess pipe. If the direct recorder still times out, the listener now falls back to a fresh `/tmp/room_capture.wav` clip so glyph and sampler state can stay audio-derived instead of dropping to a dark monitor error.
- `restart_composer.sh` now waits for a healthy steady-state `duet_composer.py` process instead of only validating the first short-lived child PID returned by `nohup`, which avoids false failure reports during the current live startup race. It also launches the composer with `nohup setsid ... </dev/null` so operator SSH teardown does not kill the live music process.
- `cypherclaw_av_boot.sh` is the cold-boot wrapper for the live AV stack. It restarts the audio server and composer only when the core stack is still missing, waits for `SuperCollider:out_1`, relaunches `self_listener.py` under a detached session with the verified JACK backend and `SuperCollider:out_1` port pinned, force-restarts `face_display.py` and `gallery_x11.py` under X with `DISPLAY=:0` and `XDG_RUNTIME_DIR=/run/user/1000`, and deduplicates/backfills `room_listener.py` and `sample_playback_engine.py` so old bad boot loops and late-start hooks do not leave multiple live copies behind.
- That AV wrapper now also normalizes the live X layout after recovery: it sets screen 0 `DP-2` to `1280x1024`, screen 1 `DP-0` to `3840x2160`, launches `face_display.py` on `:0.0`, and launches `gallery_x11.py` on `:0.1`. `gallery/gallery_x11.py` no longer hardcodes a combined-desktop offset when it is running on `:0.1`, so the 4K gallery can fill the second screen instead of starting half off-screen.
- `cypherclaw_boot.sh` now delegates core audio/composer/face/gallery/room-listener/sample ownership to `cypherclaw_av_boot.sh` instead of starting those daemons directly itself.
- `cypherclaw_boot.sh` now also treats the local webcam as a singleton resource: it deduplicates `observer_vision.py`, starts it explicitly on `/dev/video0`, and starts `room_presence_daemon.py --observer-frame-only` so room presence can reuse the shared observer frame instead of fighting the same webcam.
- `cypherclaw_boot.sh` now also starts `cypherclaw-observer-ollama.service` and launches `observer_vision.py` with `OBSERVER_OLLAMA_URLS=http://127.0.0.1:11435/api/chat,http://127.0.0.1:11434/api/chat`, so the camera summary path uses a dedicated observer queue first and only falls back to the shared local model queue if needed.
- `cypherclaw_boot.sh` now resolves an archive root before starting the long-lived capture daemons. On hosts with the 10TB archive volume mounted, porch and side camera capture rings now default under `/mnt/archive/cypherclaw/camera/` and the archive daemon inherits the same `CYPHERCLAW_ARCHIVE_ROOT`, `CYPHERCLAW_PORCH_CAPTURE_DIR`, and `CYPHERCLAW_SIDE_CAPTURE_DIR` environment so captures and archived media stay on the big disk.
- `my-claw/systemd/cypherclaw-av-stack.service` binds that wrapper to `graphical.target` as `User=user`, so the music and face stack can come back after reboot without an operator SSH session.
- `face_display.py` now reads `/tmp/sample_dsp_activity.json` too, so the head monitor can show a short sampler status line like `holding room mic · freeze bed` or `sampling theramini in via self bus · grain cloud`.
- `face_display.py` now also reads `/tmp/sample_playback_state.json`, so when the sampler is actually sounding you can see a playback-truth line such as `playing room mic · freeze bed` rather than only the plan.
- `face_display.py` now also checks `/tmp/self_listen.json` for sample-layer truth, so if playback claims activity while the monitor path is down the face can surface `monitor offline` instead of confidently reporting a false sounding state.
- `observer_vision.py` now records `video_device` in `/tmp/observer_state.json` and only treats a capture as fresh when `ffmpeg` succeeds. If the webcam wedges, the state now flips to `ok: false` instead of silently reusing the last JPEG.
- `observer_vision.py` now also exposes `vision_backend` and `vision_error` in `/tmp/observer_state.json`. It will try the ordered `OBSERVER_OLLAMA_URLS` endpoints in sequence, fail over from `11435` to `11434` when the dedicated queue is busy or unavailable, and only then fall back to a short local scene summary with backoff instead of publishing the raw `HTTP Error 503` text as its description.
- `room_presence_daemon.py` now has `--observer-frame-only` for single-camera installs. In that mode it reads `/tmp/observer_frame.jpg`, mirrors that image into `/tmp/room_frame.jpg`, and reports `capture_source: "observer_frame"` in `/tmp/room_presence.json`, which keeps the presence layer and archive consumers alive without racing the observer process for `/dev/video0`.
- `sample_dsp_activity.py` now emits `transport_trigger_now` and `transport_trigger_key`, and `sample_playback_engine.py` consumes those to launch sample events once per tracker bucket instead of only free-running on wall-clock cooldowns.
- `master_bus.py` now translates EMSD `mix_*` fields plus tracker-scene automation like `master_amp` and `reverb_send` into live `sw_master_smooth` `/n_set` updates, so scene starts affect the real summed bus as well as per-note shaping.
- Tracker automation is now row-aware too: `/tmp/tracker_runtime_state.json` includes current interpolated `automation` values, the scheduler uses low `density` to thin optional color/counter events, and `duet_composer.py` refreshes `sw_master_smooth` from those values at musical row intervals so section curves continue after scene start.
- `repertoire_memory.py` now repairs known legacy broken hook text when it loads or stores songs. That prevents older artifacts like `answer the again` from propagating through current repertoire influence after the hook system has been improved.
- Tracker melody recall is now family-aware as well: the live learner tags songs with tracker family, progression profile, cadence state, and house patch, `MelodicMemory` can filter stored fragments by those keywords, and the next song can prefer same-family/profile motifs instead of pulling only from an undifferentiated recent pool.
- Tracker form memory is now scene-aware too: `Recap` and concise-form `Release` can reuse `Theme` lane shapes with an answering transform, and they annotate that provenance in scene/lane metadata so later tooling can correlate what was recalled.
- Tracker form selection is also song-aware now: `tracker_form_for_family(..., song_num=...)` can return bridge, concise, or afterglow variants instead of one fixed five-scene template, and per-patch register metadata keeps bass lower while widening the melodic/color spread.
- Family and harmony selection are now day-phase-aware too: `resolve_tracker_plan()` rotates through cadence/day/week family palettes and emits a `progression_profile` that `score_from_mood()` uses to choose different progression banks for `awakening`, `open_day`, `lift`, `settling`, and `experiment` states.
- The cast planner now keeps at least one support-role character in low-energy songs, and tracker playback preserves explicit cast synths like metal and tabla when they fit the lane role; quiet texture lanes still normalize overly ringing `pad`/`metal`/`bell` hints to safer sustained voices, `wind_down` scenes also soften chirpy `pluck`/`kotekan`/`grain` choices before playback, the current live runtime quarantines tracker `grain` to `breath` until the underlying SynthDef is fixed, and missing `tabla_ge` playback is temporarily aliased to `tabla_tin`.
- Runtime `gong` playback is currently aliased to `bowed` on CypherClaw because the previous gong body was too inharmonic to sit inside the installation's western/modal pitch framework.
- The live playback path also applies gentle high-note saturation shaping. Because the current synths do not expose a true drive control, very high notes are softened by reducing brightness, trimming gain/release slightly, and adding a touch more detune/space instead of sending unsupported synth args.
- The top register is now folded more aggressively too. Notes above roughly `C6` are pulled down an octave, and the sharpest top band is pulled down two octaves, which fixes the earlier case where some bright instruments were still too high even after the first fold-down pass.
- `/tmp/composer_state.json` now also carries song-level metadata like `song_title`, `text_hook`, `practice_block`, `scene_caption`, and `reharm_strategy`, so face and operator surfaces can present the current song as a musical object instead of only a key and movement label.
- `/tmp/composer_state.json` now also carries EMSD production metadata like `arc_phase`, `mix_target_lufs`, `sample_source`, `sample_transforms`, `dsp_blocks`, `glyph_visual_bias`, and artistic-identity fields, which makes it the authority file for both face text and downstream visual/reactive systems.

## CypherClaw Telegram built-ins

The live CypherClaw daemon also exposes built-in Telegram commands for operator status without routing through an LLM.

- `/monitor` now prefers the real `sdp-cli monitor --last` snapshot when that CLI path is available in the live home, so Telegram reflects the same run, phase, timing, quota, and risk fields the operator sees in the terminal monitor.
- If that CLI snapshot is unavailable, `/monitor` falls back to the daemon's queue-backed summary from the authority queue DB.
- `/quota` shows provider headroom, active agents, and exclusions from quota-aware routing.
- `/prd` shows the ordered PRD roadmap as it will be implemented, using the live `.sdp/state.db` queue plus the roadmap defined in `sdp/execution-roadmap.md` instead of cached prose summaries.
- `/tasks` shows actionable queue work from the authority queue DB instead of the daemon's internal background-thread list. The default view groups running work, next root tasks, needs-split work, and attention items; filtered views like `/tasks pending 10`, `/tasks needs_split`, `/tasks attention`, `/tasks frozen`, and `/tasks all 20` provide deeper slices. Roadmap-aware views like `/tasks prd 6` and `/tasks stage clone and home creation` let operators inspect one implementation stage at a time.

`/monitor`, `/prd`, and `/tasks` are queue-backed and dependency-aware. They reflect the authority SQLite queue instead of routed prose summaries. Their totals use one canonical rubric: count all live executable tasks and exclude only split parents. Split parents are still surfaced as `skipped` in status breakdowns so decomposition remains visible without inflating completion percentages.

`/monitor` should list `pending`, `needs split`, `blocked`, `running`, and `skipped` as separate buckets when present. If the queue DB contains stale open task-run records or a running task without a matching open run, `/monitor` should include a `State: drift` line so the operator sees the inconsistency immediately.

Separately from slash commands, the live daemon now sends a scheduled half-hour heartbeat at `:00` and `:30`. That heartbeat includes uptime, I/O wait, memory, load, available agents, queue progress, and pet XP summary, and it is logged to Observatory.

`/status` also includes SenseWeave operator diagnostics from `my-claw/tools/senseweave/operator_diagnostics.py`. The block names the current score tree, section function, arrangement curve, ear metrics, sample source, master bus, self-listener, and the rollout flag states loaded by `my-claw/tools/senseweave/rollout_controls.py`. The flags are `CYPHERCLAW_ENABLE_CURRICULUM_EXERCISE`, `CYPHERCLAW_ENABLE_PREVIEW_RENDER`, `CYPHERCLAW_ENABLE_SELF_CRITIQUE`, and `CYPHERCLAW_ENABLE_LONG_FORM_SUITE`.

`/prd` reads its stage order from `sdp/execution-roadmap.md` and its batch-to-stage mapping from `sdp/execution-roadmap.queue-map.json`, so Telegram roadmap output stays aligned with the current queue-fit PRD family instead of a stale hardcoded list. Stages with only frozen work are labeled `frozen`, stages with only split parents are labeled `decomposed`, and `not loaded` is reserved for stages that truly have no queue work loaded.

`/tasks` should be operator-first rather than exhaustive by default. The root/default view should prioritize active work and the next actionable queue slices, while deeper filtered views can expose frozen, decomposed, or mixed-status task lists without forcing the operator to read raw SQL-shaped output. Stage-scoped views should resolve against the same roadmap and batch map that power `/prd`, so `/tasks prd <n>` and `/tasks stage <name>` stay aligned with the live implementation order.
