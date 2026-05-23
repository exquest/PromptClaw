// sw_pluck.scd — Source stub for the `sw_pluck` voice SynthDef.
//
// CypherClaw v2 §4 voice: small-wooden-room plucked tone.
// Routes the dry signal to `out_bus` and a parallel send to the matching
// per-voice FX return bus `fx_bus_id` (default 16, paired with the
// `cc_space_small_wooden_room` reverb synth in
// `spaces/small_wooden_room.scd`). This `fx_bus_id` control is the
// per-voice routing contract that
// `cypherclaw.space_reverb.build_voice_s_new_args` writes via OSC.
//
// Voice: pluck
// Space: small_wooden_room
// FX bus: 16
//
// Compile to synthesis/synthdefs/sw_pluck.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_pluck, {
    | freq = 220.0,
      amp = 0.06,
      attack = 0.005,
      release = 1.0,
      brightness = 0.55,
      position = 0.18,
      damping = 0.32,
      detune = 0.004,
      verb = 0.18,
      room = 0.24,
      out_bus = 0,
      fx_bus_id = 16,
      fx_send = 0.5 |

    var env, exciter, body, sig, wet, dry, send;

    env = EnvGen.kr(
        Env.perc(attack.clip(0.001, 0.5), release.clip(0.05, 6.0)),
        doneAction: 2
    );

    // Short noise exciter shapes the pluck attack transient.
    exciter = LPF.ar(WhiteNoise.ar(1.0), 4000.0 + (brightness * 6000.0))
        * Env.perc(0.001, 0.02).kr;

    // Comb-filter resonator gives the plucked-string body.
    body = CombL.ar(
        exciter,
        0.05,
        (1.0 / freq).clip(0.0001, 0.05),
        (release * (1.0 - damping)).clip(0.05, 4.0)
    );

    sig = body * env * amp;
    sig = Pan2.ar(sig, position.clip(-1.0, 1.0));

    dry  = sig;
    send = sig * fx_send.clip(0.0, 1.0);

    Out.ar(out_bus, dry);
    Out.ar(fx_bus_id, send);
}).writeDefFile("../synthdefs/");
)
