// sw_bass.scd — Source for the `sw_bass` voice SynthDef.
//
// anthony-taste SIG-8 bass = felt_sub + growl. This is the FELT SUB: a clean
// sustained sine foundation (mono, centered) with a touch of low harmonics for
// small-speaker audibility and gentle warmth. The bass role previously borrowed
// bowed/pluck (sharp/thin); this gives it a dedicated round low timbre.
//
// Fire-and-forget (the composer's play_voice path): a pure swell envelope
// (rise over `attack`, fall over `release`, no flat sustain) self-frees via
// doneAction:2. Control surface matches the LIVE house contract used by every
// play_voice voice: freq/amp/attack/release/out/verb/dly (+ room).
//
// Voice: bass
// Compile to synthesis/synthdefs/sw_bass.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_bass, {
    | freq = 110.0,
      amp = 0.1,
      attack = 0.8,
      release = 2.5,
      out = 0,
      verb = 0.0,
      dly = 0.0,
      room = 0.5 |

    var env, amp_lfo, sig;

    // Pure swell, fire-and-forget: rise then fall, self-frees. A felt sub
    // should bloom in rather than pluck — long attack, long release.
    env = EnvGen.kr(
        Env.new([0.0, 1.0, 0.0], [attack.clip(0.05, 4.0), release.clip(0.1, 6.0)], \sin),
        doneAction: 2
    );

    // Slow free-running amp breathing (felt_sub movement spec ~0.05Hz). Random
    // start phase so successive notes sit at different points of the cycle ->
    // gentle note-to-note dynamic life instead of a static level (anti-monotony).
    amp_lfo = SinOsc.kr(0.05, Rand(0.0, 2pi)).range(0.82, 1.0);

    // Clean sub sine + quiet low harmonics: the 2nd/3rd partials give the
    // missing-fundamental cue so the line is *heard* on laptop speakers while
    // still being *felt* as a sub on real ones.
    sig = SinOsc.ar(freq)
        + (SinOsc.ar(freq * 2.0) * 0.16)
        + (SinOsc.ar(freq * 3.0) * 0.05);
    // Gentle rounded saturation for body, then low-pass to keep it round (no fizz).
    sig = (sig * 1.4).tanh;
    sig = LPF.ar(sig, (freq * 8.0).clip(120.0, 1400.0));
    sig = LeakDC.ar(sig);

    sig = sig * env * amp_lfo * amp;

    // House contract: a tiny optional delay/reverb so the shared NEAR/FAR space
    // and the verb/dly args are honored. Defaults keep the sub dry and tight.
    sig = sig + (DelayC.ar(sig, 0.5, 0.28) * dly.clip(0.0, 1.0));
    sig = (sig * (1.0 - (verb.clip(0.0, 1.0) * 0.35)))
        + (FreeVerb.ar(sig, 1.0, room.clip(0.1, 0.95), 0.5) * (verb.clip(0.0, 1.0) * 0.35));

    Out.ar(out, Pan2.ar(sig, 0.0));   // mono center — bass anchors the middle
}).writeDefFile("../synthdefs/");
)
