// CypherClaw v2 algorithmic space preset.
// Voice: choir
// Space: stone_cathedral
// FX bus: 18
// Rationale: CypherClaw described a stone cathedral with high vaulted ceilings, so the preset favors a cold, diffuse, several-second tail.

(
SynthDef(\cc_space_stone_cathedral, {
    | in_bus = 18,
      out_bus = 0,
      verb_mix = 0.5,
      room_size = 0.95,
      damping = 0.18,
      predelay_ms = 42.0,
      decay_s = 6.2,
      early_reflection_level = 0.35,
      flutter_feedback = 0.02 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.061, decay_s) * flutter_feedback;
    wet = LeakDC.ar(late + flutter);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
