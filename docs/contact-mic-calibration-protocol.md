# Contact Mic Calibration Protocol

## Purpose

This protocol defines how PromptClaw should evaluate and calibrate the two initial piezo contact-mic voices on the Scarlett 4i4:

- `Line 1`: window piezo, `The Membrane`
- `Line 2`: case piezo cluster, `The Heartbeat`

These channels are not treated like conventional room microphones. They are structural/vibration sensors and should be calibrated for:

- stability
- distinctiveness
- repeatability
- useful response to environmental or machine-state changes

## Harness

The repo now ships a guided capture harness for this protocol:

```bash
python my-claw/tools/contact_mic_calibration.py list-devices
python my-claw/tools/contact_mic_calibration.py run --device hw:0,0 --output-dir artifacts/contact-mic-calibration/session-001
python my-claw/tools/contact_mic_calibration.py analyze artifacts/contact-mic-calibration/session-001/quiet_ambient_180s.wav
```

Notes:

- `run` records the baseline scenario set by default
- one WAV and one JSON report are written per scenario
- `summary.json` collects the full session bundle
- if `--device` is omitted, the harness tries to auto-select the Scarlett ALSA device

## Current Interpretation

Based on the April 2, 2026 live captures:

- `Line 1` is a subtle structural/environmental sensor
- `Line 2` is a strong machine-state / chassis-resonance sensor

The calibration goal is not "make both channels loud." The goal is "make both channels reliably meaningful."

## Capture Settings

Use these defaults for all baseline captures unless there is a reason to override them:

- interface: `Scarlett 4i4 USB`
- channels: `2`
- sample rate: `44100`
- dtype: `float32`
- analysis window: `1.0s`

For long captures:

- duration: `180s`

For directed-event captures:

- duration: `60s`

## Required Calibration Scenarios

### 1. Quiet Ambient

Duration: `180s`

Conditions:

- no intentional interaction
- no deliberate tapping or scratching
- normal room and server state

Purpose:

- establish the noise floor and passive baseline for both voices

### 2. Bass / Structural Excitation

Duration: `180s`

Conditions:

- deep bass music in the room
- no tapping on the sensors

Purpose:

- determine whether the window piezo responds to structural/environmental energy
- determine whether the case piezo is dominated by machine hum or responds to room energy too

### 3. Directed Events

Duration: `60s`

Structure:

- `0s-20s`: tap/scratch only the window/glass path
- `20s-40s`: tap/scratch only the case/chassis path
- `40s-60s`: silence

Purpose:

- verify channel identity
- confirm transient sensitivity
- confirm cross-talk is acceptable

### 4. Machine Load Change

Duration: `180s`

Structure:

- `0s-60s`: idle baseline
- `60s-120s`: apply repeatable machine load
- `120s-180s`: return to idle

Suggested load:

- local render
- CPU-heavy test
- controlled multi-second benchmark task

Purpose:

- determine whether `Line 2` tracks machine activity meaningfully

### 5. Optional DI / Input-Path A/B

Run the same `Quiet Ambient` and `Directed Events` scenarios twice:

- once direct to Scarlett
- once through the DI or alternate input path

Purpose:

- compare signal level
- compare noise floor
- compare transient clarity

This is especially important for `Line 1`.

## Metrics

Record these per channel for every capture:

- `median_rms`
- `p95_rms`
- `p99_rms`
- `median_peak`
- `max_peak`
- `active_windows`
  - count of 1-second windows where `rms > median_rms * 1.5`
- `activation_ratio`
  - `p95_rms / median_rms`

### Recommended Additional Metrics

These should be added once spectral analysis is available:

- `low_band_rms`
  - `20-120 Hz`
- `low_mid_rms`
  - `120-600 Hz`
- `high_band_rms`
  - `600+ Hz`
- `spectral_centroid`
- `dominant_band`
- `transient_density`

These matter because useful contact-mic behavior is often spectral rather than simply louder/quieter.

## Usefulness Criteria

### Line 1: Window Piezo

Treat `Line 1` as useful if it satisfies at least one of these:

- `Bass / Structural Excitation` shows `median_rms >= 5x` the `Quiet Ambient` median
- `Directed Events` window phase produces clearly higher peaks than the silent phase
- spectral analysis shows a stable low-frequency or broadband structural response pattern distinct from noise

Treat `Line 1` as production-ready if it satisfies two or more.

### Line 2: Case Piezo

Treat `Line 2` as useful if it satisfies at least one of these:

- strong stable ambient baseline above the channel noise floor
- `Machine Load Change` produces measurable movement in RMS or spectral content between idle and load
- directed case taps produce clear transient spikes without clipping

Treat `Line 2` as production-ready if it satisfies two or more.

## Current Status

Using the live captures from April 2, 2026:

- `Line 1` passed structural response under bass excitation
- `Line 1` did not show a strong passive ambient signal
- `Line 2` passed stable machine-state sensing
- `Line 2` appeared mostly dominated by constant chassis/self-noise during passive ambient listening

Current recommendation:

- `Line 1`: keep as an environmental/structural voice, but continue calibration
- `Line 2`: use now as the machine heartbeat/self-listening voice

## Gain / Routing Guidance

- Do not optimize gain only for loudness.
- Set gain using directed-event peaks, not passive ambient noise.
- Avoid clipping during directed taps.
- If a channel is only useful at extreme gain and becomes noisy, test a different path:
  - DI
  - alternate preamp mode
  - better physical coupling

## Channel-Specific Notes

### The Membrane (`Line 1`)

Primary signals:

- window resonance
- structural vibration
- weather/traffic/bass coupling

Good features to map:

- slow environmental intensity
- low-frequency motion
- transient structural events

### The Heartbeat (`Line 2`)

Primary signals:

- fan vibration
- chassis resonance
- machine hum
- load-related vibration changes

Good features to map:

- background organism pulse
- machine-state energy
- self-listening layer

## Repeatability Rules

Re-run the calibration set whenever any of these change:

- mic mounting position
- gain staging
- DI/preamp routing
- Scarlett input mode
- computer case orientation
- speaker/sub placement near the window

Store every run with:

- date/time
- scenario
- gain and routing notes
- channel assignments
- environmental notes
- summary verdict

## Verdict States

Each channel should be assigned one of:

- `production`
- `usable`
- `experimental`
- `not useful`

Current default verdict:

- `Line 1`: `usable`
- `Line 2`: `production`

## Proceed Criteria

PromptClaw may proceed with contact-mic integration when:

- `Line 2` remains at least `usable`
- `Line 1` is at least `usable` or is explicitly marked experimental but still retained
- channel identity is verified in the `Directed Events` scenario
- no calibration capture shows obvious clipping or complete dropout

## Immediate Next Step

Implement one repeatable capture harness that can run:

- `quiet_ambient_180s`
- `bass_environment_180s`
- `directed_events_60s`
- `machine_load_180s`

and emit the metrics in this document automatically.
