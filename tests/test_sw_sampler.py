"""Static tests for the sw_sampler granular SynthDef source.

depth: 2

The compiled `.scsyndef` is produced by sclang on the cypherclaw deploy host;
this dev box has no SuperCollider toolchain. These tests therefore validate the
SCD source declaratively — name, argument list, default values, signal-chain
UGens, and bus conventions — so that regressions in the source surface in CI
even when sclang isn't available.

The runtime behaviour assertions (non-silence, spectral peak near the probe
buffer's frequency, gate=0 release-tail decay) live in
`my-claw/supercollider/test_sw_sampler.scd` and run on cypherclaw.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCD_PATH = (
    REPO_ROOT
    / "my-claw"
    / "tools"
    / "senseweave"
    / "synthesis"
    / "sw_sampler.scd"
)
SC_TEST_PATH = REPO_ROOT / "my-claw" / "supercollider" / "test_sw_sampler.scd"
DEPTH: int = 2


@pytest.fixture(scope="module")
def scd_source() -> str:
    assert SCD_PATH.is_file(), f"sw_sampler.scd missing at {SCD_PATH}"
    return SCD_PATH.read_text(encoding="utf-8")


def _arg_block(source: str) -> str:
    """Extract the SynthDef argument list (between the first `|...|` pair)."""
    match = re.search(r"\|\s*([^|]+?)\s*\|", source, flags=re.DOTALL)
    assert match, "could not locate SynthDef argument list"
    return match.group(1)


def _arg_default(arg_block: str, name: str) -> float:
    pattern = rf"\b{re.escape(name)}\s*=\s*(-?\d+(?:\.\d+)?)"
    match = re.search(pattern, arg_block)
    assert match, f"argument {name!r} missing or has no default"
    return float(match.group(1))


class TestSynthDefIdentity:
    def test_synthdef_name_is_sw_sampler(self, scd_source: str) -> None:
        assert re.search(r"SynthDef\(\\sw_sampler\b", scd_source), (
            "SynthDef must be named \\sw_sampler"
        )

    def test_writes_def_file_for_compilation(self, scd_source: str) -> None:
        assert ".writeDefFile" in scd_source, (
            "SCD must invoke .writeDefFile so the .scsyndef can be compiled"
        )

    def test_writes_to_synthdefs_directory(self, scd_source: str) -> None:
        assert re.search(r"\.writeDefFile\(\s*\"synthdefs/?\"\s*\)",
                         scd_source), (
            "compiled .scsyndef must land in synthesis/synthdefs/"
        )


class TestRequiredArgsAndDefaults:
    """Acceptance criteria pin the argument names and default values."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("amp", 0.5),
            ("grain_size_ms", 80.0),
            ("density", 12.0),
            ("position", 0.0),
            ("pitch_transpose_semitones", 0.0),
            ("pitch_jitter_semitones", 0.1),
            ("attack_sec", 0.05),
            ("release_sec", 0.2),
            ("out_bus", 0.0),
            ("fx_send", 0.4),
        ],
    )
    def test_arg_default(
        self, scd_source: str, name: str, expected: float
    ) -> None:
        block = _arg_block(scd_source)
        assert _arg_default(block, name) == pytest.approx(expected)

    def test_bufnum_arg_present(self, scd_source: str) -> None:
        block = _arg_block(scd_source)
        # bufnum must be declared so SamplerDispatcher can pass /s_new bufnum N.
        assert re.search(r"\bbufnum\s*=", block), (
            "bufnum arg required so dispatch can target a specific buffer"
        )

    def test_position_rate_arg_present(self, scd_source: str) -> None:
        block = _arg_block(scd_source)
        assert re.search(r"\bposition_rate\s*=", block), (
            "position_rate arg required for buffer scrub speed"
        )

    def test_gate_arg_defaults_to_open(self, scd_source: str) -> None:
        # Sustained voice — gate must default to 1 so the synth runs until
        # the dispatcher explicitly closes it via /n_set gate 0.
        block = _arg_block(scd_source)
        assert _arg_default(block, "gate") >= 1.0, (
            "gate must default open (1) so the voice sustains until release"
        )


