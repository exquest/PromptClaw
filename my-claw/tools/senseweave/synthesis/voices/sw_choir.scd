// sw_choir.scd — Source stub for the `sw_choir` voice SynthDef.
//
// CypherClaw v2 §4 voice: stone-cathedral choir tone.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 18, paired with the
// `cc_space_stone_cathedral` reverb synth). This `fx_bus_id` control is
// the per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: choir
// Space: stone_cathedral
// FX bus: 18
//
// Compile to synthesis/synthdefs/sw_choir.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_choir, {
    | freq = 220.0,
      amp = 0.06,
      attack = 0.6,
      release = 2.5,
      formant = 0.5,
      out_bus = 0,
      fx_bus_id = 18,
      fx_send = 0.7 |

    var env, voices, sig;

    env = EnvGen.kr(
        Env.asr(attack.clip(0.05, 6.0), 1.0, release.clip(0.1, 8.0)),
        doneAction: 2
    );

    // Detuned saw stack approximates a stacked choral ensemble.
    voices = Mix.fill(5, { |i|
        SinOsc.ar(freq * (1.0 + ((i - 2) * 0.004)), mul: 0.2)
        + Saw.ar(freq * (1.0 + ((i - 2) * 0.004)), mul: 0.05)
    });
    voices = BPF.ar(voices, freq * (1.0 + formant.clip(0.0, 2.0)), 0.4);

    sig = voices * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0));
}).writeDefFile("../synthdefs/");
)
