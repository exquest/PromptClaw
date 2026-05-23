// CypherClaw v2 algorithmic space preset.
// Voice: breath
// Space: glass_bell_jar
// FX bus: 17
// Rationale: CypherClaw described a glass bell jar at sea level, so the preset uses tight predelay and high early reflections for trapped intimacy.

(
SynthDef(\cc_space_glass_bell_jar, {
    | in_bus = 17,
      out_bus = 0,
      verb_mix = 0.24,
      room_size = 0.18,
      damping = 0.24,
      predelay_ms = 3.0,
      decay_s = 1.1,
      early_reflection_level = 0.86,
      flutter_feedback = 0.05 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.029, decay_s) * flutter_feedback;
    wet = LeakDC.ar(late + flutter);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
