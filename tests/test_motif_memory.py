from __future__ import annotations

import math

from cypherclaw.render.events import Event
from cypherclaw.render.rules.motif_memory import (
    MotifMemory,
    MotifMemoryRule,
    VARIATION_MENU,
    VARIATION_STRATEGIES,
)


def _make_motif(pitch_start: int = 60, role: str = "melody") -> list[Event]:
    e1 = Event(role=role)
    setattr(e1, "pitch", pitch_start)
    setattr(e1, "nominal_dur_sec", 0.5)

    e2 = Event(role=role)
    setattr(e2, "pitch", pitch_start + 2)
    setattr(e2, "nominal_dur_sec", 0.25)

    e3 = Event(role=role)
    setattr(e3, "pitch", pitch_start + 4)
    setattr(e3, "nominal_dur_sec", 0.25)
    return [e1, e2, e3]


def test_motif_memory_insert_stores_metadata() -> None:
    memory = MotifMemory(capacity=2)

    entry = memory.insert("motif-a", timestamp=10.0)

    assert entry.motif_hash == "motif-a"
    assert entry.timestamp == 10.0
    assert entry.hit_count == 1
    assert entry.decay_weight == 1.0
    assert memory.hashes() == ("motif-a",)


def test_motif_memory_lookup_updates_hit_count_timestamp_and_lru_order() -> None:
    memory = MotifMemory(capacity=2)
    memory.insert("motif-a", timestamp=1.0)
    memory.insert("motif-b", timestamp=2.0)

    entry = memory.lookup("motif-a", timestamp=3.0)

    assert entry is not None
    assert entry.hit_count == 2
    assert entry.timestamp == 3.0
    assert memory.hashes() == ("motif-b", "motif-a")


def test_motif_memory_capacity_evicts_least_recently_used() -> None:
    memory = MotifMemory(capacity=2)
    memory.insert("motif-a")
    memory.insert("motif-b")
    memory.lookup("motif-a")

    memory.insert("motif-c")

    assert len(memory) == 2
    assert memory.lookup("motif-b") is None
    assert memory.hashes() == ("motif-a", "motif-c")


def test_motif_memory_evict_returns_oldest_entry() -> None:
    memory = MotifMemory(capacity=2)
    memory.insert("motif-a")
    memory.insert("motif-b")

    evicted = memory.evict()

    assert evicted is not None
    assert evicted.motif_hash == "motif-a"
    assert memory.hashes() == ("motif-b",)


def test_motif_memory_return_home_decay_cycles_weight() -> None:
    memory = MotifMemory(capacity=1)
    memory.insert("motif-a")

    assert memory.should_return_home("motif-a", return_home_iterations=4)
    assert memory.entries["motif-a"].decay_weight == 1.0

    memory.lookup("motif-a")
    assert math.isclose(
        memory.return_home_decay("motif-a", return_home_iterations=4),
        2.0 / 3.0,
    )

    memory.lookup("motif-a")
    assert math.isclose(
        memory.return_home_decay("motif-a", return_home_iterations=4),
        1.0 / 3.0,
    )

    memory.lookup("motif-a")
    assert memory.return_home_decay("motif-a", return_home_iterations=4) == 0.0

    memory.lookup("motif-a")
    assert memory.should_return_home("motif-a", return_home_iterations=4)
    assert memory.entries["motif-a"].decay_weight == 1.0


def test_motif_memory_hashes_by_pitch_class_and_rhythm() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8)
    m1 = _make_motif(60)
    m2 = _make_motif(72)

    h1 = rule._hash_motif(m1)
    h2 = rule._hash_motif(m2)
    assert h1 == h2

    m3 = _make_motif(60)
    setattr(m3[0], "nominal_dur_sec", 0.75)
    h3 = rule._hash_motif(m3)
    assert h1 != h3


def test_motif_memory_return_home() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)
    motif = _make_motif()

    assert rule.apply(motif) == "original"

    for _ in range(2, 9):
        var = rule.apply(motif)
        assert var in VARIATION_MENU
        assert var != "original"

    assert rule.apply(motif) == "original"


def test_motif_memory_lru_decay() -> None:
    rule = MotifMemoryRule(max_cache_size=2, return_home_iterations=8)

    m1 = _make_motif(60)
    m2 = _make_motif(62)
    m3 = _make_motif(64)

    assert rule.apply(m1) == "original"
    assert rule.apply(m2) == "original"
    assert rule.apply(m3) == "original"

    assert rule.apply(m1) == "original"
    assert rule.memory.hashes() == (
        rule._hash_motif(m3),
        rule._hash_motif(m1),
    )


def test_motif_memory_role_gating() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8)

    motif = _make_motif(role="ostinato")

    for _ in range(10):
        assert rule.apply(motif) == "original"
    assert len(rule.memory) == 0


# ── Variation ranking and selection ──────────────────────────────


def test_rank_variations_returns_all_strategies_sorted_by_weight() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)
    motif = _make_motif()
    motif_hash = rule._hash_motif(motif)
    rule.memory.insert(motif_hash)

    ranking = rule.rank_variations(motif_hash)

    assert len(ranking) == len(VARIATION_STRATEGIES)
    assert {rv.strategy for rv in ranking} == set(VARIATION_STRATEGIES)
    weights = [rv.weight for rv in ranking]
    assert weights == sorted(weights, reverse=True)


def test_rank_variations_hit_count_increases_weights() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)
    motif = _make_motif()
    motif_hash = rule._hash_motif(motif)
    rule.memory.insert(motif_hash)

    low_hit_max = max(rv.weight for rv in rule.rank_variations(motif_hash))

    for _ in range(5):
        rule.memory.lookup(motif_hash)

    high_hit_max = max(rv.weight for rv in rule.rank_variations(motif_hash))

    assert high_hit_max > low_hit_max


def test_rank_variations_recency_demotes_recently_used() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)
    motif = _make_motif()
    motif_hash = rule._hash_motif(motif)
    rule.memory.insert(motif_hash)

    chosen = rule.select_variation(motif_hash)

    ranking = rule.rank_variations(motif_hash)
    recently_used = next(rv for rv in ranking if rv.strategy == chosen)
    others = [rv for rv in ranking if rv.strategy != chosen]
    assert all(rv.weight > recently_used.weight for rv in others)


def test_rank_variations_unknown_motif_returns_equal_weights() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)

    ranking = rule.rank_variations("nonexistent-hash")

    assert len(ranking) == len(VARIATION_STRATEGIES)
    weights = {rv.weight for rv in ranking}
    assert len(weights) == 1


def test_select_variation_picks_from_strategies() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)
    motif = _make_motif()
    motif_hash = rule._hash_motif(motif)
    rule.memory.insert(motif_hash)

    for _ in range(20):
        assert rule.select_variation(motif_hash) in VARIATION_STRATEGIES


def test_select_variation_updates_recency_tracking() -> None:
    rule = MotifMemoryRule(max_cache_size=10, return_home_iterations=8, seed=42)
    motif = _make_motif()
    motif_hash = rule._hash_motif(motif)
    rule.memory.insert(motif_hash)

    chosen = rule.select_variation(motif_hash)

    assert rule._strategy_last_used[chosen] == rule._strategy_counter
    assert rule._strategy_counter == 1
