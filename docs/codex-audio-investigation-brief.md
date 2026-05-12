# Audio Investigation Brief — CypherClaw Clicking/Popping

## Mission

Investigate and fix random clicking/popping in CypherClaw's audio output. Also audit the full audio chain for improvements to mixing, synthesis, and signal flow.

## Access

```bash
ssh cypherclaw    # or ssh user@192.168.1.139
```

All tools are in `/home/user/cypherclaw/`. Python venv at `/home/user/cypherclaw/.venv/bin/python3`.

## The Problem

Random audio clicks/pops during music playback. Not rhythmic, not correlated with note attacks. Happens unpredictably — sometimes every 30 seconds, sometimes minutes apart. The music is generative ambient played through SuperCollider via PipeWire.

## Audio Chain (signal flow)

```
duet_composer.py (Python)
    │ sends /s_new OSC messages to scsynth
    ▼
scsynth (SuperCollider, port 57110, 48kHz, 4096 quantum)
    │ renders audio to JACK outputs via PipeWire shim
    ▼
PipeWire (pw-jack) ─── quantum 4096/48000
    │
    ▼
Scarlett 4i4 USB ─── playback_FL + playback_FR
    │
    ▼
Speakers
```

### PipeWire Config

```
/etc/pipewire/pipewire.conf.d/10-pro-audio.conf:
    default.clock.rate          = 48000
    default.clock.quantum       = 4096
    default.clock.min-quantum   = 1024
    default.clock.max-quantum   = 8192
```

### scsynth Launch

```bash
# From scripts/start_audio.sh
pw-jack chrt -f 40 scsynth -u 57110 -a 1024 -m 65536 -D 0 -R 0 -o 6 -i 8 -S 48000
```

- Real-time priority via `chrt -f 40`
- No hardware buffer control (`-D 0 -R 0`)
- 6 outputs, 8 inputs, 48kHz

### Scarlett Mixer State

- All analog Mix A-F inputs zeroed to -80dB (prevents Theramini/contact mic pass-through)
- Outputs set to PCM direct (SuperCollider outputs)
- Standalone mode OFF

### Connections

```
SuperCollider:out_1 → Scarlett 4i4 USB:playback_FL
SuperCollider:out_2 → Scarlett 4i4 USB:playback_FR
Scarlett 4i4 USB:capture_FL → SuperCollider:in_1  (contact mic, recently reconnected)
Scarlett 4i4 USB:capture_FR → SuperCollider:in_2  (contact mic, recently reconnected)
```

**Note:** Webcam audio was previously connected to SC inputs and caused confirmed pops. It was disconnected. The Scarlett inputs were recently reconnected — the clicking may have returned with them.

## Key Files

| File | What |
|------|------|
| `/home/user/cypherclaw/scripts/start_audio.sh` | Audio chain startup — PipeWire, scsynth, connections, SynthDef loading, master chain |
| `/home/user/cypherclaw/tools/duet_composer.py` | Music engine — sends OSC to scsynth, ~1200 lines |
| `/home/user/cypherclaw/tools/senseweave/synthesis/senseweave_voice.py` | ADSR voice controller with gate lifecycle |
| `/home/user/cypherclaw/tools/senseweave/synthesis/synthdefs/` | Compiled .scsyndef binary files |
| `/home/user/cypherclaw/tools/senseweave/synthesis/boot_synthdefs.scd` | SC source for gate-controlled SynthDefs |
| `/home/user/cypherclaw/scripts/restart_composer.sh` | Fade-out/fade-in restart (no hardware mute) |
| `/home/user/cypherclaw/scripts/composer_supervisor.sh` | Auto-restart on crash/silence |
| `/home/user/cypherclaw/tools/self_listener.py` | Self-monitoring — captures SC output, reports peak/RMS/rolling_peak to `/tmp/self_listen.json` |
| `/etc/pipewire/pipewire.conf.d/10-pro-audio.conf` | PipeWire quantum/rate config |

