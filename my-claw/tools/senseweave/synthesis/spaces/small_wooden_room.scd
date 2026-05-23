// CypherClaw v2 algorithmic space preset.
// Voice: pluck
// Space: small_wooden_room
// FX bus: 16
// Rationale: CypherClaw described a small wooden room with hard floorboards, so the preset keeps the tail dry and lively with strong early reflections.

(
SynthDef(\cc_space_small_wooden_room, {
    | in_bus = 16,
      out_bus = 0,
      verb_mix = 0.18,
      room_size = 0.24,
      damping = 0.42,
      predelay_ms = 8.0,
      decay_s = 0.7,
      early_reflection_level = 0.72,
      flutter_feedback = 0.08 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.037, decay_s) * flutter_feedback;
    wet = LeakDC.ar(late + flutter);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
