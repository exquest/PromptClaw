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
//             -> sum of seven per-voice FX return buses
//                (gong, pluck, bowed, bell, kotekan, choir, breath)
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
// T-042 added seven dedicated stereo FX return buses, one per voice in
// the Korsakov orchestral registry (`voice_manager_v2.VOICES`). Voices
// write their wet/aux signal to their named bus; this SynthDef sums
// those returns into the bus-comp input so each voice's effects ride
// the same glue compression and reverb tail as the dry mix. Defaults
// follow the sampler convention (stereo bus 16/17): voice FX returns
// occupy stereo pairs 18..30. Voices can override their assigned bus
// at synth-instantiation time.
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
      room = 0.5,
      fx_bus_gong = 18,
      fx_bus_pluck = 20,
      fx_bus_bowed = 22,
      fx_bus_bell = 24,
      fx_bus_kotekan = 26,
      fx_bus_choir = 28,
      fx_bus_breath = 30 |

    var input, driven, warm, masterStage, samplerStage;
    var compIn, compressed, busSig, verbWet, sig;
    var driveAmt, warmAmt, vbMix, rmSize, sampAmp, bypassMix;
    var fxGong, fxPluck, fxBowed, fxBell, fxKotekan, fxChoir, fxBreath, fxSum;

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

    // Seven dedicated per-voice stereo FX return buses (T-042). Each
    // voice in `voice_manager_v2.VOICES` writes its processed/aux signal
    // into its named bus; we sum the returns into the compressor input
    // so per-voice effects share the master glue compression and tail.
    fxGong    = In.ar(fx_bus_gong, 2);
    fxPluck   = In.ar(fx_bus_pluck, 2);
    fxBowed   = In.ar(fx_bus_bowed, 2);
    fxBell    = In.ar(fx_bus_bell, 2);
    fxKotekan = In.ar(fx_bus_kotekan, 2);
    fxChoir   = In.ar(fx_bus_choir, 2);
    fxBreath  = In.ar(fx_bus_breath, 2);
    fxSum     = fxGong + fxPluck + fxBowed + fxBell + fxKotekan + fxChoir + fxBreath;

    // Bus compressor (gentle 1.5:1) — `sampler_bypass_comp` blends the
    // compressed and dry stages so transients can pass through cleanly
    // when set to 1.0. FX returns are summed in here so they ride the
    // same compression as the dry mix.
    compIn      = samplerStage + fxSum;
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
