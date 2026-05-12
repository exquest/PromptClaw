// test_sw_sampler.scd — SC-side smoke test for the sw_sampler granular voice.
//
// Runs on cypherclaw (where sclang/scsynth are installed). Verifies:
//   (a) The SynthDef source compiles and the .scsyndef is written.
//   (b) Rendering 2 seconds from a known sine buffer produces non-silence.
//   (c) The output spectrum has a dominant peak near the sine's frequency
//       (granular reproduction of pitched material preserves pitch class).
//   (d) Setting gate=0 triggers a release tail (audible after gate close,
//       then decays toward silence within `release_sec`).
//
// Usage (from the my-claw repo root):
//   sclang my-claw/supercollider/test_sw_sampler.scd
//
// Exit codes / output:
//   - All assertions print "PASS …" lines on success.
//   - Any failure prints "FAIL …" with diagnostics; non-zero exit via 1.exit.

(
~sampleRate     = 48000;
~renderDur      = 2.0;
~probeFreqHz    = 440.0;
~peakTolHz      = 8.0;
~releaseSec     = 0.25;
~gateCloseAt    = 1.0;
~sourcePath     = "my-claw/tools/senseweave/synthesis/sw_sampler.scd";
~defPath        = "my-claw/tools/senseweave/synthesis/synthdefs/sw_sampler.scsyndef";

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
    var stop  = (endSec   * ~sampleRate).asInteger.clip(start + 1, arr.size);
    var window = arr.copyRange(start, stop - 1);
    (((window * window).sum) / window.size.max(1)).sqrt;
};

// --- (a) Compile the source SynthDef ------------------------------------
~sourcePath.load;
~assert.(SynthDescLib.global.at(\sw_sampler).notNil,
    "source SynthDef registered: " ++ ~sourcePath);
~assert.(File.exists(~defPath), "compiled scsyndef present: " ++ ~defPath);

s.waitForBoot {
    var runRender, runRelease;

    // A short stereo recorder that captures whatever lands on `in_bus` so
    // we can post-process the audio offline.
    SynthDef(\test_sampler_record, { |in = 0, buf = 0|
        RecordBuf.ar(In.ar(in, 2).sum * 0.5, buf, loop: 0, doneAction: 2);
    }).add;

    s.sync;

    runRender = { |gateCloseAt, onDone|
        fork {
            var probeBuf, recBuf, outBus, samplerSyn;
            var probeFrames = (~sampleRate * 1.0).asInteger;
            var sineWave;

            // Allocate a 1-second mono sine buffer at ~probeFreqHz so the
            // grain cloud has known spectral content to reproduce.
            probeBuf = Buffer.alloc(s, probeFrames, 1);
            sineWave = Array.fill(probeFrames, { |i|
                (2pi * ~probeFreqHz * i / ~sampleRate).sin * 0.6;
            });
            probeBuf.loadCollection(sineWave);

            outBus = Bus.audio(s, 2);
            recBuf = Buffer.alloc(s, (~sampleRate * ~renderDur).asInteger, 1);
            s.sync;

            samplerSyn = Synth(\sw_sampler, [
                \bufnum,                    probeBuf.bufnum,
                \amp,                       0.5,
                \grain_size_ms,             80.0,
                \density,                   12.0,
                \position,                  0.0,
                \position_rate,             0.5,
                \pitch_transpose_semitones, 0.0,
                \pitch_jitter_semitones,    0.0,
                \attack_sec,                0.05,
                \release_sec,               ~releaseSec,
                \gate,                      1,
                \out_bus,                   outBus.index,
                \fx_send,                   0.0
            ]);
            Synth.after(samplerSyn, \test_sampler_record,
                [\in, outBus.index, \buf, recBuf]);

            if (gateCloseAt.notNil) {
                SystemClock.sched(gateCloseAt, {
                    samplerSyn.set(\gate, 0);
                    nil;
                });
            };

            (~renderDur + 0.2).wait;
            // Synth self-frees on doneAction:2 if gate was closed; otherwise
            // free explicitly so the test is deterministic.
            samplerSyn.free;

            recBuf.loadToFloatArray(action: { |arr|
                recBuf.free;
                outBus.free;
                probeBuf.free;
                onDone.(arr);
            });
        };
    };

    // (b)+(c): render the full 2 s with gate held open the entire time.
    runRender.(nil, { |arr|
        var peak, rms;
        var fftSize = 16384;

        peak = arr.abs.maxItem;
        rms  = ((arr * arr).sum / arr.size).sqrt;
        ~assert.(peak > 0.001, "non-silent grain cloud (peak > 1e-3)");
        ~assert.(rms  > 1.0e-5, "non-trivial RMS energy");

        // Spectral characteristic: dominant magnitude bin must sit close to
        // ~probeFreqHz, confirming the granular voice reproduces the
        // buffer's pitch rather than emitting broadband noise.
        block { |break|
            var sig = Signal.newClear(fftSize);
            var i = 0;
            var cosTbl, imag, spec, binHz, peakBin, peakHz;

            while ({ (i < fftSize) and: { i < arr.size } }) {
                sig[i] = arr[i]; i = i + 1;
            };
            cosTbl = Signal.fftCosTable(fftSize);
            imag = Signal.newClear(fftSize);
            // Only inspect the lower half (Nyquist limit) for the peak bin.
            spec = sig.fft(imag, cosTbl).magnitude.copyRange(0, (fftSize / 2).asInteger - 1);
            binHz = ~sampleRate / fftSize;
            peakBin = spec.maxIndex;
            peakHz = peakBin * binHz;

            ~assert.((peakHz - ~probeFreqHz).abs < ~peakTolHz,
                "spectral peak near " ++ ~probeFreqHz ++ " Hz "
                ++ "(observed=" ++ peakHz ++ " Hz)");
        };

        // (d): same render, but close the gate mid-stream and confirm the
        // tail energy after release_sec has decayed below the in-flight RMS.
        runRender.(~gateCloseAt, { |arr2|
            var inFlight, postRelease;

            inFlight    = ~windowRms.(arr2, 0.4, ~gateCloseAt);
            postRelease = ~windowRms.(arr2,
                ~gateCloseAt + ~releaseSec + 0.2,
                ~renderDur);

            ~assert.(inFlight > 1.0e-4,
                "in-flight RMS non-zero before gate close "
                ++ "(rms=" ++ inFlight ++ ")");
            ~assert.(postRelease < (inFlight * 0.25),
                "post-release tail decays after gate=0 "
                ++ "(in_flight=" ++ inFlight
                ++ ", post_release=" ++ postRelease ++ ")");

            "ALL TESTS PASSED".postln;
            0.exit;
        });
    });
};
)