## Master Chain

Node 99999 (`sw_master_smooth`) sits at the tail of the synth tree. It has internal coprime LFOs for EQ modulation so no external `/n_set` is needed during play (which was a previous pop source).

```
drive=0.18, warmth=0.38, reverb=0.08, room=0.5, amp=3.0
```

The composer recreates the master via `/s_new` + `/n_set` at the start of every song (self-healing).

## What We Know About the Clicks

1. **PipeWire replaced JACK** specifically to eliminate clicks — PipeWire fills xruns with silence instead of producing discontinuities
2. **All SynthDefs have doneAction:2** — synths self-free when their envelope ends, no `/n_free` or `/n_set gate 0` needed for fire-and-forget voices
3. **No `/n_set` during play** for the master chain — internal LFOs handle EQ drift
4. **Webcam audio was confirmed as a previous click source** — disconnected
5. **Scarlett contact mic inputs were recently reconnected** — clicking may correlate
6. **The composer has amplitude compression** (hard limiter floor=0.06, ceiling=0.25) and per-voice normalization — clipping from amplitude overflow is possible if normalization factors are wrong
7. **Multiple composer processes were running simultaneously at one point** — could have left orphaned synth nodes in scsynth
8. **Gate-controlled SynthDefs** (sw_drone_fog, sw_string_resonance, sw_granular_field) were recently added — their release behavior via `/n_set gate 0` needs verification

## Possible Click Sources to Investigate

1. **Scarlett input reconnection** — the contact mics flowing into SC might be introducing noise/clicks. Test: disconnect inputs, listen for 5 min.
2. **Synth node accumulation** — if synths aren't freeing properly (broken doneAction), nodes pile up and eventually cause audio artifacts. Check: `/g_dumpTree` or query node count.
3. **PipeWire xruns** — even though PipeWire fills with silence, xruns still indicate timing problems. Check: `pw-top` for xrun counts.
4. **USB audio glitches** — the Scarlett is USB. USB audio can click on bus contention. Check: `dmesg | grep -i usb` for errors.
5. **Sample rate mismatch** — if any component runs at a different rate than 48kHz, SRC artifacts could cause clicks.
6. **Amplitude discontinuities** — if the normalization or compression creates sharp amplitude jumps between notes, that's a click. Check the play_voice() signal chain.
7. **The self-healing master chain** — `/s_new` with an existing node ID might cause a brief audio discontinuity even though scsynth "silently fails." Test: remove the `/s_new` and only keep `/n_set`.
8. **CPU scheduling** — scsynth runs at `chrt -f 40` but the compositor, greeter, and art engine also consume CPU. Check if scsynth is getting preempted.

## Self-Listener

The self-listener captures 1-second audio clips from SC output every 3 seconds and writes to `/tmp/self_listen.json`:

```json
{
    "timestamp": 1776017277.0,
    "rms": 0.0155,
    "peak": 0.065,
    "rolling_peak": 0.131,
    "amplitude": 0.0155,
    "pitch_hz": 220.0,
    "pitch_confidence": 0.85,
    "is_playing": true,
    "is_silent": false
}
```

This could be enhanced to detect clicks (a click is a single-sample or few-sample spike that's 10-20dB above the surrounding signal level).

## Deliverables

1. **Root cause identification** — what specifically causes the clicks
2. **Fix** — eliminate the clicks
3. **Audio chain audit** — recommendations for improvements to mixing, signal flow, SynthDef quality, buffer sizes, etc.
4. **Click detector** — add transient spike detection to the self-listener so CypherClaw can self-monitor audio quality going forward

## Hardware

- Dell OptiPlex 7090, 62GB RAM, T1000 8GB GPU, Ubuntu 24.04
- Focusrite Scarlett 4i4 USB audio interface
- 2x C920 webcams (video0 dark/covered, video2 = head camera)
- PipeWire 1.0.x managing all audio
