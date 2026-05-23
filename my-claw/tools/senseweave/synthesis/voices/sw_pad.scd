// sw_pad.scd — Source stub for the `sw_pad` voice SynthDef.
//
// CypherClaw v2 §4 voice: marble-empty-hall sustained pad tone.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 20, paired with the
// `cc_space_marble_empty_hall` reverb synth). This `fx_bus_id` control
// is the per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: pad
// Space: marble_empty_hall
// FX bus: 20
//
// Compile to synthesis/synthdefs/sw_pad.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_pad, {
    | freq = 220.0,
      amp = 0.05,
      attack = 1.2,
      release = 3.0,
      out_bus = 0,
      fx_bus_id = 20,
      fx_send = 0.7 |

    var env, layers, sig;

    env = EnvGen.kr(
        Env.asr(attack.clip(0.05, 8.0), 1.0, release.clip(0.1, 8.0)),
        doneAction: 2
    );

    // Multi-octave detuned saw stack for a wide, slow-evolving pad.
    layers = Mix.ar([
        Saw.ar(freq * 0.998, mul: 0.20),
        Saw.ar(freq * 1.002, mul: 0.20),
        Saw.ar(freq * 0.501, mul: 0.10),
        Saw.ar(freq * 2.003, mul: 0.07)
    ]);
    layers = RLPF.ar(layers, freq * 6.0, 0.6);

    sig = layers * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0));
}).writeDefFile("../synthdefs/");
)
