// morph_voice.scd — Source for the `morph_voice` SynthDef.
//
// CypherClaw v2 §11 single-line timbre morph (CC-050 / T-047): two
// parallel source voices crossfaded by a continuous `morph_x` control.
// `morph_x = 0.0` produces source A only (saw); `morph_x = 1.0`
// produces source B only (pulse). The `morph_curve` control selects
// the crossfade law: 0 = linear (constant-sum gain), 1 = equal-power
// (constant-power gain; the standard musical crossfade that avoids the
// ~3 dB perceived dip in the middle of a linear fade). The two scaled
// sources are summed and written to `out_bus`.
//
// Compile to synthesis/synthdefs/morph_voice.scsyndef via `.writeDefFile`.

(
SynthDef(\morph_voice, {
    | freq = 220.0,
      amp = 0.06,
      attack = 0.05,
      release = 1.2,
      morph_x = 0.0,
      morph_curve = 1,
      pulse_width = 0.5,
      out_bus = 0 |

    var env, source_a, source_b, x, lin_a, lin_b, ep_a, ep_b, gain_a, gain_b, sig;

    env = EnvGen.kr(
        Env.asr(attack.clip(0.005, 4.0), 1.0, release.clip(0.05, 8.0)),
        doneAction: 2
    );

    // Source A: bandlimited saw.
    source_a = Saw.ar(freq);
    // Source B: bandlimited pulse.
    source_b = Pulse.ar(freq, pulse_width.clip(0.05, 0.95));

    // Clamp morph position into the documented [0.0, 1.0] range once.
    x = morph_x.clip(0.0, 1.0);

    // Linear crossfade: gain_a + gain_b == 1.
    lin_a = 1.0 - x;
    lin_b = x;

    // Equal-power crossfade: gain_a^2 + gain_b^2 == 1. Uses the
    // quarter-cosine pair so the endpoints still hit unity exactly at
    // x=0 and x=1 (cos(0)=1, sin(pi/2)=1).
    ep_a = cos(x * 0.5pi);
    ep_b = sin(x * 0.5pi);

    // Select the law per-synth via `morph_curve` (0=linear, 1=equal-power).
    gain_a = Select.kr(morph_curve.clip(0, 1), [lin_a, ep_a]);
    gain_b = Select.kr(morph_curve.clip(0, 1), [lin_b, ep_b]);

    // Sum the two scaled sources to the output bus.
    sig = (source_a * gain_a) + (source_b * gain_b);
    sig = sig * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