class TestRangeClipping:
    """Defaults sit inside acceptance ranges; clip() guards keep runtime safe."""

    def test_grain_size_clipped_to_acceptance_range(
        self, scd_source: str
    ) -> None:
        # Acceptance range for grain duration is 20..200 ms.
        assert re.search(
            r"grain_size_ms\.clip\(\s*20\.0\s*,\s*200\.0\s*\)", scd_source
        ), "grain_size_ms must clip to the [20, 200] ms acceptance range"

    def test_density_clipped(self, scd_source: str) -> None:
        # Density must be positive (Impulse.kr at 0 produces no triggers and
        # negative density is undefined) and bounded to keep CPU sane.
        assert re.search(r"density\.clip\(", scd_source), (
            "density must be clipped to a sane positive grains/sec range"
        )

    def test_position_clipped_to_unit_range(self, scd_source: str) -> None:
        assert re.search(
            r"position\.clip\(\s*0\.0\s*,\s*1\.0\s*\)", scd_source
        ), "position must clip to the normalized [0, 1] range"

    def test_fx_send_clipped_to_unit_range(self, scd_source: str) -> None:
        assert re.search(
            r"fx_send\.clip\(\s*0\.0\s*,\s*1\.0\s*\)", scd_source
        ), "fx_send must clip to [0, 1]"


class TestSignalChain:
    """All required granular stages must be present in the chain."""

    def test_grain_trigger_present(self, scd_source: str) -> None:
        assert "Impulse.kr" in scd_source, (
            "granular voice must use Impulse.kr to generate the per-grain "
            "trigger train at the requested density"
        )

    def test_grainbuf_used_for_buffer_playback(self, scd_source: str) -> None:
        assert re.search(r"GrainBuf\.ar\(", scd_source), (
            "GrainBuf.ar is required for buffered granular synthesis"
        )

    def test_grainbuf_reads_from_bufnum(self, scd_source: str) -> None:
        # The GrainBuf call must be wired to bufnum (possibly via a local var).
        assert re.search(
            r"GrainBuf\.ar\([\s\S]*?\bbufnum\b", scd_source
        ), "GrainBuf must read from the bufnum arg"

    def test_pitch_transpose_uses_midiratio(self, scd_source: str) -> None:
        # Standard SC idiom: convert semitones to a rate multiplier via
        # .midiratio so .midiratio(0) == 1.0 (no transposition).
        assert ".midiratio" in scd_source, (
            "pitch_transpose_semitones should drive a .midiratio rate"
        )

    def test_pitch_jitter_uses_per_grain_random(
        self, scd_source: str
    ) -> None:
        # Per-grain randomisation must be re-rolled on each grain trigger,
        # which is what TRand.kr (or equivalent) is for.
        assert re.search(r"TRand\.kr", scd_source), (
            "pitch jitter must be re-rolled per grain via TRand.kr"
        )

    def test_position_scrub_uses_sweep_or_phasor(
        self, scd_source: str
    ) -> None:
        # Position must advance over time at position_rate; both Sweep.ar and
        # Phasor.ar are acceptable phase sources for the scrub.
        assert re.search(r"Sweep\.ar", scd_source) or re.search(
            r"Phasor\.ar", scd_source
        ), (
            "position scrub must integrate position_rate via Sweep.ar/Phasor.ar"
        )

    def test_attack_release_envelope_present(self, scd_source: str) -> None:
        assert "Env.asr" in scd_source, (
            "attack/release envelope must use Env.asr for sustained voices"
        )
        assert re.search(
            r"EnvGen\.kr\(\s*Env\.asr\([^)]+\)\s*,\s*gate\b", scd_source
        ), (
            "EnvGen must take the gate arg so gate=0 triggers the release tail"
        )

    def test_envelope_self_frees_with_doneaction_2(
        self, scd_source: str
    ) -> None:
        assert re.search(
            r"EnvGen\.kr\([\s\S]*?doneAction\s*:\s*2", scd_source
        ), (
            "EnvGen must use doneAction: 2 so the synth self-frees once the "
            "release tail completes"
        )


class TestRoutingAndFxSend:
    """Dry path and parallel fx send must both reach the audio graph."""

    def test_dry_writes_to_out_bus(self, scd_source: str) -> None:
        assert re.search(r"Out\.ar\(\s*out_bus\s*,", scd_source), (
            "dry signal must be written to out_bus"
        )

    def test_fx_send_writes_to_fx_bus(self, scd_source: str) -> None:
        # The send must route to the dedicated sw_sampler_fx bus. Either a
        # named fx_bus arg or the literal default (16) is acceptable.
        assert re.search(r"Out\.ar\(\s*fx_bus\s*,", scd_source) or re.search(
            r"Out\.ar\(\s*16\s*,", scd_source
        ), "fx send must write to the sampler effects bus (default 16)"

    def test_fx_bus_default_is_sampler_bus(self, scd_source: str) -> None:
        block = _arg_block(scd_source)
        # If fx_bus is exposed as an arg, its default must match the global
        # sampler-fx bus convention (channels 16/17). If absent, the literal
        # 16 in Out.ar is checked above.
        match = re.search(r"\bfx_bus\s*=\s*(\d+)", block)
        if match is not None:
            assert int(match.group(1)) == 16, (
                "fx_bus default must be 16 to match sw_sampler_fx's in_bus"
            )

    def test_fx_send_scales_send_only(self, scd_source: str) -> None:
        # The dry path must not be multiplied by fx_send (parallel send
        # architecture: changing fx_send must not change dry level). We
        # check that the Out.ar(out_bus, ...) line does not reference fxAmt.
        out_match = re.search(
            r"Out\.ar\(\s*out_bus\s*,\s*([^)]+)\)", scd_source
        )
        assert out_match, "expected an Out.ar(out_bus, ...) call"
        out_arg = out_match.group(1)
        assert "fxAmt" not in out_arg and "fx_send" not in out_arg, (
            "dry write to out_bus must not be scaled by fx_send "
            "(parallel send architecture)"
        )


