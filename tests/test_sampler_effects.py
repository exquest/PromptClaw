"""Static tests for the sw_sampler_fx SynthDef source.

The compiled `.scsyndef` is produced by sclang on the cypherclaw deploy host;
this dev box has no SuperCollider toolchain. These tests therefore validate the
SCD source declaratively — name, argument list, default values, signal-chain
UGens, and bus conventions — so that regressions in the source surface in CI
even when sclang isn't available.

The runtime behaviour assertions (freeze-toggle response, non-silent output,
61.74 Hz comb peak) live in `my-claw/supercollider/test_sampler_effects.scd`
and run on cypherclaw.
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
    / "sampler_effects.scd"
)
SC_TEST_PATH = REPO_ROOT / "my-claw" / "supercollider" / "test_sampler_effects.scd"


@pytest.fixture(scope="module")
def scd_source() -> str:
    assert SCD_PATH.is_file(), f"sampler_effects.scd missing at {SCD_PATH}"
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
    def test_synthdef_name_is_sw_sampler_fx(self, scd_source: str) -> None:
        assert re.search(r"SynthDef\(\\sw_sampler_fx\b", scd_source), (
            "SynthDef must be named \\sw_sampler_fx"
        )

    def test_writes_def_file_for_compilation(self, scd_source: str) -> None:
        assert ".writeDefFile" in scd_source, (
            "SCD must invoke .writeDefFile so the .scsyndef can be compiled"
        )


class TestRequiredArgsAndDefaults:
    """Acceptance criteria pin the argument names and default values."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("delay_time", 0.5),
            ("tempo_bpm", 120.0),
            ("delay_feedback", 0.55),
            ("verb_mix", 0.35),
            ("room_size", 0.7),
            ("freeze_amount", 0.0),
            ("comb_b_amount", 0.25),
            ("comb_b_freq", 61.74),
            ("comb_decay", 4.0),
            ("comb_damping", 0.5),
        ],
    )
    def test_arg_default(
        self, scd_source: str, name: str, expected: float
    ) -> None:
        block = _arg_block(scd_source)
        assert _arg_default(block, name) == pytest.approx(expected)

    def test_in_bus_default_is_stereo_pair_at_16(self, scd_source: str) -> None:
        block = _arg_block(scd_source)
        assert _arg_default(block, "in_bus") == 16.0, (
            "convention: sampler bus is stereo at channels 16+17"
        )

    def test_out_bus_defaults_to_master(self, scd_source: str) -> None:
        block = _arg_block(scd_source)
        assert _arg_default(block, "out_bus") == 0.0


class TestRangeClipping:
    """Defaults sit inside acceptance ranges; clip() guards keep runtime safe."""

    def test_delay_time_clipped_to_tempo_window(self, scd_source: str) -> None:
        assert re.search(r"tempo_bpm\.clip\(\s*30\.0\s*,\s*240\.0\s*\)",
                         scd_source), "tempo_bpm must clip to a sane sync range"
        assert re.search(r"delay_time\.clip\(\s*quarterMeasure\s*,\s*halfMeasure\s*\)",
                         scd_source), (
            "delay_time must stay within the tempo-synced 1/4..1/2-measure window"
        )

    def test_delay_feedback_clipped_to_safe_range(self, scd_source: str) -> None:
        # 0..0.85 per acceptance criteria.
        assert re.search(r"delay_feedback\.clip\(\s*0\.0\s*,\s*0\.85\s*\)",
                         scd_source), "delay_feedback must clip to [0, 0.85]"

    def test_freeze_amount_clipped_to_unit_range(self, scd_source: str) -> None:
        assert re.search(r"freeze_amount\.clip\(\s*0\.0\s*,\s*1\.0\s*\)",
                         scd_source), "freeze_amount must clip to [0, 1]"

    def test_comb_b_amount_clipped_to_unit_range(self, scd_source: str) -> None:
        assert re.search(r"comb_b_amount\.clip\(\s*0\.0\s*,\s*1\.0\s*\)",
                         scd_source), "comb_b_amount must clip to [0, 1]"

    def test_comb_decay_clipped_to_safe_range(self, scd_source: str) -> None:
        # Negative or excessive decay times destabilise CombC; clip to a sane
        # T60 window.
        assert re.search(r"comb_decay\.clip\(\s*0\.0?5\s*,\s*10\.0\s*\)",
                         scd_source), "comb_decay must clip to a finite T60 range"

    def test_comb_damping_clipped_to_unit_range(self, scd_source: str) -> None:
        assert re.search(r"comb_damping\.clip\(\s*0\.0\s*,\s*1\.0\s*\)",
                         scd_source), "comb_damping must clip to [0, 1]"


