// CypherClaw v2 algorithmic space preset.
// Voice: bowed
// Space: damp_cave_wall
// FX bus: 21
// Rationale: CypherClaw described a damp cave wall, so the preset darkens the tail with high damping and a slow, weighty decay.

(
SynthDef(\cc_space_damp_cave_wall, {
    | in_bus = 21,
      out_bus = 0,
      verb_mix = 0.38,
      room_size = 0.76,
      damping = 0.68,
      predelay_ms = 26.0,
      decay_s = 3.6,
      early_reflection_level = 0.28,
      flutter_feedback = 0.12 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.083, decay_s) * flutter_feedback;
    wet = LPF.ar(LeakDC.ar(late + flutter), 4200.0);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
