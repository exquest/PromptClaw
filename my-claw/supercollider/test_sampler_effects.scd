// test_sampler_effects.scd — SC-side smoke test for sw_sampler_fx.
//
// Runs on cypherclaw (where sclang/scsynth are installed). Verifies:
//   (a) The SynthDef source compiles and the .scsyndef is written.
//   (b) Toggling freeze_amount from 0 -> 1 raises late-tail RMS.
//   (c) An impulse applied to in_bus produces non-silent output on out_bus.
//   (d) When comb_b_amount > 0, the output spectrum has a peak at 61.74 Hz.
//
// Usage (from the my-claw repo root):
//   sclang my-claw/supercollider/test_sampler_effects.scd
//
// Exit codes / output:
//   - All assertions print "PASS …" lines on success.
//   - Any failure prints "FAIL …" with diagnostics; non-zero exit via 1.exit.

(
~sampleRate  = 48000;
~combPeakHz  = 61.74;
~peakTolHz   = 1.0;     // allow ±1 Hz drift from comb tuning
~impulseAmp  = 0.5;
~freezeBurstAmp = 0.35;
~freezeToggleAt = 0.06;
~renderDur   = 2.0;     // seconds
~sourcePath  = "my-claw/tools/senseweave/synthesis/sampler_effects.scd";
~defPath     = "my-claw/tools/senseweave/synthesis/synthdefs/sw_sampler_fx.scsyndef";

~assert = { |cond, label|
    if (cond) {
        ("PASS " ++ label).postln;
    } {
        ("FAIL " ++ label).postln;
        1.exit;
    };
};

~windowRms = { |arr, startSec, endSec|
    var start = (startSec * ~sampleRate).asInteger.clip(0, arr.size - 1);
    var stop = (endSec * ~sampleRate).asInteger.clip(start + 1, arr.size);
    var window = arr.copyRange(start, stop - 1);
    (((window * window).sum) / window.size.max(1)).sqrt;
};

// --- (a) Compile the source SynthDef ------------------------------------
~sourcePath.load;
~assert.(SynthDescLib.global.at(\sw_sampler_fx).notNil,
    "source SynthDef registered: " ++ ~sourcePath);
~assert.(File.exists(~defPath), "compiled scsyndef present: " ++ ~defPath);

s.waitForBoot {
    var runFreezeResponse, runImpulseComb;

    SynthDef(\test_impulse_in, { |out = 16, amp = 0.5|
        // One-sample impulse on both channels.
        var trig = Impulse.ar(0);
        Out.ar(out, [trig * amp, trig * amp]);
    }).add;

    SynthDef(\test_freeze_burst_in, { |out = 16, amp = 0.35|
        var env = EnvGen.kr(Env.linen(0.001, 0.12, 0.02), doneAction: 2);
        var sig = PinkNoise.ar(amp) * env;
        Out.ar(out, [sig, sig]);
    }).add;

    SynthDef(\test_record, { |in = 0, buf = 0|
        RecordBuf.ar(In.ar(in, 2).sum * 0.5, buf, loop: 0, doneAction: 2);
    }).add;

    s.sync;

    runFreezeResponse = { |toggleFreeze = false, onDone|
        fork {
            var inBus, outBus, recBuf, fxSyn;

            inBus  = Bus.audio(s, 2);
            outBus = Bus.audio(s, 2);
            recBuf = Buffer.alloc(s, (~sampleRate * ~renderDur).asInteger, 1);
            s.sync;

            fxSyn = Synth(\sw_sampler_fx, [\in_bus, inBus.index,
                                           \out_bus, outBus.index,
                                           \tempo_bpm, 120.0,
                                           \delay_feedback, 0.0,
                                           \verb_mix, 0.0,
                                           \comb_b_amount, 0.0,
                                           \freeze_amount, 0.0]);
            Synth.after(fxSyn, \test_record, [\in, outBus.index, \buf, recBuf]);
            Synth.before(fxSyn, \test_freeze_burst_in, [\out, inBus.index,
                                                        \amp, ~freezeBurstAmp]);

            if (toggleFreeze) {
                SystemClock.sched(~freezeToggleAt, {
                    fxSyn.set(\freeze_amount, 1.0);
                    nil;
                });
            };

            (~renderDur + 0.2).wait;
            fxSyn.free;

            recBuf.loadToFloatArray(action: { |arr|
                recBuf.free;
                inBus.free;
                outBus.free;
                onDone.(arr);
            });
        };
    };

    runImpulseComb = { |onDone|
        fork {
            var inBus, outBus, recBuf, impulseSyn, fxSyn;

            inBus  = Bus.audio(s, 2);
            outBus = Bus.audio(s, 2);
            recBuf = Buffer.alloc(s, (~sampleRate * ~renderDur).asInteger, 1);
            s.sync;

            // (c) impulse -> sampler_fx -> record path -------------------
            // Runs the full chain (delay -> reverb -> freeze -> comb) with
            // explicit comb_decay / comb_damping to exercise the new controls.
            fxSyn      = Synth(\sw_sampler_fx, [\in_bus, inBus.index,
                                                \out_bus, outBus.index,
                                                \tempo_bpm, 120.0,
                                                \comb_b_amount, 0.6,
                                                \comb_decay, 6.0,
                                                \comb_damping, 0.2,
                                                \verb_mix, 0.35]);
            Synth.after(fxSyn, \test_record, [\in, outBus.index, \buf, recBuf]);
            impulseSyn = Synth.before(fxSyn, \test_impulse_in, [\out, inBus.index,
                                                                \amp, ~impulseAmp]);

            (~renderDur + 0.2).wait;
            fxSyn.free;
            impulseSyn.free;

            recBuf.loadToFloatArray(action: { |arr|
                recBuf.free;
                inBus.free;
                outBus.free;
                onDone.(arr);
            });
        };
    };

    runFreezeResponse.(false, { |freezeOff|
        var offTail = ~windowRms.(freezeOff, 1.2, 1.8);

        runFreezeResponse.(true, { |freezeOn|
            var onTail = ~windowRms.(freezeOn, 1.2, 1.8);

            ~assert.(onTail > (offTail * 2.0).max(1.0e-4),
                "freeze toggle raises late-tail RMS "
                ++ "(off=" ++ offTail ++ ", on=" ++ onTail ++ ")");

            runImpulseComb.({ |arr|
                var peak, rms;
                var fftSize = 16384;

                peak = arr.abs.maxItem;
                rms  = ((arr * arr).sum / arr.size).sqrt;

                ~assert.(peak > 0.001, "non-silent output for impulse (peak > 1e-3)");
                ~assert.(rms  > 1.0e-5, "non-trivial RMS energy");

                // (d) Frequency-domain check: comb peak near 61.74 Hz ----
                block { |break|
                    var sig = Signal.newClear(fftSize);
                    var i = 0;
                    var cosTbl, imag, spec, binHz, targetBin, window, lo, hi;
                    var combRegion, nearbyBaseline;

                    while ({ (i < fftSize) and: { i < arr.size } }) {
                        sig[i] = arr[i]; i = i + 1;
                    };
                    cosTbl = Signal.fftCosTable(fftSize);
                    imag = Signal.newClear(fftSize);
                    spec = sig.fft(imag, cosTbl).magnitude;
                    binHz = ~sampleRate / fftSize;
                    targetBin = (~combPeakHz / binHz).round.asInteger;
                    window = (~peakTolHz / binHz).ceil.asInteger.max(1);
                    lo = (targetBin - window).max(1);
                    hi = (targetBin + window).min(spec.size - 1);
                    combRegion = spec.copyRange(lo, hi).maxItem;
                    nearbyBaseline =
                        spec.copyRange((targetBin * 4).min(spec.size - 1) - 4,
                                       (targetBin * 4).min(spec.size - 1) + 4)
                            .maxItem.max(1.0e-9);

                    ~assert.(combRegion > nearbyBaseline,
                        "61.74 Hz comb peak exceeds far-band baseline "
                        ++ "(peak=" ++ combRegion ++ ", baseline=" ++ nearbyBaseline ++ ")");
                };

                "ALL TESTS PASSED".postln;
                0.exit;
            });
        });
    });
};
)
