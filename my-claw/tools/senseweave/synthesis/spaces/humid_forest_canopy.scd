// CypherClaw v2 algorithmic space preset.
// Voice: kotekan
// Space: humid_forest_canopy
// FX bus: 19
// Rationale: CypherClaw described a dense forest canopy on a humid day, so the preset adds deep space plus flutter feedback for leaflike echoes.

(
SynthDef(\cc_space_humid_forest_canopy, {
    | in_bus = 19,
      out_bus = 0,
      verb_mix = 0.34,
      room_size = 0.7,
      damping = 0.38,
      predelay_ms = 18.0,
      decay_s = 2.4,
      early_reflection_level = 0.44,
      flutter_feedback = 0.68 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.023, decay_s) * flutter_feedback;
    wet = LeakDC.ar(late + flutter);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
