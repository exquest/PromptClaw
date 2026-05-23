// CypherClaw v2 algorithmic space preset.
// Voice: tabla_tin
// Space: dusk_garden
// FX bus: 22
// Rationale: CypherClaw described an outdoor garden at dusk, so the preset keeps the space open but intimate with warm nearby diffusion.

(
SynthDef(\cc_space_dusk_garden, {
    | in_bus = 22,
      out_bus = 0,
      verb_mix = 0.26,
      room_size = 0.48,
      damping = 0.36,
      predelay_ms = 12.0,
      decay_s = 1.5,
      early_reflection_level = 0.54,
      flutter_feedback = 0.28 |

    var input, early, late, flutter, wet, sig;
    input = In.ar(in_bus, 2);
    early = DelayC.ar(input, 0.08, predelay_ms * 0.001) * early_reflection_level;
    late = FreeVerb.ar(input + early, mix: 1.0, room: room_size, damp: damping);
    flutter = CombC.ar(late, 0.3, 0.031, decay_s) * flutter_feedback;
    wet = LeakDC.ar(late + flutter);
    sig = (input * (1.0 - verb_mix)) + (wet * verb_mix);
    Out.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
