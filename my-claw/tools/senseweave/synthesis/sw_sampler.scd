// sw_sampler.scd — Source stub for the `sw_sampler` granular SynthDef.
//
// Companion source for `synthdefs/sw_sampler.scsyndef`. This is the memory
// voice of the signature quintet: a granular cloud over a buffer (live
// capture, self-quotation, or curated library sample) with a parallel
// send to the dedicated `sw_sampler_fx` bus (default stereo bus 16).
//
// Voice control surface (driven by `senseweave.sampler_dispatch.SamplerDispatcher`
// over OSC):
//
//     bufnum                      sample buffer to scrub (required)
//     amp                         linear output gain (post-envelope)
//     grain_size_ms               grain duration in milliseconds (20..200)
//     density                     grains per second (Impulse.kr trigger rate)
//     position                    initial buffer position, normalised 0..1
//     position_rate               scrub speed in normalised-pos / second
//                                 (0 = freeze on `position`, 1 = ~natural-time
//                                 scrub through the whole buffer per second)
//     pitch_transpose_semitones   constant transposition applied to grain rate
//     pitch_jitter_semitones      ±semitone jitter rolled per-grain (TRand)
//     attack_sec / release_sec    Env.asr envelope shape
//     gate                        sustained gate; gate=0 triggers release tail
//     out_bus                     dry destination (defaults to master 0)
//     fx_bus_id                   effects-bus destination (defaults to 16)
//     fx_send                     level of the parallel send into fx_bus_id
//
// Routing convention: the dry signal is written at full level to `out_bus`
// (master, channels 0/1 in our graph) and a parallel copy scaled by
// `fx_send` is written to `fx_bus_id` (16/17). `sw_sampler_fx` reads from
// 16 and writes the processed tail back to 0, so master receives dry+wet.
// `fx_bus_id` matches the per-voice routing contract used by the seven
// `voices/*.scd` SynthDefs and `cypherclaw.space_reverb.build_voice_s_new_args`.
//
// `EnvGen.kr(Env.asr, gate, doneAction: 2)` self-frees the synth once the
// release tail completes after the caller flips `gate` to 0.
//
// Compile to synthesis/synthdefs/sw_sampler.scsyndef via .writeDefFile.

(
SynthDef(\sw_sampler, {
    | bufnum = 0,
      amp = 0.5,
      grain_size_ms = 80.0,
      density = 12.0,
      position = 0.0,
      position_rate = 0.0,
      pitch_transpose_semitones = 0.0,
      pitch_jitter_semitones = 0.1,
      attack_sec = 0.05,
      release_sec = 0.2,
      gate = 1.0,
      out_bus = 0,
      fx_bus_id = 16,
      fx_send = 0.4 |

    var grainDur, dens, pos, posRate, transpose, jitter, atk, rel, fxAmt;
    var grainTrig, jitterSemis, rate, positionPhase, pan;
    var env, grain, sig, fxOut;

    // Range-clip incoming controls to keep the granular engine numerically
    // stable. The acceptance ranges live here so OSC senders can push raw
    // values without crashing scsynth.
    grainDur  = grain_size_ms.clip(20.0, 200.0) * 0.001;
    dens      = density.clip(1.0, 200.0);
    pos       = position.clip(0.0, 1.0);
    posRate   = position_rate.clip(-8.0, 8.0);
    transpose = pitch_transpose_semitones.clip(-48.0, 48.0);
    jitter    = pitch_jitter_semitones.clip(0.0, 12.0);
    atk       = attack_sec.clip(0.001, 4.0);
    rel       = release_sec.clip(0.001, 8.0);
    fxAmt     = fx_send.clip(0.0, 1.0);

    // Grain trigger train at the requested density (grains per second).
    grainTrig = Impulse.kr(dens);

    // Per-grain pitch jitter (±jitter semitones) plus the constant
    // transpose, both folded into a single rate multiplier.
    jitterSemis = TRand.kr(jitter.neg, jitter, grainTrig);
    rate        = (transpose + jitterSemis).midiratio;

    // Position scrub: normalised position advances at `posRate` units / sec.
    // Sweep.ar emits a continuous ramp so partial-grain interpolation stays
    // smooth; .wrap keeps the phase inside [0, 1] for GrainBuf.
    positionPhase = (pos + Sweep.ar(1, posRate)).wrap(0.0, 1.0);

    // Mild stereo spread per grain; deterministic-feeling at low jitter.
    pan = TRand.kr(-0.6, 0.6, grainTrig);

    // Stereo grain cloud. interp:2 = linear interp; envbufnum:-1 = built-in
    // Hanning grain envelope. maxGrains caps polyphony to keep CPU bounded.
    grain = GrainBuf.ar(
        numChannels: 2,
        trigger:     grainTrig,
        dur:         grainDur,
        sndbuf:      bufnum,
        rate:        rate,
        pos:         positionPhase,
        interp:      2,
        pan:         pan,
        envbufnum:   -1,
        maxGrains:   64
    );

    // Attack / release envelope with sustain held by `gate`. doneAction:2
    // self-frees the synth once the release tail completes.
    env = EnvGen.kr(Env.asr(atk, 1.0, rel), gate, doneAction: 2);

    sig = grain * env * amp;

    // Parallel send architecture: dry at full level to out_bus, scaled
    // copy to the fx bus. Reducing fx_send does not pull down the dry.
    fxOut = sig * fxAmt;

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, fxOut);
}).writeDefFile("synthdefs/");
)
