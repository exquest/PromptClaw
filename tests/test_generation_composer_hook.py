from __future__ import annotations

import importlib
import json
import os
import sys
import types
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generation.composer_hook import (  # noqa: E402
    MIN_DAILY_BUDGET_REMAINING_USD,
    MIN_GENERATION_INTERVAL_SECONDS,
    _should_queue_now,
    build_generation_request,
)


def test_should_queue_now_allows_cold_start() -> None:
    assert _should_queue_now(
        "evening_reflection",
        {"energy": 0.6, "valence": 0.5, "arousal": 0.4},
        {"arc_payoff_score": 0.7, "daily_budget_remaining_usd": 1.0},
        now=1000.0,
        last_enqueued_at=None,
    )


def test_should_queue_now_enforces_rate_budget_and_working_gate() -> None:
    learning = {"arc_payoff_score": 0.7, "daily_budget_remaining_usd": 1.0}
    mood = {"energy": 0.6, "valence": 0.5, "arousal": 0.4}

    assert not _should_queue_now(
        "evening_reflection",
        mood,
        learning,
        now=1000.0,
        last_enqueued_at=500.0,
    )
    assert not _should_queue_now(
        "evening_reflection",
        mood,
        {"arc_payoff_score": 0.7, "daily_budget_remaining_usd": 0.5},
    )
    assert not _should_queue_now(
        "working_ambience",
        mood,
        {"arc_payoff_score": 0.2, "daily_budget_remaining_usd": 1.0},
    )


def test_should_queue_now_rate_gate_reads_last_enqueued_from_learning() -> None:
    base = {
        "arc_payoff_score": 0.7,
        "daily_budget_remaining_usd": 1.0,
    }

    too_soon = dict(base, last_generation_enqueued_at=900.0)
    assert not _should_queue_now(
        "evening_reflection",
        {"energy": 0.6},
        too_soon,
        now=1000.0,
    )

    cooled_off = dict(base, last_generation_enqueued_at=900.0)
    assert _should_queue_now(
        "evening_reflection",
        {"energy": 0.6},
        cooled_off,
        now=900.0 + 30 * 60,
    )


def test_should_queue_now_blocks_sampler_dominating_antipattern() -> None:
    assert not _should_queue_now(
        "solitary",
        {"energy": 0.6},
        {
            "arc_payoff_score": 0.8,
            "daily_budget_remaining_usd": 2.0,
            "antipatterns": [
                {"name": "sampler_dominating", "failed": True},
            ],
        },
    )


def test_build_generation_request_is_deterministic_and_json_ready() -> None:
    mood = {"energy": 0.6, "valence": 0.55, "arousal": 0.4}

    first = build_generation_request(
        mode="evening_reflection",
        arc_phase="Emergence",
        mood=mood,
        clap_centroid=[0.1, 0.2, 0.3],
    )
    second = build_generation_request(
        mode="evening_reflection",
        arc_phase="Emergence",
        mood=mood,
        clap_centroid=[0.1, 0.2, 0.3],
    )

    assert first == second
    assert len(first["request_hash"]) == 64
    assert first["mode_name"] == "evening_reflection"
    assert first["arc_phase"] == "Emergence"


def _duet_composer(monkeypatch):
    pythonosc = types.ModuleType("pythonosc")
    udp_client = types.ModuleType("pythonosc.udp_client")

    class SimpleUDPClient:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def send_message(self, *_args, **_kwargs) -> None:
            pass

    udp_client.SimpleUDPClient = SimpleUDPClient
    pythonosc.udp_client = udp_client
    monkeypatch.setitem(sys.modules, "pythonosc", pythonosc)
    monkeypatch.setitem(sys.modules, "pythonosc.udp_client", udp_client)
    module = importlib.import_module("duet_composer")
    monkeypatch.delenv("CYPHERCLAW_GENERATION_ENABLED", raising=False)
    monkeypatch.delenv("CYPHERCLAW_GENERATION_QUEUE_DB", raising=False)
    monkeypatch.setattr(module, "_generation_queue", None)
    monkeypatch.setattr(module, "_generation_conditioner", None)
    monkeypatch.setattr(module, "_conditioner", None)
    monkeypatch.setattr(module, "_generation_last_enqueued_at", None)
    return module


class _FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[object, str]] = []

    def enqueue(self, payload: object, idempotency_key: str) -> int:
        self.enqueued.append((payload, idempotency_key))
        return 42


