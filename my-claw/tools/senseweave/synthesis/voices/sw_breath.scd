// sw_breath.scd — Source stub for the `sw_breath` voice SynthDef.
//
// CypherClaw v2 §4 voice: glass-bell-jar breath tone.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 17, paired with the
// `cc_space_glass_bell_jar` reverb synth). This `fx_bus_id` control is
// the per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: breath
// Space: glass_bell_jar
// FX bus: 17
//
// Compile to synthesis/synthdefs/sw_breath.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_breath, {
    | freq = 220.0,
      amp = 0.06,
      attack = 0.4,
      release = 1.4,
      breathiness = 0.65,
      formant_shift = 1.0,
      out_bus = 0,
      fx_bus_id = 17,
      fx_send = 0.6 |

    var env, tone, noise, sig, send;

    env = EnvGen.kr(
        Env.linen(
            attackTime: attack.clip(0.01, 4.0),
            sustainTime: 0.05,
            releaseTime: release.clip(0.05, 6.0)
        ),
        doneAction: 2
    );

    tone  = SinOsc.ar(freq * formant_shift.clip(0.5, 2.0)) * (1.0 - breathiness);
    noise = BPF.ar(WhiteNoise.ar(1.0), freq * 2.0, 0.3) * breathiness;

    sig = (tone + noise) * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0));
}).writeDefFile("../synthdefs/");
)
