// sw_kotekan.scd — Source stub for the `sw_kotekan` voice SynthDef.
//
// CypherClaw v2 §4 voice: humid-forest-canopy interlocking kotekan tone.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 19, paired with the
// `cc_space_humid_forest_canopy` reverb synth). This `fx_bus_id` control
// is the per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: kotekan
// Space: humid_forest_canopy
// FX bus: 19
//
// Compile to synthesis/synthdefs/sw_kotekan.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_kotekan, {
    | freq = 440.0,
      amp = 0.06,
      attack = 0.005,
      release = 0.6,
      brightness = 0.7,
      out_bus = 0,
      fx_bus_id = 19,
      fx_send = 0.55 |

    var env, mallet, body, sig;

    env = EnvGen.kr(
        Env.perc(attack.clip(0.001, 0.2), release.clip(0.05, 4.0)),
        doneAction: 2
    );

    // Metallic FM bell-tone characteristic of bronze gamelan keys.
    mallet = SinOsc.ar(freq * 2.76)
        * EnvGen.kr(Env.perc(0.001, 0.25))
        * brightness.clip(0.0, 1.0);
    body = SinOsc.ar(freq) + (SinOsc.ar(freq * 2.0) * 0.4);

    sig = (body + mallet) * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0));
}).writeDefFile("../synthdefs/");
)
