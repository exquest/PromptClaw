// CypherClaw v2 algorithmic space preset.
// Voice: pad
// Space: marble_empty_hall
// FX bus: 20
// Rationale: CypherClaw described a large, empty hall with marble floors, so the preset uses a broad cold room and a long washing decay.

(
SynthDef(\cc_space_marble_empty_hall, {
    | in_bus = 20,
      out_bus = 0,
      verb_mix = 0.44,
      room_size = 0.88,
      damping = 0.2,
      predelay_ms = 32.0,
      decay_s = 4.8,
      early_reflection_level = 0.3,
      flutter_feedback = 0.08 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.047, decay_s) * flutter_feedback;
    wet = LeakDC.ar(late + flutter);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