class TestSignalChain:
    """All four required stages must be present in the chain."""

    def test_reads_stereo_input(self, scd_source: str) -> None:
        assert re.search(r"In\.ar\(\s*in_bus\s*,\s*2\s*\)", scd_source), (
            "must read 2-channel input from in_bus"
        )

    def test_writes_to_out_bus(self, scd_source: str) -> None:
        assert re.search(r"Out\.ar\(\s*out_bus\s*,", scd_source)

    def test_long_delay_stage_present(self, scd_source: str) -> None:
        assert "DelayC.ar" in scd_source or "DelayN.ar" in scd_source, (
            "delay stage missing"
        )
        # Feedback path requires a LocalIn / LocalOut pair.
        assert "LocalIn.ar" in scd_source and "LocalOut.ar" in scd_source, (
            "delay must be feedback-capable (LocalIn/LocalOut pair)"
        )

    def test_freeverb_fallback_present(self, scd_source: str) -> None:
        assert "FreeVerb.ar" in scd_source, (
            "FreeVerb fallback (no IR loaded) is required by the spec"
        )

    def test_partconv_convolution_branch_present(self, scd_source: str) -> None:
        assert "PartConv.ar" in scd_source, (
            "convolution reverb branch (PartConv) is required for the IR-loaded path"
        )

    def test_pv_freeze_stage_present(self, scd_source: str) -> None:
        assert "PV_Freeze" in scd_source, "spectral freeze stage missing"
        assert "FFT(" in scd_source and "IFFT(" in scd_source, (
            "PV_Freeze requires FFT/IFFT framing"
        )

    def test_pv_freeze_uses_toggle_derived_from_freeze_amount(
        self, scd_source: str
    ) -> None:
        match = re.search(r"\b([A-Za-z_]\w*)\s*=\s*fzAmt\s*>\s*0\.0", scd_source)
        assert match, (
            "freeze_amount must be converted into a binary toggle before it "
            "drives PV_Freeze"
        )
        toggle_var = match.group(1)
        assert re.search(
            rf"PV_Freeze\(\s*fft\s*,\s*{re.escape(toggle_var)}\s*\)",
            scd_source,
        ), (
            "PV_Freeze must be controlled by the freeze toggle so runtime "
            "parameter changes act as an on/off capture gate"
        )

    def test_freeze_amount_still_controls_wet_dry_mix(
        self, scd_source: str
    ) -> None:
        assert re.search(
            r"SelectX\.ar\(\s*fzAmt\s*,\s*\[\s*postVerb\s*,\s*freezeChain\s*\]\s*\)",
            scd_source,
        ), (
            "freeze_amount should remain the wet/dry mix control after the "
            "binary PV_Freeze gate is derived from it"
        )

    def test_comb_resonance_stage_present(self, scd_source: str) -> None:
        assert re.search(r"Comb[CLN]\.ar", scd_source), (
            "comb resonance stage missing (CombC/CombL/CombN)"
        )

    def test_comb_tuned_to_b_fundamental(self, scd_source: str) -> None:
        # Comb delay must equal 1 / comb_b_freq to tune to the B fundamental.
        # The freq value may pass through a clipped local var first.
        assert re.search(
            r"Comb[CLN]\.ar\([^)]*\.reciprocal", scd_source
        ) or re.search(
            r"Comb[CLN]\.ar\([^)]*1\s*/\s*[A-Za-z_]\w*", scd_source
        ), "comb delay must equal 1/comb_b_freq to tune to B fundamental"

    def test_comb_freq_arg_drives_comb_stage(self, scd_source: str) -> None:
        # Confirm comb_b_freq actually feeds the comb stage (directly or via
        # an intermediate clip). Walk forward from the arg to the CombC call.
        assert re.search(
            r"comb_b_freq[\s\S]*?Comb[CLN]\.ar", scd_source
        ), "comb_b_freq must be wired into the CombC stage"

    def test_comb_decay_drives_comb_decaytime(self, scd_source: str) -> None:
        # CombC's fourth positional arg is decaytime; cbDecay must reach it so
        # the runtime control actually sets T60.
        assert re.search(
            r"Comb[CLN]\.ar\([^)]*,\s*[A-Za-z_]\w*\s*\)", scd_source
        ), "CombC must receive a decaytime expression as its fourth argument"
        assert re.search(
            r"Comb[CLN]\.ar\([^)]*,\s*cbDecay\s*\)", scd_source
        ), "comb_decay (via cbDecay) must drive CombC's decaytime arg"

    def test_comb_damping_drives_post_comb_filter(self, scd_source: str) -> None:
        # Damping is realised as an LPF whose cutoff drops as cbDamp rises.
        assert "LPF.ar" in scd_source, (
            "comb damping requires an LPF stage post-comb"
        )
        assert re.search(
            r"cbDamp[\s\S]*?LPF\.ar", scd_source
        ), "comb_damping (via cbDamp) must drive an LPF cutoff after the comb"