class TestSCSideTestExists:
    """The runtime test is the source of truth for the runtime DSP checks."""

    def test_sc_side_test_present(self) -> None:
        assert SC_TEST_PATH.is_file(), (
            f"SC-side runtime test missing at {SC_TEST_PATH}"
        )

    def test_sc_side_test_compiles_source(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert "sw_sampler.scd" in body, (
            "SC-side test must compile the source SynthDef before loading it"
        )
        assert ".load" in body or ".loadPaths" in body, (
            "SC-side test must evaluate the source .scd file"
        )

    def test_sc_side_test_renders_two_seconds(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert re.search(r"~renderDur\s*=\s*2\.0", body), (
            "SC-side test must render a 2-second clip per acceptance criteria"
        )

    def test_sc_side_test_checks_non_silence(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert "non-silent" in body, (
            "SC-side test must assert non-silence on the rendered grain cloud"
        )

    def test_sc_side_test_checks_spectral_characteristic(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        # Spectral check: the test must run an FFT and inspect bin magnitudes.
        assert ".fft(" in body, (
            "SC-side test must compute an FFT to verify spectral content"
        )
        assert "spectral peak" in body or "peakBin" in body, (
            "SC-side test must locate a spectral peak to verify pitched "
            "buffer content survives the granular voice"
        )

    def test_sc_side_test_exercises_gate_release(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert re.search(r"\\gate\s*,\s*0", body), (
            "SC-side test must close the gate (gate=0) to exercise the "
            "release tail per acceptance criteria"
        )

    def test_sc_side_test_uses_known_buffer(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        # A "known buffer" per acceptance criteria: the test must allocate and
        # populate one (e.g. with a sine) so the spectral assertion is meaningful.
        assert "Buffer.alloc" in body, (
            "SC-side test must allocate a buffer to use as the granular source"
        )
        assert "loadCollection" in body or "sineFill" in body or (
            "read" in body and ".wav" in body
        ), (
            "SC-side test must populate the source buffer with known content "
            "so spectral assertions have a reference frequency"
        )


class SwSamplerEndToEndTests:
    """End-to-end diagnostic coverage for the sw_sampler granular voice."""

    __test__ = True

    def test_sw_sampler_source_and_runtime_harness_round_trip_json_diagnostic(
        self, scd_source: str
    ) -> None:
        arg_block = _arg_block(scd_source)
        defaults = {
            name: _arg_default(arg_block, name)
            for name in (
                "bufnum",
                "amp",
                "grain_size_ms",
                "density",
                "position",
                "position_rate",
                "pitch_transpose_semitones",
                "pitch_jitter_semitones",
                "attack_sec",
                "release_sec",
                "gate",
                "out_bus",
                "fx_bus",
                "fx_send",
            )
        }

        # Strip line comments before stage-position checks so documentation
        # mentions of Out.ar / fx_send cannot mask source-order regressions.
        code = "\n".join(
            line.split("//", 1)[0] for line in scd_source.splitlines()
        )
        stage_patterns = (
            ("grain_trigger", r"\bImpulse\.kr\("),
            ("pitch_jitter", r"\bTRand\.kr\("),
            ("pitch_transpose", r"\.midiratio\b"),
            ("position_scrub", r"\b(?:Sweep|Phasor)\.ar\("),
            ("grain_buffer", r"\bGrainBuf\.ar\([\s\S]*?\bbufnum\b"),
            (
                "envelope",
                r"\bEnvGen\.kr\(\s*Env\.asr\([^)]+\)\s*,\s*gate\b"
                r"[\s\S]*?doneAction\s*:\s*2",
            ),
            ("dry_out", r"\bOut\.ar\(\s*out_bus\s*,"),
            ("fx_send_out", r"\bOut\.ar\(\s*(?:fx_bus|16)\s*,"),
        )
        stage_positions: list[dict[str, int | str]] = []
        for label, pattern in stage_patterns:
            match = re.search(pattern, code)
            assert match, f"missing integrated granular stage: {label}"
            stage_positions.append({"stage": label, "position": match.start()})

        positions = [int(item["position"]) for item in stage_positions]
        assert positions == sorted(positions), (
            f"granular stages must appear in canonical source order: "
            f"{stage_positions}"
        )

        dry_out_match = re.search(
            r"\bOut\.ar\(\s*out_bus\s*,\s*([^)]+)\)", code
        )
        assert dry_out_match, "expected an Out.ar(out_bus, ...) call"
        dry_out_arg = dry_out_match.group(1)
        assert "fxAmt" not in dry_out_arg and "fx_send" not in dry_out_arg, (
            "dry write to out_bus must not be scaled by fx_send "
            "(parallel send architecture)"
        )

        runtime_body = SC_TEST_PATH.read_text(encoding="utf-8")
        runtime_checks = {
            "compiles_source": (
                "sw_sampler.scd" in runtime_body
                and (".load" in runtime_body or ".loadPaths" in runtime_body)
            ),
            "renders_two_seconds": bool(
                re.search(r"~renderDur\s*=\s*2\.0", runtime_body)
            ),
            "asserts_non_silence": "non-silent" in runtime_body,
            "computes_fft": ".fft(" in runtime_body,
            "checks_spectral_peak": (
                "spectral peak" in runtime_body or "peakBin" in runtime_body
            ),
            "exercises_gate_release": bool(
                re.search(r"\\gate\s*,\s*0", runtime_body)
            ),
            "allocates_known_buffer": (
                "Buffer.alloc" in runtime_body
                and (
                    "loadCollection" in runtime_body
                    or "sineFill" in runtime_body
                )
            ),
        }
        assert all(runtime_checks.values()), runtime_checks

        diagnostic = {
            "synthdef": "sw_sampler",
            "source": str(SCD_PATH.relative_to(REPO_ROOT)),
            "runtime_harness": {
                "path": str(SC_TEST_PATH.relative_to(REPO_ROOT)),
                "checks": runtime_checks,
            },
            "defaults": defaults,
            "signal_chain": [label for label, _ in stage_patterns],
            "stage_positions": stage_positions,
            "parallel_send": {
                "dry_out_arg": dry_out_arg.strip(),
                "fx_send_scales_dry": False,
            },
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["synthdef"] == "sw_sampler"
        assert round_tripped["defaults"]["amp"] == pytest.approx(0.5)
        assert round_tripped["defaults"]["grain_size_ms"] == pytest.approx(80.0)
        assert round_tripped["defaults"]["density"] == pytest.approx(12.0)
        assert round_tripped["defaults"]["gate"] >= 1.0
        assert round_tripped["defaults"]["out_bus"] == pytest.approx(0.0)
        assert round_tripped["defaults"]["fx_send"] == pytest.approx(0.4)
        assert round_tripped["signal_chain"] == [
            "grain_trigger",
            "pitch_jitter",
            "pitch_transpose",
            "position_scrub",
            "grain_buffer",
            "envelope",
            "dry_out",
            "fx_send_out",
        ]
        # Exhaustive coverage (frac-0116c): the round-tripped diagnostic must
        # carry exactly the canonical fourteen-name defaults set and exactly
        # the canonical eight-stage signal chain. Set equality plus explicit
        # length rejects a regression that drops a key during serialization
        # or introduces a duplicate stage label.
        assert set(round_tripped["defaults"].keys()) == {
            "bufnum",
            "amp",
            "grain_size_ms",
            "density",
            "position",
            "position_rate",
            "pitch_transpose_semitones",
            "pitch_jitter_semitones",
            "attack_sec",
            "release_sec",
            "gate",
            "out_bus",
            "fx_bus",
            "fx_send",
        }
        assert len(round_tripped["defaults"]) == 14
        assert set(round_tripped["signal_chain"]) == {
            "grain_trigger",
            "pitch_jitter",
            "pitch_transpose",
            "position_scrub",
            "grain_buffer",
            "envelope",
            "dry_out",
            "fx_send_out",
        }
        assert len(round_tripped["signal_chain"]) == 8
        assert round_tripped["parallel_send"]["fx_send_scales_dry"] is False
        assert round_tripped["runtime_harness"]["checks"]["computes_fft"] is True
        assert (
            round_tripped["runtime_harness"]["checks"]["exercises_gate_release"]
            is True
        )
