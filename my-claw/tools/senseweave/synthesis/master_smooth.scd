// master_smooth.scd — Source stub for the `sw_master_smooth` SynthDef.
//
// Companion source for `synthdefs/sw_master_smooth.scsyndef`. This stub
// documents the control surface that `senseweave.master_bus` drives over
// OSC; rebuilds via `.writeDefFile("synthdefs/")` keep the binary
// artefact in lockstep with the Python helper.
//
// Chain order (mono in, stereo out):
//
//     bus 0/1 -> tape-style soft drive (`drive`, `warmth`)
//             -> master VCA scaled by `amp`
//             -> sampler-bus VCA scaled by `sampler_amp`
//             -> bus comp (bypassed when `sampler_bypass_comp` >= 0.5)
//             -> stereo plate reverb (`reverb` wet mix, `room` size)
//             -> Out.ar(0)
//
// The two sampler controls were added in T-005 to give the granular
// sampler bus its own peak-normalised gain stage and a way to bypass the
// master bus compressor so grain transients are not squashed. Both
// default to 1.0 (unity gain, comp bypassed) so a fresh boot does not
// accidentally mute or compress the sampler before
// `master_bus_s_new_args()` writes scene-aware values.
//
// `senseweave.master_bus.master_bus_s_new_args()` is the single source of
// truth for the boot-time arg list — keep this stub's defaults in sync
// with `DEFAULT_MASTER_BUS_VALUES` there.

(
SynthDef(\sw_master_smooth, {
    | amp = 5.0,
      sampler_amp = 1.0,
      sampler_bypass_comp = 1.0,
      drive = 0.15,
      warmth = 0.35,
      reverb = 0.05,
      room = 0.5 |

    var input, driven, warm, masterStage, samplerStage;
    var compIn, compressed, busSig, verbWet, sig;
    var driveAmt, warmAmt, vbMix, rmSize, sampAmp, bypassMix;

    driveAmt  = drive.clip(0.0, 1.0);
    warmAmt   = warmth.clip(0.0, 1.0);
    vbMix     = reverb.clip(0.0, 1.0);
    rmSize    = room.clip(0.0, 1.0);
    sampAmp   = sampler_amp.clip(0.0, 4.0);
    bypassMix = sampler_bypass_comp.clip(0.0, 1.0);

    // Stereo source pulled from the master bus (channels 0/1).
    input = In.ar(0, 2);

    // Soft drive + warmth tilt feed into the master VCA.
    driven      = (input * (1.0 + (driveAmt * 4.0))).tanh;
    warm        = LPF.ar(driven, 18000.0 - (warmAmt * 12000.0));
    masterStage = warm * amp;

    // Sampler bus rides its own peak-normalised VCA so quieter library
    // samples retain their transients before the bus comp is applied.
    samplerStage = masterStage * sampAmp;

    // Bus compressor (gentle 1.5:1) — `sampler_bypass_comp` blends the
    // compressed and dry stages so transients can pass through cleanly
    // when set to 1.0.
    compIn      = samplerStage;
    compressed  = Compander.ar(compIn, compIn,
        thresh:     0.5,
        slopeBelow: 1.0,
        slopeAbove: 1.0 / 1.5,
        clampTime:  0.005,
        relaxTime:  0.12);
    busSig      = (compressed * (1.0 - bypassMix)) + (compIn * bypassMix);

    // Stereo plate reverb tail.
    verbWet     = FreeVerb.ar(busSig, mix: 1.0, room: rmSize, damp: 0.4);
    sig         = (busSig * (1.0 - vbMix)) + (verbWet * vbMix);

    ReplaceOut.ar(0, sig);
}).writeDefFile("synthdefs/");
)