class _FakeConditioner:
    def __init__(self, request: dict[str, object] | None = None) -> None:
        self.request = request or {"request_hash": "req-1", "prompt": "bells"}
        self.calls: list[dict[str, object]] = []

    def build_request(
        self,
        *,
        mode: object,
        arc_phase: str,
        mood: dict[str, float],
        clap_centroid: object,
        duration_sec: float,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "mode": mode,
                "arc_phase": arc_phase,
                "mood": mood,
                "clap_centroid": clap_centroid,
                "duration_sec": duration_sec,
            }
        )
        return self.request


def test_post_song_generation_hook_noops_when_phase5_disabled(monkeypatch) -> None:
    duet_composer = _duet_composer(monkeypatch)
    conditioner = _FakeConditioner()
    monkeypatch.setattr(duet_composer, "_generation_conditioner", conditioner)

    row_id = duet_composer._post_song_generation_hook(
        SimpleNamespace(metadata={"arc_phase": "Reflection"}),
        {"arc_payoff_score": 0.8, "daily_budget_remaining_usd": 2.0},
        {"energy": 0.6},
        "solitary",
        [0.1, 0.2],
    )

    assert row_id is None
    assert conditioner.calls == []


def test_post_song_generation_hook_respects_gate(monkeypatch) -> None:
    duet_composer = _duet_composer(monkeypatch)
    queue = _FakeQueue()
    conditioner = _FakeConditioner()
    monkeypatch.setattr(duet_composer, "_generation_queue", queue)
    monkeypatch.setattr(duet_composer, "_generation_conditioner", conditioner)
    gate_calls = []

    def gate(mode: object, mood: dict[str, float], learning: dict) -> bool:
        gate_calls.append((mode, mood, learning))
        return False

    monkeypatch.setattr(duet_composer, "_should_queue_now", gate)
    learning = {"arc_payoff_score": 0.8, "daily_budget_remaining_usd": 2.0}
    mood = {"energy": 0.6}

    row_id = duet_composer._post_song_generation_hook(
        SimpleNamespace(metadata={"arc_phase": "Reflection"}),
        learning,
        mood,
        "solitary",
        [0.1, 0.2],
    )

    assert row_id is None
    assert gate_calls == [("solitary", mood, learning)]
    assert conditioner.calls == []
    assert queue.enqueued == []


def test_post_song_generation_hook_builds_and_enqueues_when_gated(
    monkeypatch,
) -> None:
    duet_composer = _duet_composer(monkeypatch)
    queue = _FakeQueue()
    conditioner = _FakeConditioner({"request_hash": "req-queued", "prompt": "bells"})
    monkeypatch.setattr(duet_composer, "_generation_queue", queue)
    monkeypatch.setattr(duet_composer, "_generation_conditioner", conditioner)
    monkeypatch.setattr(duet_composer, "_should_queue_now", lambda *_args: True)
    learning = {"arc_payoff_score": 0.8, "daily_budget_remaining_usd": 2.0}
    mood = {"energy": 0.6}
    clap_centroid = [0.1, 0.2]

    row_id = duet_composer._post_song_generation_hook(
        SimpleNamespace(metadata={"arc_phase": "Reflection"}),
        learning,
        mood,
        "solitary",
        clap_centroid,
    )

    assert row_id == 42
    assert conditioner.calls == [
        {
            "mode": "solitary",
            "arc_phase": "Reflection",
            "mood": mood,
            "clap_centroid": clap_centroid,
            "duration_sec": 5.0,
        }
    ]
    assert queue.enqueued == [
        ({"request_hash": "req-queued", "prompt": "bells"}, "req-queued")
    ]


def test_post_song_generation_hook_lazy_initializes_queue(
    monkeypatch,
    tmp_path,
) -> None:
    duet_composer = _duet_composer(monkeypatch)
    queue_db = tmp_path / "generation_queue.sqlite"
    monkeypatch.setenv("CYPHERCLAW_GENERATION_ENABLED", "1")
    monkeypatch.setenv("CYPHERCLAW_GENERATION_QUEUE_DB", str(queue_db))
    monkeypatch.setattr(duet_composer, "_generation_conditioner", _FakeConditioner())
    monkeypatch.setattr(duet_composer, "_should_queue_now", lambda *_args: True)

    row_id = duet_composer._post_song_generation_hook(
        SimpleNamespace(metadata={"arc_phase": "Reflection"}),
        {"arc_payoff_score": 0.8, "daily_budget_remaining_usd": 2.0},
        {"energy": 0.6},
        "solitary",
        [0.1, 0.2],
    )

    assert row_id == 1
    assert duet_composer._generation_queue is not None
    assert queue_db.exists()