class TestReverbBranchSelection:
    """Reverb stage must support both convolution and FreeVerb paths."""

    def test_ir_bufnum_arg_defaults_to_no_ir_sentinel(
        self, scd_source: str
    ) -> None:
        block = _arg_block(scd_source)
        # A negative default signals "no IR loaded" — BufFrames.kr returns 0
        # for an unallocated/invalid bufnum, so this gates the conv branch off.
        assert _arg_default(block, "ir_bufnum") < 0, (
            "ir_bufnum must default to a sentinel (<0) so the FreeVerb fallback "
            "is the active branch when no IR buffer has been loaded"
        )

    def test_ir_presence_check_uses_bufframes(self, scd_source: str) -> None:
        # The presence check must read live buffer state so a runtime-loaded
        # IR can flip the branch without recompiling the SynthDef.
        assert re.search(
            r"BufFrames\.(?:kr|ir)\(\s*ir_bufnum\s*\)", scd_source
        ), (
            "IR presence must be detected via BufFrames(ir_bufnum) so the "
            "branch selector reflects whether a buffer has actually been loaded"
        )

    def test_partconv_uses_guarded_bufnum(self, scd_source: str) -> None:
        # PartConv must not be fed the raw `ir_bufnum` arg — when ir_bufnum=-1
        # it would read from an invalid buffer. A guard (Select.kr or similar)
        # routes a safe sentinel buffer when no IR is loaded.
        assert re.search(
            r"PartConv\.ar\(\s*[A-Za-z_]\w*\s*,\s*[A-Za-z_]\w*\s*,\s*"
            r"(?!ir_bufnum\b)[A-Za-z_]\w*",
            scd_source,
        ), (
            "PartConv must read from a guarded bufnum (not the raw ir_bufnum) "
            "so an unallocated default doesn't drive the convolution UGen"
        )

    def test_branch_selector_keyed_on_ir_presence(self, scd_source: str) -> None:
        # The branch selector must take the IR-presence flag, with FreeVerb at
        # index 0 (no IR) and PartConv at index 1 (IR loaded). We check that
        # both UGens appear inside a single SelectX/Select array AND that the
        # presence flag is the selector input.
        match = re.search(
            r"(?:SelectX|Select)\.ar\(\s*([A-Za-z_]\w*)\s*,\s*\[([^\]]+)\]",
            scd_source,
        )
        assert match, (
            "reverb branches must be combined via SelectX.ar/Select.ar so the "
            "IR-presence flag picks between FreeVerb and PartConv at runtime"
        )
        selector_var, branch_array = match.group(1), match.group(2)
        # The selector variable must trace back to the BufFrames(ir_bufnum)
        # comparison — i.e. the variable is assigned from a BufFrames > 0 expr.
        selector_assignment = re.search(
            rf"\b{re.escape(selector_var)}\s*=\s*BufFrames\.(?:kr|ir)"
            rf"\(\s*ir_bufnum\s*\)\s*>\s*0",
            scd_source,
        )
        assert selector_assignment, (
            f"branch selector {selector_var!r} must be assigned from "
            "BufFrames(ir_bufnum) > 0 so the IR-presence check drives selection"
        )
        # Both branches must be referenced in the SelectX array. The names
        # are vars that point to FreeVerb / PartConv signals respectively.
        branch_names = [tok.strip() for tok in branch_array.split(",")]
        assert len(branch_names) == 2, (
            "reverb selector array must contain exactly two branches "
            "(fallback, convolution)"
        )
        fallback_var, conv_var = branch_names
        # Confirm fallback_var holds FreeVerb output and conv_var holds PartConv.
        fallback_assigned = re.search(
            rf"\b{re.escape(fallback_var)}\s*=\s*FreeVerb\.ar", scd_source
        )
        conv_assigned = re.search(
            rf"\b{re.escape(conv_var)}\s*=\s*PartConv\.ar", scd_source
        )
        assert fallback_assigned, (
            f"first branch {fallback_var!r} must be assigned from FreeVerb.ar "
            "so the no-IR path is the fallback at selector index 0"
        )
        assert conv_assigned, (
            f"second branch {conv_var!r} must be assigned from PartConv.ar "
            "so the IR-loaded path is the convolution branch at selector index 1"
        )


