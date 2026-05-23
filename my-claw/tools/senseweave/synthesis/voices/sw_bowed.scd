// sw_bowed.scd — Source stub for the `sw_bowed` voice SynthDef.
//
// CypherClaw v2 §4 voice: damp-cave-wall bowed-string tone.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 21, paired with the
// `cc_space_damp_cave_wall` reverb synth). This `fx_bus_id` control is
// the per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: bowed
// Space: damp_cave_wall
// FX bus: 21
//
// Compile to synthesis/synthdefs/sw_bowed.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_bowed, {
    | freq = 220.0,
      amp = 0.05,
      attack = 0.25,
      release = 1.6,
      bow_pressure = 0.55,
      out_bus = 0,
      fx_bus_id = 21,
      fx_send = 0.6 |

    var env, exciter, body, sig;

    env = EnvGen.kr(
        Env.asr(attack.clip(0.02, 4.0), 1.0, release.clip(0.1, 6.0)),
        doneAction: 2
    );

    // Bowed-string excitation: pink noise filtered into resonator.
    exciter = PinkNoise.ar(bow_pressure.clip(0.0, 1.0));
    body = Resonz.ar(exciter, freq, 0.04, mul: 8.0);
    body = body + (SinOsc.ar(freq) * 0.2);

    sig = body * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0));
}).writeDefFile("../synthdefs/");
)
