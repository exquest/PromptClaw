// morph_voice.scd — Source stub for the `morph_voice` SynthDef.
//
// CypherClaw v2 §11 single-line timbre morph (CC-050 / T-047): two
// parallel source voices crossfaded by a continuous `morph_x` control.
// `morph_x = 0.0` produces source A only (saw); `morph_x = 1.0`
// produces source B only (pulse). Intermediate values blend gains
// linearly. This is a skeleton: the real palette assigns source A/B
// to entries in synthdef_registry; here we use saw + pulse as the two
// canonical bandlimited oscillators that share a register and let the
// morph crossfade be auditioned end-to-end.
//
// Compile to synthesis/synthdefs/morph_voice.scsyndef via `.writeDefFile`.

(
SynthDef(\morph_voice, {
    | freq = 220.0,
      amp = 0.06,
      attack = 0.05,
      release = 1.2,
      morph_x = 0.0,
      pulse_width = 0.5,
      out_bus = 0 |

    var env, source_a, source_b, gain_a, gain_b, sig;

    env = EnvGen.kr(
        Env.asr(attack.clip(0.005, 4.0), 1.0, release.clip(0.05, 8.0)),
        doneAction: 2
    );

    // Source A: bandlimited saw.
    source_a = Saw.ar(freq);
    // Source B: bandlimited pulse.
    source_b = Pulse.ar(freq, pulse_width.clip(0.05, 0.95));

    // Linear crossfade: morph_x=0 -> all A, morph_x=1 -> all B.
    gain_a = 1.0 - morph_x.clip(0.0, 1.0);
    gain_b = morph_x.clip(0.0, 1.0);

    sig = (source_a * gain_a) + (source_b * gain_b);
    sig = sig * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