class TestStageOrdering:
    """The chain must run delay → reverb → freeze → comb (per the spec)."""

    def test_chain_ordering(self, scd_source: str) -> None:
        # Strip line comments before checking ordering, so doc-block markers
        # don't confuse the search.
        code = "\n".join(
            line.split("//", 1)[0] for line in scd_source.splitlines()
        )
        order_patterns = [
            ("DelayC.ar",   r"\bDelayC\.ar"),
            ("FreeVerb.ar", r"\bFreeVerb\.ar"),
            ("PV_Freeze",   r"\bPV_Freeze\b"),
            ("CombC.ar",    r"\bCombC\.ar"),
            ("Out.ar",      r"(?<!Local)\bOut\.ar"),
        ]
        positions = {}
        for label, pattern in order_patterns:
            match = re.search(pattern, code)
            assert match, f"missing stage marker: {label}"
            positions[label] = match.start()
        ordered = list(positions.values())
        assert ordered == sorted(ordered), (
            f"stages out of order: {positions}"
        )


class TestFullChainIntegration:
    """End-to-end assertions covering the full FX-bus chain.

    The `TestSignalChain` and `TestStageOrdering` classes verify each UGen and
    its position individually. This class is the integration view: it confirms
    the four required stages flow from `In.ar` through each FX block and into
    `Out.ar` in one continuous pass, with the new damping/decay controls wired
    into the final comb stage.
    """

    def test_full_chain_contains_all_four_fx_stages(self, scd_source: str) -> None:
        for stage in ("DelayC.ar", "FreeVerb.ar", "PV_Freeze", "CombC.ar"):
            assert stage in scd_source, f"full chain missing FX stage: {stage}"

    def test_full_chain_runs_input_through_to_output(
        self, scd_source: str
    ) -> None:
        code = "\n".join(
            line.split("//", 1)[0] for line in scd_source.splitlines()
        )
        in_match = re.search(r"\bIn\.ar\(\s*in_bus\s*,\s*2\s*\)", code)
        out_match = re.search(r"(?<!Local)\bOut\.ar\(\s*out_bus\s*,", code)
        assert in_match, "chain must start at In.ar(in_bus, 2)"
        assert out_match, "chain must terminate at Out.ar(out_bus, ...)"
        assert in_match.start() < out_match.start(), (
            "In.ar must precede Out.ar in the SynthDef body"
        )

    def test_full_chain_routes_comb_into_final_mix(
        self, scd_source: str
    ) -> None:
        # The comb tail must flow through the damping LPF and be summed with
        # postFreeze before Out.ar — that is the integrated chain endpoint.
        assert re.search(
            r"comb\s*=\s*LPF\.ar\(", scd_source
        ), "damped comb output must come from the post-comb LPF"
        assert re.search(
            r"sig\s*=\s*postFreeze\s*\+\s*\(\s*comb\s*\*\s*cbAmt\s*\)",
            scd_source,
        ), (
            "final mix must sum the post-freeze signal with the damped, "
            "amount-scaled comb tail"
        )
        assert re.search(
            r"Out\.ar\(\s*out_bus\s*,\s*sig\s*\)", scd_source
        ), "Out.ar must write the final summed `sig` to out_bus"

    def test_sc_side_test_runs_full_chain_end_to_end(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        # The SC-side runtime test is the integration harness: it must drive
        # an impulse through the full SynthDef and verify the comb peak.
        assert "runImpulseComb" in body, (
            "SC-side test must run the full chain via the runImpulseComb fork"
        )
        for stage_keyword in ("comb_b_amount", "verb_mix"):
            assert stage_keyword in body, (
                f"full-chain run must exercise {stage_keyword!r}"
            )

    def test_sc_side_test_exercises_comb_decay_and_damping(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert re.search(r"\\comb_decay\s*,", body), (
            "SC-side full-chain run must exercise the comb_decay control"
        )
        assert re.search(r"\\comb_damping\s*,", body), (
            "SC-side full-chain run must exercise the comb_damping control"
        )


class TestCompiledArtifactConvention:
    def test_writes_to_synthdefs_directory(self, scd_source: str) -> None:
        # writeDefFile path is relative to the .scd file's directory; the
        # compiled artifact must end up in synthesis/synthdefs/.
        assert re.search(r"\.writeDefFile\(\s*\"synthdefs/?\"\s*\)",
                         scd_source), (
            "compiled .scsyndef must land in synthesis/synthdefs/"
        )


class TestSCSideTestExists:
    """The runtime test is the source of truth for the runtime DSP checks."""

    def test_sc_side_test_present(self) -> None:
        assert SC_TEST_PATH.is_file(), (
            f"SC-side runtime test missing at {SC_TEST_PATH}"
        )

    def test_sc_side_test_covers_impulse_and_comb_peak(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert "Impulse" in body or "impulse" in body, (
            "SC-side test must drive an impulse"
        )
        assert "61.74" in body, (
            "SC-side test must verify the 61.74 Hz comb peak"
        )
        assert "comb_b_amount" in body, (
            "SC-side test must exercise comb_b_amount > 0"
        )

    def test_sc_side_test_covers_freeze_parameter_response(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert "freeze_amount" in body, (
            "SC-side test must exercise freeze_amount at runtime"
        )
        assert re.search(
            r"fxSyn\.set\(\s*\\freeze_amount\s*,\s*1\.0\s*\)",
            body,
        ), (
            "SC-side test must toggle freeze_amount on after startup so the "
            "freeze control response is exercised dynamically"
        )
        assert "tail RMS" in body or "late-tail RMS" in body, (
            "SC-side test must compare a late tail-energy metric to confirm "
            "the freeze toggle changes audible behaviour"
        )

    def test_sc_side_test_compiles_source(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert "sampler_effects.scd" in body, (
            "SC-side test must compile the source SynthDef before loading it"
        )
        assert ".load" in body or ".loadPaths" in body, (
            "SC-side test must evaluate the source .scd file"
        )

    def test_sc_side_test_uses_private_buses_for_routing(self) -> None:
        body = SC_TEST_PATH.read_text(encoding="utf-8")
        assert re.search(r"inBus\s*=\s*Bus\.audio", body), (
            "SC-side test must allocate a dedicated stereo input bus"
        )
        assert re.search(r"outBus\s*=\s*Bus\.audio", body), (
            "SC-side test must allocate a dedicated stereo output bus"
        )


class SamplerEffectsEndToEndTests:
    """End-to-end diagnostic coverage for the sampler effects artifacts."""

    __test__ = True

    def test_sampler_effects_source_and_runtime_harness_round_trip_json_diagnostic(
        self, scd_source: str
    ) -> None:
        arg_block = _arg_block(scd_source)
        defaults = {
            name: _arg_default(arg_block, name)
            for name in (
                "in_bus",
                "out_bus",
                "delay_time",
                "tempo_bpm",
                "delay_feedback",
                "verb_mix",
                "room_size",
                "freeze_amount",
                "comb_b_amount",
                "comb_b_freq",
                "comb_decay",
                "comb_damping",
            )
        }

        code = "\n".join(
            line.split("//", 1)[0] for line in scd_source.splitlines()
        )
        stage_patterns = (
            ("input", r"\bIn\.ar\(\s*in_bus\s*,\s*2\s*\)"),
            ("delay", r"\bDelayC\.ar"),
            ("reverb", r"\bFreeVerb\.ar"),
            ("freeze", r"\bPV_Freeze\b"),
            ("comb", r"\bCombC\.ar"),
            ("damping", r"\bLPF\.ar"),
            ("output", r"(?<!Local)\bOut\.ar\(\s*out_bus\s*,\s*sig\s*\)"),
        )
        stage_positions: list[dict[str, int | str]] = []
        for label, pattern in stage_patterns:
            match = re.search(pattern, code)
            assert match, f"missing integrated FX stage: {label}"
            stage_positions.append({"stage": label, "position": match.start()})

        positions = [int(item["position"]) for item in stage_positions]
        assert positions == sorted(positions)

        runtime_body = SC_TEST_PATH.read_text(encoding="utf-8")
        runtime_checks = {
            "compiles_source": (
                "sampler_effects.scd" in runtime_body
                and ".load" in runtime_body
            ),
            "toggles_freeze": bool(
                re.search(
                    r"fxSyn\.set\(\s*\\freeze_amount\s*,\s*1\.0\s*\)",
                    runtime_body,
                )
            ),
            "runs_impulse_comb": "runImpulseComb" in runtime_body,
            "exercises_decay": bool(re.search(r"\\comb_decay\s*,", runtime_body)),
            "exercises_damping": bool(
                re.search(r"\\comb_damping\s*,", runtime_body)
            ),
            "checks_comb_peak": "61.74" in runtime_body,
            "reports_success": "ALL TESTS PASSED" in runtime_body,
        }
        assert all(runtime_checks.values()), runtime_checks

        diagnostic = {
            "synthdef": "sw_sampler_fx",
            "source": str(SCD_PATH.relative_to(REPO_ROOT)),
            "runtime_harness": {
                "path": str(SC_TEST_PATH.relative_to(REPO_ROOT)),
                "checks": runtime_checks,
                "comb_peak_hz": defaults["comb_b_freq"],
            },
            "defaults": defaults,
            "fx_chain": [label for label, _ in stage_patterns],
            "stage_positions": stage_positions,
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped == diagnostic
        assert round_tripped["defaults"]["in_bus"] == 16.0
        assert round_tripped["defaults"]["out_bus"] == 0.0
        assert round_tripped["defaults"]["comb_b_freq"] == pytest.approx(61.74)
        assert round_tripped["fx_chain"] == [
            "input",
            "delay",
            "reverb",
            "freeze",
            "comb",
            "damping",
            "output",
        ]
        assert round_tripped["runtime_harness"]["checks"]["toggles_freeze"] is True
        assert round_tripped["runtime_harness"]["checks"]["runs_impulse_comb"] is True
