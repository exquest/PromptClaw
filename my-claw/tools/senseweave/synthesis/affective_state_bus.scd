// affective_state_bus.scd — Provision the shared `affective_state_bus`
// control bus and the reader-side wiring used by every voice.
//
// Per the CypherClaw v2 PRD (§7.5.2 / CC-070..073), a single control
// bus holds a float in [0.0, 1.0] — the current ensemble affect. Each
// voice writes its rolling-window expression intensity to the bus
// (max-pooled across voices) and reads the bus to scale its own
// modulator depths via `(1 + coupling_strength * affect)`. The bus
// slow-decays toward 0 with a ~5s time constant in the absence of
// contributors.
//
// Allocation: the bus lives at a fixed control-bus index so voices and
// the writer/decay synths can address it without runtime negotiation.
// `senseweave.affective_state_bus.AFFECTIVE_STATE_BUS_INDEX` is the
// single source of truth — keep this stub's index in sync with that
// Python constant (tests pin both).

(
~affectiveStateBusIndex = 100;
~affectiveStateBusChannels = 1;
~affectiveStateBusMin = 0.0;
~affectiveStateBusMax = 1.0;
~affectiveStateBusDecaySeconds = 5.0;

// Reader-side macro used by every voice SynthDef in T-003: read the
// shared bus, clamp it to the documented [0, 1] range, and return the
// k-rate affect signal. Inlined into voice synthdefs as
// `In.kr(~affectiveStateBusIndex, 1).clip(0.0, 1.0)`.
~affectiveStateBusReader = {
    In.kr(~affectiveStateBusIndex, ~affectiveStateBusChannels)
        .clip(~affectiveStateBusMin, ~affectiveStateBusMax);
};

// Reference reader SynthDef demonstrating the reader-side wiring per
// voice. Voice synthdefs adopt the same three steps (T-003):
//
//   1. affect = In.kr(~affectiveStateBusIndex, 1).clip(0.0, 1.0)
//   2. coupling = coupling_strength.clip(0.0, 1.0)
//   3. effective_depth = nominal_depth * (1.0 + coupling * affect)
//
// The synth writes the effective modulator depth to a per-voice
// control bus so the calling voice can patch it into its vibrato /
// tremolo / dynamics modulators without bundling the read inside each
// modulator's UGen graph.
SynthDef(\sw_affective_state_reader, {
    | out_bus = 0,
      coupling_strength = 0.5,
      nominal_depth = 0.0 |

    var affect, coupling, effectiveDepth;

    affect          = In.kr(~affectiveStateBusIndex, ~affectiveStateBusChannels)
                        .clip(~affectiveStateBusMin, ~affectiveStateBusMax);
    coupling        = coupling_strength.clip(0.0, 1.0);
    effectiveDepth  = nominal_depth * (1.0 + (coupling * affect));

    Out.kr(out_bus, effectiveDepth);
}).writeDefFile("synthdefs/");

// Slow-decay synth (T-004 / PRD §7.5.2). Reads the shared bus, applies
// an exponential decay toward 0 with the documented ~5s time constant,
// and writes the decayed value back to the same bus. Per-voice writers
// re-assert the bus on every tick they have contributors, so the decay
// only takes effect when the writer has been silent — matching the
// Python-side `AffectiveStateBusWriter.flush` semantics.
//
//   decayed = current * exp(-dt / tau)
//
// `Decay.kr` is not used here because it is impulse-driven; the bus
// instead carries the *current* affect value, so we apply a first-order
// IIR lowpass toward 0 (`LagUD.kr` with downward lag = tau, upward lag
// = 0) which is equivalent at the documented time constant.
SynthDef(\sw_affective_state_decay, {
    | tau = 5.0 |

    var affect, decayed;

    affect  = In.kr(~affectiveStateBusIndex, ~affectiveStateBusChannels)
                .clip(~affectiveStateBusMin, ~affectiveStateBusMax);
    decayed = LagUD.kr(affect, lagTimeU: 0.0, lagTimeD: tau);

    ReplaceOut.kr(~affectiveStateBusIndex, decayed);
}).writeDefFile("synthdefs/");
)
