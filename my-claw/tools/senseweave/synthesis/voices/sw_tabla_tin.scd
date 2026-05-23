// sw_tabla_tin.scd — Source stub for the `sw_tabla_tin` voice SynthDef.
//
// CypherClaw v2 §4 voice: dusk-garden tabla "tin" stroke.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 22, paired with the
// `cc_space_dusk_garden` reverb synth). This `fx_bus_id` control is the
// per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: tabla_tin
// Space: dusk_garden
// FX bus: 22
//
// Compile to synthesis/synthdefs/sw_tabla_tin.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_tabla_tin, {
    | freq = 660.0,
      amp = 0.07,
      attack = 0.002,
      release = 0.35,
      sharpness = 0.65,
      out_bus = 0,
      fx_bus_id = 22,
      fx_send = 0.5 |

    var env, strike, body, sig;

    env = EnvGen.kr(
        Env.perc(attack.clip(0.001, 0.05), release.clip(0.05, 2.0)),
        doneAction: 2
    );

    // Tabla "tin": sharp tonal slap with metallic upper partials.
    strike = HPF.ar(WhiteNoise.ar(1.0), 2000.0)
        * EnvGen.kr(Env.perc(0.001, 0.015))
        * sharpness.clip(0.0, 1.0);
    body = SinOsc.ar(freq) + (SinOsc.ar(freq * 1.5) * 0.4);

    sig = (body + strike) * env * amp;
    sig = Pan2.ar(sig, 0.0);

    Out.ar(out_bus, sig);
    Out.ar(fx_bus_id, sig * fx_send.clip(0.0, 1.0));
}).writeDefFile("../synthdefs/");
)
