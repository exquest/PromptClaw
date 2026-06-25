// morph_insert.scd — Source for the `sw_morph_insert` SynthDef.
//
// CypherClaw v2 §11 macro timbre morph (CC-050 follow-on). A single persistent
// insert node placed immediately BEFORE the master node (99999), mirroring the
// reverb-space seed pattern (addBefore, ids in the 99000s). It reads the summed
// main bus, slowly crossfades the WHOLE ensemble between a WARM color (fuller
// lows, softer highs) and a BRIGHT color (trimmed lows, lifted highs), and
// writes the result back in place. A free-running slow LFO sweeps the morph so
// the entire mix's timbre breathes over minutes (SIG-2 — something always
// slowly moving), with no composer wiring required.
//
// LEVEL-SAFE BY CONSTRUCTION: the morph is a low/high *tilt* built from a
// complementary crossover, with every band coefficient <= 1 except a small
// high-band lift that rides on the (sparse, low-energy) top end. Neither color
// exceeds the input's broadband energy, so the wet signal is never louder than
// the dry mix at any morph position. This matters because the master's tanh
// drive + compander duck on RMS/loudness: the earlier additive-"air" version
// raised level on its bright side and re-triggered that ducking (heard as
// regular soft drop-outs). A pure tilt cannot add master loading.
//
// LIVE-SAFE: `mix` defaults to 0.0, an exact passthrough (sig == input), so
// seeding the node onto the live master chain is audibly transparent.
//
// Signal flow on bus 0:
//   [voices Out.ar(0)] -> [reverb spaces sum into 0]
//     -> [sw_morph_insert reads 0, tilts, ReplaceOut(0)] -> [master 99999]
//
// Compile to synthesis/synthdefs/sw_morph_insert.scsyndef via `.writeDefFile`.

(
SynthDef(\sw_morph_insert, {
    | in_bus = 0,
      out_bus = 0,
      mix = 0.0,
      rate = 0.018,
      depth = 1.0,
      bias = 0.0,
      fc = 900.0,
      warm_hi = 0.5,
      bright_lo = 0.8,
      bright_hi = 1.18 |

    var input, x, low, high, warm, bright, ga, gb, morphed, m, sig;

    input = In.ar(in_bus, 2);

    // Free-running morph position in [0,1]. Random start phase so a restart
    // doesn't snap the sweep back to a fixed point, and so it never sits still.
    x = (SinOsc.kr(rate.clip(0.001, 1.0), Rand(0.0, 2pi)).range(0.0, 1.0)
            * depth.clip(0.0, 1.0))
        + bias.clip(0.0, 1.0);
    x = x.clip(0.0, 1.0);

    // Complementary crossover: low + high == input (no energy created here).
    low  = LPF.ar(input, fc.clip(200.0, 4000.0));
    high = input - low;

    // Warm: keep lows, soften highs (always <= input energy).
    warm = low + (high * warm_hi.clip(0.0, 1.0));
    // Bright: trim lows, lift the sparse highs. Lows cut by `bright_lo` removes
    // more energy than the small high lift adds, so bright stays <= input too.
    bright = (low * bright_lo.clip(0.0, 1.0)) + (high * bright_hi.clip(0.0, 1.5));

    // Equal-power crossfade between the two colors.
    ga = cos(x * 0.5pi);
    gb = sin(x * 0.5pi);
    morphed = (warm * ga) + (bright * gb);

    // Wet/dry. mix == 0.0 -> sig == input exactly (transparent live insert).
    m = mix.clip(0.0, 1.0);
    sig = (input * (1.0 - m)) + (morphed * m);

    // Belt-and-braces peak guard (the tilt already prevents loudness gain).
    sig = sig.clip2(1.5);

    ReplaceOut.ar(out_bus, sig);
}).writeDefFile("../synthdefs/");
)
