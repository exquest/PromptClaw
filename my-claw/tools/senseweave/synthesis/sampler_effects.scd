// sampler_effects.scd — Dedicated effects-bus SynthDef for the granular sampler.
//
// SynthDef: sw_sampler_fx
//   Reads a stereo signal from in_bus and writes the processed signal to out_bus
//   (the master bus by default). Chain order:
//
//       input -> long delay (1/4 .. 1/2 measure)
//             -> reverb     (PartConv when ir_bufnum is loaded; FreeVerb fallback)
//             -> spectral freeze (PV_Freeze)
//             -> comb resonance tuned to the B fundamental (61.74 Hz)
//                with comb_decay (T60 in seconds) and comb_damping (HF roll-off)
//             -> out_bus
//
// Bus convention: the granular sampler writes its summed grain cloud to the
// stereo bus 16 (channels 16+17). This SynthDef defaults to that bus.
//
// Compile to synthesis/synthdefs/sw_sampler_fx.scsyndef via .writeDefFile.

(
SynthDef(\sw_sampler_fx, {
    | in_bus = 16,
      out_bus = 0,
      delay_time = 0.5,
      tempo_bpm = 120.0,
      delay_feedback = 0.55,
      verb_mix = 0.35,
      room_size = 0.7,
      freeze_amount = 0.0,
      comb_b_amount = 0.25,
      comb_b_freq = 61.74,
      comb_decay = 4.0,
      comb_damping = 0.5,
      ir_bufnum = -1,
      ir_fft_size = 2048 |

    var input, dlySig, fbIn, fbOut, postDelay, verb, postVerb;
    var freezeChain, postFreeze, combRaw, comb, sig;
    var dlyTime, dlyFb, vbMix, fzAmt, fzGate, cbAmt, cbFreq, rmSize;
    var cbDecay, cbDamp, cbDampCutoff;
    var tBpm, quarterMeasure, halfMeasure;
    var irHasFrames, safeIRBuf, convReverb, freeReverb;

    // Range-clip incoming controls to keep the chain numerically stable.
    // Assume 4/4: 1/4 measure = one beat, 1/2 measure = two beats.
    tBpm = tempo_bpm.clip(30.0, 240.0);
    quarterMeasure = 60.0 / tBpm;
    halfMeasure = quarterMeasure * 2.0;
    dlyTime = delay_time.clip(quarterMeasure, halfMeasure);
    dlyFb   = delay_feedback.clip(0.0, 0.85);
    vbMix   = verb_mix.clip(0.0, 1.0);
    rmSize  = room_size.clip(0.0, 1.0);
    fzAmt   = freeze_amount.clip(0.0, 1.0);
    // PV_Freeze expects a capture gate; keep freeze_amount as the wet/dry mix.
    fzGate  = fzAmt > 0.0;
    cbAmt   = comb_b_amount.clip(0.0, 1.0);
    cbFreq  = comb_b_freq.clip(20.0, 2000.0);
    // T60 decay in seconds; capped at 0.05..10 s to avoid runaway buildup.
    cbDecay = comb_decay.clip(0.05, 10.0);
    cbDamp  = comb_damping.clip(0.0, 1.0);

    // --- Stereo input from the sampler bus ----------------------------------
    input = In.ar(in_bus, 2);

    // --- Long delay with feedback (1/4 to 1/2 measure typical) --------------
    fbIn = LocalIn.ar(2);
    dlySig = DelayC.ar(input + (fbIn * dlyFb), 4.0, dlyTime);
    LocalOut.ar(dlySig);
    postDelay = input + (dlySig * 0.5);

    // --- Reverb: convolution (PartConv) with FreeVerb fallback --------------
    // IR-buffer presence check: BufFrames.kr returns 0 for an unallocated or
    // sentinel (ir_bufnum = -1) buffer, so the convolution branch is gated on
    // its non-zero output. PartConv expects a pre-FFT'd IR buffer prepared via
    // PartConv.calcBufSize / PartConv.preProcess at the matching ir_fft_size.
    irHasFrames = BufFrames.kr(ir_bufnum) > 0;
    // Guard the bufnum fed into PartConv so an unallocated default (-1) never
    // reaches the UGen — Select.kr passes a valid sentinel (bufnum 0) instead.
    safeIRBuf   = Select.kr(irHasFrames, [DC.kr(0), ir_bufnum]);
    convReverb  = PartConv.ar(postDelay, ir_fft_size, safeIRBuf);
    freeReverb  = FreeVerb.ar(postDelay, mix: 1.0, room: rmSize, damp: 0.5);
    // SelectX.ar with a binary 0/1 selector hard-switches branches at the
    // extremes (no audible crossfade), so the fallback engages cleanly when
    // no IR is loaded and the convolution branch takes over once one is.
    verb        = SelectX.ar(irHasFrames, [freeReverb, convReverb]);
    postVerb    = (postDelay * (1.0 - vbMix)) + (verb * vbMix);

    // --- Spectral freeze (PV_Freeze) per channel ----------------------------
    freezeChain = postVerb.collect { |chan|
        var fft = FFT(LocalBuf(2048), chan);
        IFFT(PV_Freeze(fft, fzGate));
    };
    postFreeze = SelectX.ar(fzAmt, [postVerb, freezeChain]);

    // --- Comb resonance tuned to B fundamental (61.74 Hz) -------------------
    // Resonant comb at delay = 1 / cbFreq emphasises the B fundamental and its
    // harmonic series, locking the sampler's character to the room key.
    // cbDecay drives CombC's T60 decay time; cbDamp post-filters the resonance
    // with an LPF whose cutoff drops as damping rises (bright -> woody).
    combRaw = CombC.ar(postFreeze, 0.1, cbFreq.reciprocal, cbDecay);
    cbDampCutoff = ((20000.0 * (1.0 - cbDamp.squared))
                    + (cbFreq * 4.0 * cbDamp.squared))
                       .clip(cbFreq * 2.0, 20000.0);
    comb = LPF.ar(combRaw, cbDampCutoff);
    sig = postFreeze + (comb * cbAmt);

    Out.ar(out_bus, sig);
}).writeDefFile("synthdefs/");
)
