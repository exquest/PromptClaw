"""Tests for the SenseWeave render pass framework."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import Role, role_is_eligible
from cypherclaw.render.rules.motif_memory import MotifMemoryRule
from senseweave.render.pass_ import RULE_ORDER, PerformedPart, RenderPass


@dataclass(frozen=True)
class StubRule:
    rule_id: str

    def apply(
        self,
        score: Any,
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> Any:
        entry = {"rule_id": self.rule_id, "k": k, "roles": roles}
        if isinstance(score, dict) and "trace" in score:
            return {**score, "trace": [*score["trace"], entry]}
        return {"trace": [entry], "original": score}


@dataclass(frozen=True)
class NoopRule:
    rule_id: str

    def apply(
        self,
        score: Any,
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> Any:
        del k, seeds, roles
        return score


@dataclass(frozen=True)
class MicrotimingProbeRule:
    rule_id: str = "R8"

    def applies_to(
        self,
        role: str,
        metadata: Mapping[str, object] | None = None,
    ) -> bool:
        return role_is_eligible(role, metadata)

    def apply(
        self,
        score: list[Event],
        *,
        k: float,
        seeds: Mapping[str, int] | None,
        roles: frozenset[str] | None,
    ) -> list[Event]:
        del k, seeds, roles
        for event in score:
            event.timing_deviation_ms = 4.0
            event.metadata["microtiming_probe"] = "called"
        return score


def _motif(pitch_start: int = 60, role: str = "melody") -> list[Event]:
    events = [Event(role=role), Event(role=role), Event(role=role)]
    for offset, event in zip((0, 2, 4), events):
        event.pitch = pitch_start + offset  # type: ignore[attr-defined]
        event.nominal_dur_sec = 0.5  # type: ignore[attr-defined]
    return events


class TestRuleOrder:
    def test_canonical_order_is_preserved(self) -> None:
        rules = [StubRule(f"R{i}") for i in (5, 1, 12, 3)]
        rp = RenderPass(rules)
        assert rp.rule_order == ("R1", "R3", "R5", "R12")

    def test_full_stack_follows_documented_order(self) -> None:
        rules = [StubRule(rid) for rid in reversed(RULE_ORDER)]
        rp = RenderPass(rules)
        assert rp.rule_order == RULE_ORDER

    def test_non_canonical_rules_appended_in_registration_order(self) -> None:
        rules = [StubRule("custom_b"), StubRule("R2"), StubRule("custom_a")]
        rp = RenderPass(rules)
        assert rp.rule_order == ("R2", "custom_b", "custom_a")

    def test_duplicate_rule_id_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate rule id"):
            RenderPass([StubRule("R1"), StubRule("R1")])

    def test_apply_trace_matches_canonical_order(self) -> None:
        rules = [StubRule(f"R{i}") for i in (3, 1, 2)]
        rp = RenderPass(rules)
        result = rp.apply("tree")
        trace_ids = [e["rule_id"] for e in result.score["trace"]]
        assert trace_ids == ["R1", "R2", "R3"]

    def test_motif_memory_runs_as_r9_and_varies_repeated_motif(self) -> None:
        first = _motif()
        repeat = _motif()
        rp = RenderPass([NoopRule("R8"), MotifMemoryRule(seed=1), NoopRule("R10")])

        result = rp.apply([first, repeat])

        assert result.applied_rules == ("R8", "R9", "R10")
        assert first[0].metadata["motif_memory_variation"] == "original"
        assert first[0].metadata["motif_memory_repeated"] == "false"
        assert repeat[0].metadata["motif_memory_variation"] == "transposition"
        assert repeat[0].metadata["motif_memory_repeated"] == "true"
        assert repeat[0].pitch == 62  # type: ignore[attr-defined]


class TestQuantityK:
    def test_default_k_is_one(self) -> None:
        rp = RenderPass([StubRule("R1")])
        assert rp.effective_k("R1") == 1.0

    def test_k_zero_equals_rule_disabled(self) -> None:
        rp = RenderPass(
            [StubRule("R1"), StubRule("R2")],
            quantities={"R1": 0.0},
        )
        result = rp.apply("input")
        assert "R1" not in result.applied_rules
        assert "R2" in result.applied_rules
        assert result.quantities["R1"] == 0.0

    def test_k_one_equals_calibrated_default(self) -> None:
        rp = RenderPass([StubRule("R1")])
        result = rp.apply("input")
        assert result.applied_rules == ("R1",)
        assert result.score["trace"][0]["k"] == 1.0

    def test_enabled_flag_false_sets_effective_k_to_zero(self) -> None:
        rp = RenderPass(
            [StubRule("R1"), StubRule("R2")],
            enabled_flags={"R1": False},
        )
        assert rp.effective_k("R1") == 0.0
        assert rp.effective_k("R2") == 1.0
        result = rp.apply("input")
        assert "R1" not in result.applied_rules

    def test_custom_quantity_forwarded_to_rule(self) -> None:
        rp = RenderPass(
            [StubRule("R1")],
            quantities={"R1": 0.75},
        )
        result = rp.apply("input")
        assert result.score["trace"][0]["k"] == 0.75

    def test_quantity_override_at_apply_time(self) -> None:
        rp = RenderPass(
            [StubRule("R1"), StubRule("R2")],
            quantities={"R1": 0.5},
        )
        result = rp.apply("input", quantity_overrides={"R1": 0.0, "R2": 0.75})
        assert "R1" not in result.applied_rules
        assert "R2" in result.applied_rules
        assert result.quantities["R1"] == 0.0
        assert result.quantities["R2"] == 0.75

    def test_enabled_false_overridden_by_quantity_override(self) -> None:
        rp = RenderPass(
            [StubRule("R1")],
            enabled_flags={"R1": False},
        )
        result = rp.apply("input", quantity_overrides={"R1": 0.5})
        assert "R1" in result.applied_rules
        assert result.score["trace"][0]["k"] == 0.5


class TestRoleGating:
    def test_role_gate_passed_to_rule(self) -> None:
        gate = frozenset({"melody", "bass"})
        rp = RenderPass(
            [StubRule("R1")],
            role_gates={"R1": gate},
        )
        result = rp.apply("input")
        assert result.score["trace"][0]["roles"] == gate

    def test_ungated_rule_receives_none(self) -> None:
        rp = RenderPass([StubRule("R1")])
        result = rp.apply("input")
        assert result.score["trace"][0]["roles"] is None

    def test_grid_locked_role_gate_skips_microtiming_in_render_pass(self) -> None:
        event = Event(role=Role.OSTINATO)
        rp = RenderPass(
            [MicrotimingProbeRule()],
            role_gates={"R8": frozenset({Role.OSTINATO})},
        )

        result = rp.apply([event])

        assert result.applied_rules == ()
        assert event.timing_deviation_ms == 0.0
        assert "microtiming_probe" not in event.metadata


class TestApply:
    def test_returns_performed_part(self) -> None:
        rp = RenderPass([StubRule("R1")])
        result = rp.apply("tree", {"seed": 42})
        assert isinstance(result, PerformedPart)
        assert result.applied_rules == ("R1",)

    def test_empty_pass_returns_input_unchanged(self) -> None:
        rp = RenderPass([])
        result = rp.apply("raw_tree")
        assert result.score == "raw_tree"
        assert result.applied_rules == ()
        assert result.quantities == {}

    def test_seeds_forwarded_to_rules(self) -> None:
        captured: list[dict[str, int] | None] = []

        @dataclass(frozen=True)
        class SeedCapture:
            rule_id: str = "R1"

            def apply(
                self, score: Any, *, k: float, seeds: Any, roles: Any,
            ) -> Any:
                captured.append(dict(seeds) if seeds else None)
                return score

        rp = RenderPass([SeedCapture()])
        rp.apply("tree", {"comp": 7})
        assert captured == [{"comp": 7}]

    def test_metadata_defaults_to_empty(self) -> None:
        rp = RenderPass([])
        result = rp.apply("tree")
        assert result.metadata == {}


def test_render_pass_reaches_depth_two() -> None:
    from sdp.fractal import classify_depth

    result = classify_depth("my-claw/tools/senseweave/render/pass_.py")
    assert result.depth >= 2, result.reason


class RenderPassEndToEndTests:
    """End-to-end primary render-path lifecycle across the public surface."""

    __test__ = True

    def test_register_enable_quantity_gate_apply_lifecycle_is_json_safe(self) -> None:
        import json

        rules = [StubRule("R3"), StubRule("R1"), StubRule("R2")]
        role_gate = frozenset({"melody", "bass"})
        rp = RenderPass(
            rules,
            enabled_flags={"R1": False},
            quantities={"R2": 0.5},
            role_gates={"R3": role_gate},
        )

        assert rp.rule_order == ("R1", "R2", "R3")
        assert rp.effective_k("R1") == 0.0
        assert rp.effective_k("R2") == 0.5
        assert rp.effective_k("R3") == 1.0

        first = rp.apply("root", {"composition": 7})

        assert isinstance(first, PerformedPart)
        assert first.applied_rules == ("R2", "R3")
        assert first.quantities == {"R1": 0.0, "R2": 0.5, "R3": 1.0}
        assert first.metadata == {}
        assert isinstance(first.score, dict)
        assert first.score["original"] == "root"
        first_trace = first.score["trace"]
        assert [entry["rule_id"] for entry in first_trace] == ["R2", "R3"]
        assert first_trace[0]["k"] == 0.5
        assert first_trace[0]["roles"] is None
        assert first_trace[1]["k"] == 1.0
        assert first_trace[1]["roles"] == role_gate

        second = rp.apply("root", {"composition": 7}, quantity_overrides={"R1": 0.75})

        assert second.applied_rules == ("R1", "R2", "R3")
        assert second.quantities == {"R1": 0.75, "R2": 0.5, "R3": 1.0}
        second_trace = second.score["trace"]
        assert [entry["rule_id"] for entry in second_trace] == ["R1", "R2", "R3"]
        assert second_trace[0]["k"] == 0.75
        assert second_trace[0]["roles"] is None
        assert second_trace[2]["roles"] == role_gate

        def _serialize_trace(trace: list[dict[str, Any]]) -> list[dict[str, Any]]:
            return [
                {
                    "rule_id": entry["rule_id"],
                    "k": entry["k"],
                    "roles": (
                        sorted(entry["roles"])
                        if isinstance(entry["roles"], frozenset)
                        else entry["roles"]
                    ),
                }
                for entry in trace
            ]

        diagnostic = {
            "rule_order": list(rp.rule_order),
            "effective_k": {
                rid: rp.effective_k(rid) for rid in rp.rule_order
            },
            "first": {
                "applied_rules": list(first.applied_rules),
                "quantities": dict(first.quantities),
                "trace": _serialize_trace(first.score["trace"]),
                "original": first.score["original"],
                "metadata": dict(first.metadata),
            },
            "second": {
                "applied_rules": list(second.applied_rules),
                "quantities": dict(second.quantities),
                "trace": _serialize_trace(second.score["trace"]),
                "original": second.score["original"],
            },
        }
        restored = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert restored["rule_order"] == ["R1", "R2", "R3"]
        assert restored["effective_k"] == {"R1": 0.0, "R2": 0.5, "R3": 1.0}
        assert restored["first"]["applied_rules"] == ["R2", "R3"]
        assert restored["first"]["quantities"] == {"R1": 0.0, "R2": 0.5, "R3": 1.0}
        assert restored["first"]["trace"][1]["roles"] == ["bass", "melody"]
        assert restored["second"]["applied_rules"] == ["R1", "R2", "R3"]
        assert restored["second"]["trace"][0] == {
            "rule_id": "R1",
            "k": 0.75,
            "roles": None,
        }
