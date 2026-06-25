// sw_growl.scd — Source for the `sw_growl` voice SynthDef.
//
// anthony-taste SIG-8 bass = felt_sub + growl. This is the GROWL: an FM voice
// run through rounded saturation and a resonant low-pass whose cutoff drifts on
// a slow free-running LFO. Built as the contemplative-stream BATH variant
// (warm, slow, evolving) rather than the festival CLUB variant (tempo-synced,
// aggressive) — the live stream is the meditative ambient set, not the drop.
//
// Fire-and-forget (play_voice path): a swell envelope self-frees via
// doneAction:2. Control surface matches the LIVE house contract:
// freq/amp/attack/release/out/verb/dly (+ room).
//
// Voice: growl
// Compile to synthesis/synthdefs/sw_growl.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_growl, {
    | freq = 110.0,
      amp = 0.1,
      attack = 0.4,
      release = 1.8,
      out = 0,
      verb = 0.0,
      dly = 0.0,
      room = 0.5 |

    var env, mod, car, cutoff, sig;

    env = EnvGen.kr(
        Env.new([0.0, 1.0, 0.0], [attack.clip(0.02, 3.0), release.clip(0.1, 5.0)], \sin),
        doneAction: 2
    );

    // FM: modulator at the fundamental, moderate index -> a warm harmonic stack
    // (more body than a bare sine, less buzz than a saw).
    mod = SinOsc.ar(freq * 1.0) * (freq * 0.75);
    car = SinOsc.ar(freq + mod);
    // Rounded saturation (BATH variant: warm, not aggressive).
    sig = (car * 2.0).tanh;

    // Resonant low-pass whose cutoff drifts on a slow free-running LFO (0.12Hz,
    // SIG-2 "something always slowly moving"). Random phase per note so the
    // sweep never sits still or lines up across notes.
    cutoff = (freq * 4.0) * SinOsc.kr(0.12, Rand(0.0, 2pi)).range(0.55, 1.7);
    sig = RLPF.ar(sig, cutoff.clip(70.0, 1400.0), 0.4);
    sig = LeakDC.ar(sig);

    sig = sig * env * amp;

    sig = sig + (DelayC.ar(sig, 0.5, 0.28) * dly.clip(0.0, 1.0));
    sig = (sig * (1.0 - (verb.clip(0.0, 1.0) * 0.4)))
        + (FreeVerb.ar(sig, 1.0, room.clip(0.1, 0.95), 0.5) * (verb.clip(0.0, 1.0) * 0.4));

    Out.ar(out, Pan2.ar(sig, 0.0));   // mono center
}).writeDefFile("../synthdefs/");
)