def test_post_song_generation_hook_logs_and_swallows_failures(
    monkeypatch,
    capsys,
) -> None:
    duet_composer = _duet_composer(monkeypatch)

    class BrokenQueue:
        def enqueue(self, _payload: object, _idempotency_key: str) -> int:
            raise RuntimeError("queue unavailable")

    monkeypatch.setattr(duet_composer, "_generation_queue", BrokenQueue())
    monkeypatch.setattr(duet_composer, "_generation_conditioner", _FakeConditioner())
    monkeypatch.setattr(duet_composer, "_should_queue_now", lambda *_args: True)

    row_id = duet_composer._post_song_generation_hook(
        SimpleNamespace(metadata={"arc_phase": "Reflection"}),
        {"arc_payoff_score": 0.8, "daily_budget_remaining_usd": 2.0},
        {"energy": 0.6},
        "solitary",
        [0.1, 0.2],
    )

    assert row_id is None
    assert "Generation hook skipped: queue unavailable" in capsys.readouterr().err


class _ConditionerAdapter:
    """Thin adapter that routes ``build_request`` through the real builder."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def build_request(
        self,
        *,
        mode: object,
        arc_phase: str,
        mood: dict[str, float],
        clap_centroid: object,
        duration_sec: float,
    ) -> dict[str, object]:
        self.calls.append(
            {
                "mode": mode,
                "arc_phase": arc_phase,
                "mood": dict(mood),
                "clap_centroid": list(clap_centroid)
                if isinstance(clap_centroid, (list, tuple))
                else clap_centroid,
                "duration_sec": duration_sec,
            }
        )
        return build_generation_request(
            mode=mode,
            arc_phase=arc_phase,
            mood=mood,
            clap_centroid=clap_centroid,
            duration_sec=duration_sec,
        )


class GenerationComposerHookEndToEndTests:
    """End-to-end checks for the composer-hook gating + builder + queue path."""

    __test__ = True

    def test_gate_then_build_then_enqueue_full_cycle(self, monkeypatch) -> None:
        duet_composer = _duet_composer(monkeypatch)
        queue = _FakeQueue()
        conditioner = _ConditionerAdapter()
        monkeypatch.setattr(duet_composer, "_generation_queue", queue)
        monkeypatch.setattr(duet_composer, "_generation_conditioner", conditioner)

        learning = {
            "arc_payoff_score": 0.8,
            "daily_budget_remaining_usd": 2.0,
        }
        mood = {"energy": 0.6, "valence": 0.55, "arousal": 0.4}
        clap_centroid = [0.1, 0.2, 0.3]

        gate = _should_queue_now(
            "evening_reflection",
            mood,
            learning,
            now=10_000.0,
            last_enqueued_at=None,
        )
        assert gate is True

        row_id = duet_composer._post_song_generation_hook(
            SimpleNamespace(metadata={"arc_phase": "Emergence"}),
            learning,
            mood,
            "evening_reflection",
            clap_centroid,
        )

        assert row_id == 42
        assert len(conditioner.calls) == 1
        assert conditioner.calls[0]["mode"] == "evening_reflection"
        assert conditioner.calls[0]["arc_phase"] == "Emergence"
        assert conditioner.calls[0]["duration_sec"] == 5.0

        assert len(queue.enqueued) == 1
        payload, idempotency_key = queue.enqueued[0]
        assert isinstance(payload, dict)
        assert payload["mode_name"] == "evening_reflection"
        assert payload["arc_phase"] == "Emergence"
        assert len(payload["request_hash"]) == 64
        assert idempotency_key == payload["request_hash"]

        expected = build_generation_request(
            mode="evening_reflection",
            arc_phase="Emergence",
            mood=mood,
            clap_centroid=clap_centroid,
            duration_sec=5.0,
        )
        assert payload == expected

    def test_gate_denials_short_circuit_post_song_hook(self, monkeypatch) -> None:
        duet_composer = _duet_composer(monkeypatch)
        queue = _FakeQueue()
        conditioner = _ConditionerAdapter()
        monkeypatch.setattr(duet_composer, "_generation_queue", queue)
        monkeypatch.setattr(duet_composer, "_generation_conditioner", conditioner)

        mood = {"energy": 0.6}
        clap_centroid = [0.1, 0.2]
        score = SimpleNamespace(metadata={"arc_phase": "Reflection"})

        low_budget = {
            "arc_payoff_score": 0.8,
            "daily_budget_remaining_usd": MIN_DAILY_BUDGET_REMAINING_USD,
        }
        assert not _should_queue_now("evening_reflection", mood, low_budget)
        assert (
            duet_composer._post_song_generation_hook(
                score, dict(low_budget), mood, "evening_reflection", clap_centroid
            )
            is None
        )

        sampler_dominating = {
            "arc_payoff_score": 0.8,
            "daily_budget_remaining_usd": 2.0,
            "antipatterns": [{"name": "sampler_dominating", "failed": True}],
        }
        assert not _should_queue_now("solitary", mood, sampler_dominating)
        assert (
            duet_composer._post_song_generation_hook(
                score, dict(sampler_dominating), mood, "solitary", clap_centroid
            )
            is None
        )

        low_arc = {"arc_payoff_score": 0.2, "daily_budget_remaining_usd": 2.0}
        assert not _should_queue_now("working_ambience", mood, low_arc)
        assert (
            duet_composer._post_song_generation_hook(
                score, dict(low_arc), mood, "working_ambience", clap_centroid
            )
            is None
        )

        cooled_off = MIN_GENERATION_INTERVAL_SECONDS - 1.0
        rate_limited = {
            "arc_payoff_score": 0.8,
            "daily_budget_remaining_usd": 2.0,
            "last_generation_enqueued_at": 1_000.0,
        }
        assert not _should_queue_now(
            "evening_reflection",
            mood,
            rate_limited,
            now=1_000.0 + cooled_off,
        )

        assert conditioner.calls == []
        assert queue.enqueued == []

    def test_build_generation_request_is_deterministic_and_distinct_by_inputs(
        self,
    ) -> None:
        mood = {"energy": 0.6, "valence": 0.55, "arousal": 0.4}

        first = build_generation_request(
            mode="evening_reflection",
            arc_phase="Emergence",
            mood=mood,
            clap_centroid=[0.1, 0.2, 0.3],
        )
        second = build_generation_request(
            mode="evening_reflection",
            arc_phase="Emergence",
            mood=mood,
            clap_centroid=[0.1, 0.2, 0.3],
        )
        different_phase = build_generation_request(
            mode="evening_reflection",
            arc_phase="Reflection",
            mood=mood,
            clap_centroid=[0.1, 0.2, 0.3],
        )
        different_mode = build_generation_request(
            mode="working_ambience",
            arc_phase="Emergence",
            mood=mood,
            clap_centroid=[0.1, 0.2, 0.3],
        )

        assert first == second
        assert first["request_hash"] != different_phase["request_hash"]
        assert first["request_hash"] != different_mode["request_hash"]
        assert first["seed"] != different_phase["seed"]

    def test_built_request_is_json_safe_round_trip(self) -> None:
        request = build_generation_request(
            mode="evening_reflection",
            arc_phase="Emergence",
            mood={"energy": 0.6, "valence": 0.55, "arousal": 0.4},
            clap_centroid=[0.1, 0.2, 0.3],
        )

        encoded = json.dumps(request, sort_keys=True)
        decoded = json.loads(encoded)

        assert decoded == request
        assert decoded["mode_name"] == "evening_reflection"
        assert decoded["arc_phase"] == "Emergence"
        assert decoded["backend"] == "replicate"
        assert decoded["model"] == "musicgen-medium"
        assert decoded["duration_sec"] == 5.0
        assert isinstance(decoded["seed"], int)
        assert isinstance(decoded["prompt"], str)
        assert "evening reflection" in decoded["prompt"]

    def test_full_cycle_uses_real_gate_and_real_builder_against_queue(
        self, monkeypatch
    ) -> None:
        duet_composer = _duet_composer(monkeypatch)
        queue = _FakeQueue()
        conditioner = _ConditionerAdapter()
        monkeypatch.setattr(duet_composer, "_generation_queue", queue)
        monkeypatch.setattr(duet_composer, "_generation_conditioner", conditioner)

        mood = {"energy": 0.6, "valence": 0.55, "arousal": 0.4}
        clap_centroid = [0.1, 0.2, 0.3]
        learning = {
            "arc_payoff_score": 0.8,
            "daily_budget_remaining_usd": 2.0,
        }

        row_id = duet_composer._post_song_generation_hook(
            SimpleNamespace(metadata={"arc_phase": "Emergence"}),
            dict(learning),
            mood,
            "evening_reflection",
            clap_centroid,
        )

        assert row_id == 42
        assert len(queue.enqueued) == 1
        payload, key = queue.enqueued[0]
        assert isinstance(payload, dict)
        assert json.loads(json.dumps(payload, sort_keys=True)) == payload
        assert key == payload["request_hash"]
        assert payload["mode_name"] == "evening_reflection"
        assert payload["arc_phase"] == "Emergence"
