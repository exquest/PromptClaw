from __future__ import annotations

import collections
import hashlib
import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, is_dataclass, replace
from typing import Any, Final

from cypherclaw.render.events import Event
from cypherclaw.render.role_gate import role_is_eligible

VARIATION_MENU: Final[tuple[str, ...]] = (
    "transposition",
    "inversion",
    "retrograde",
    "rhythmic augmentation",
    "re-voicing",
    "partial fragmentation",
)

VARIATION_STRATEGIES: Final[tuple[str, ...]] = (
    "transpose",
    "invert",
    "augment",
    "diminish",
    "ornament",
)


@dataclass(frozen=True)
class RankedVariation:
    strategy: str
    weight: float


@dataclass
class MotifMemoryEntry:
    motif_hash: str
    timestamp: float
    hit_count: int = 1
    decay_weight: float = 1.0


@dataclass(frozen=True)
class _ProcessedMotif:
    items: list[Any]
    variation: str


class MotifMemory:
    """Fixed-capacity LRU cache for motif recall metadata."""

    def __init__(self, capacity: int = 16) -> None:
        if capacity < 1:
            raise ValueError("MotifMemory capacity must be positive")
        self.capacity = capacity
        self._clock = 0.0
        self._entries: collections.OrderedDict[str, MotifMemoryEntry]
        self._entries = collections.OrderedDict()

    def __contains__(self, motif_hash: object) -> bool:
        return motif_hash in self._entries

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def entries(self) -> Mapping[str, MotifMemoryEntry]:
        return self._entries

    def hashes(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def insert(
        self,
        motif_hash: str,
        *,
        timestamp: float | None = None,
    ) -> MotifMemoryEntry:
        timestamp = self._next_timestamp(timestamp)
        entry = self._entries.get(motif_hash)
        if entry is None:
            entry = MotifMemoryEntry(motif_hash=motif_hash, timestamp=timestamp)
            self._entries[motif_hash] = entry
        else:
            entry.timestamp = timestamp
            entry.hit_count += 1
            self._entries.move_to_end(motif_hash)

        while len(self._entries) > self.capacity:
            self.evict()
        return entry

    def lookup(
        self,
        motif_hash: str,
        *,
        timestamp: float | None = None,
    ) -> MotifMemoryEntry | None:
        entry = self._entries.get(motif_hash)
        if entry is None:
            return None
        entry.timestamp = self._next_timestamp(timestamp)
        entry.hit_count += 1
        self._entries.move_to_end(motif_hash)
        return entry

    def evict(self) -> MotifMemoryEntry | None:
        if not self._entries:
            return None
        _, entry = self._entries.popitem(last=False)
        return entry

    def return_home_decay(
        self,
        motif_hash: str,
        *,
        return_home_iterations: int,
    ) -> float:
        if return_home_iterations < 1:
            raise ValueError("return_home_iterations must be positive")
        entry = self._entries[motif_hash]
        phase = (entry.hit_count - 1) % return_home_iterations
        if return_home_iterations == 1:
            entry.decay_weight = 1.0
        else:
            entry.decay_weight = 1.0 - (phase / (return_home_iterations - 1))
        return entry.decay_weight

    def should_return_home(
        self,
        motif_hash: str,
        *,
        return_home_iterations: int,
    ) -> bool:
        self.return_home_decay(
            motif_hash,
            return_home_iterations=return_home_iterations,
        )
        return self._entries[motif_hash].decay_weight == 1.0

    def _next_timestamp(self, timestamp: float | None) -> float:
        if timestamp is not None:
            self._clock = max(self._clock, timestamp)
            return timestamp
        self._clock += 1.0
        return self._clock


class MotifMemoryRule:
    """R9 Motif Memory: LRU cache of motif hashes with variation menu and return-home decay."""

    rule_id = "R9"

    def __init__(
        self,
        max_cache_size: int = 16,
        return_home_iterations: int = 8,
        seed: int | None = None,
    ) -> None:
        self.max_cache_size = max_cache_size
        self.return_home_iterations = return_home_iterations
        self._rng = random.Random(seed)
        self.memory = MotifMemory(capacity=max_cache_size)

        self._variation_last_used: dict[str, int] = {v: 0 for v in VARIATION_MENU}
        self._variation_counter = 0

        self._strategy_last_used: dict[str, int] = {s: 0 for s in VARIATION_STRATEGIES}
        self._strategy_counter = 0

    def applies_to(self, role: str, metadata: Mapping[str, object] | None = None) -> bool:
        return role_is_eligible(role, metadata)

    def _hash_motif(self, events: list[Event]) -> str:
        """Hash motifs by pitch-class + rhythm signature."""
        return self._hash_items(events)

    def _hash_items(self, items: Sequence[object]) -> str:
        parts = []
        for item in items:
            pc = _numeric_attr(item, ("pitch", "midi_pitch", "pitch_midi", "scale_degree")) % 12
            dur = _numeric_attr(
                item,
                ("nominal_dur_sec", "nominal_sec", "duration_sec", "dur_sec", "length_rows"),
            )
            parts.append(f"{pc}:{dur:.3f}")
        return hashlib.sha256(",".join(parts).encode("utf-8")).hexdigest()

    def _select_variation(self) -> str:
        """Select a variation weighted inversely by recency."""
        weights = []
        for v in VARIATION_MENU:
            age = self._variation_counter - self._variation_last_used[v]
            weights.append(max(1, age))

        chosen = self._rng.choices(VARIATION_MENU, weights=weights, k=1)[0]
        self._variation_counter += 1
        self._variation_last_used[chosen] = self._variation_counter
        return chosen

    def rank_variations(self, motif_hash: str) -> list[RankedVariation]:
        """Return variation strategies ranked by weight derived from hit count and recency."""
        entry = self.memory.entries.get(motif_hash)
        hit_count = entry.hit_count if entry is not None else 0
        hit_factor = 1.0 + math.log1p(hit_count)
        ranked = []
        for strategy in VARIATION_STRATEGIES:
            age = self._strategy_counter - self._strategy_last_used[strategy]
            recency_factor = 1 + age
            weight = recency_factor * hit_factor
            ranked.append(RankedVariation(strategy=strategy, weight=weight))
        ranked.sort(key=lambda rv: rv.weight, reverse=True)
        return ranked

    def select_variation(self, motif_hash: str) -> str:
        """Pick a variation from the ranked strategies using weighted random selection."""
        ranking = self.rank_variations(motif_hash)
        strategies = [rv.strategy for rv in ranking]
        weights = [rv.weight for rv in ranking]
        chosen = self._rng.choices(strategies, weights=weights, k=1)[0]
        self._strategy_counter += 1
        self._strategy_last_used[chosen] = self._strategy_counter
        return chosen

    def apply(
        self,
        score: Any,
        *,
        k: float | None = None,
        seeds: Mapping[str, int] | None = None,
        roles: frozenset[str] | None = None,
    ) -> Any:
        """
        Apply motif memory.

        Direct calls with ``apply(events)`` preserve the original rule API and
        return the selected variation string. RenderPass calls provide ``k`` and
        receive the score back after repeated motifs are varied in-place or via
        dataclass replacement.
        """
        del seeds

        if k is None and _is_motif_sequence(score):
            return self._process_motif(
                list(score),
                role=None,
                metadata=None,
                roles=roles,
                apply_variation=False,
            ).variation

        return self._apply_to_score(score, k=1.0 if k is None else k, roles=roles)

    def _apply_to_score(
        self,
        score: Any,
        *,
        k: float,
        roles: frozenset[str] | None,
    ) -> Any:
        if k == 0.0:
            return score
        if _is_motif_sequence(score):
            processed = self._process_motif(
                list(score),
                role=None,
                metadata=None,
                roles=roles,
                apply_variation=True,
            )
            return _replace_sequence(score, processed.items)
        if _looks_like_tracker_lane(score):
            return self._apply_to_tracker_lane(score, roles=roles)
        if _has_attr(score, "scenes"):
            return _replace_or_set(
                score,
                scenes=[
                    self._apply_to_score(scene, k=k, roles=roles)
                    for scene in getattr(score, "scenes")
                ],
            )
        if _has_attr(score, "pattern"):
            return _replace_or_set(
                score,
                pattern=self._apply_to_score(getattr(score, "pattern"), k=k, roles=roles),
            )
        if _has_attr(score, "lanes"):
            return _replace_or_set(
                score,
                lanes=[
                    self._apply_to_score(lane, k=k, roles=roles)
                    for lane in getattr(score, "lanes")
                ],
            )
        if isinstance(score, list):
            for index, item in enumerate(score):
                score[index] = self._apply_to_score(item, k=k, roles=roles)
            return score
        if isinstance(score, tuple):
            return tuple(self._apply_to_score(item, k=k, roles=roles) for item in score)
        return score

    def _apply_to_tracker_lane(
        self,
        lane: Any,
        *,
        roles: frozenset[str] | None,
    ) -> Any:
        role = str(getattr(lane, "role", ""))
        metadata = _metadata_mapping(getattr(lane, "metadata", None))
        if not self._role_allowed(role, metadata, roles):
            return lane

        new_steps: list[Any] = []
        for group in _contiguous_groups(getattr(lane, "steps")):
            processed = self._process_motif(
                group,
                role=role,
                metadata=metadata,
                roles=roles,
                apply_variation=True,
            )
            new_steps.extend(processed.items)
        return _replace_or_set(lane, steps=new_steps)

    def _process_motif(
        self,
        items: Sequence[Any],
        *,
        role: str | None,
        metadata: Mapping[str, object] | None,
        roles: frozenset[str] | None,
        apply_variation: bool,
    ) -> _ProcessedMotif:
        if not items:
            return _ProcessedMotif([], "original")

        first = items[0]
        motif_role = role if role is not None else str(getattr(first, "role", ""))
        motif_metadata = metadata if metadata is not None else _metadata_mapping(
            getattr(first, "metadata", None),
        )
        if not self._role_allowed(motif_role, motif_metadata, roles):
            return _ProcessedMotif(list(items), "original")

        motif_hash = self._hash_items(items)
        entry = self.memory.lookup(motif_hash)
        repeated = entry is not None
        if entry is None:
            self.memory.insert(motif_hash)

        variation = "original"
        if repeated and not self.memory.should_return_home(
            motif_hash,
            return_home_iterations=self.return_home_iterations,
        ):
            variation = self._select_variation()
        elif not repeated:
            self.memory.should_return_home(
                motif_hash,
                return_home_iterations=self.return_home_iterations,
            )

        processed_items = list(items)
        if apply_variation and repeated and variation != "original":
            processed_items = self._apply_variation(processed_items, variation)
        processed_items = self._annotate_items(
            processed_items,
            motif_hash=motif_hash,
            variation=variation,
            repeated=repeated,
        )
        return _ProcessedMotif(processed_items, variation)

    def _role_allowed(
        self,
        role: str,
        metadata: Mapping[str, object] | None,
        roles: frozenset[str] | None,
    ) -> bool:
        if roles is not None:
            allowed_roles = {allowed.strip().lower() for allowed in roles}
            if role.strip().lower() not in allowed_roles:
                return False
        return self.applies_to(role, metadata)

    def _apply_variation(self, items: list[Any], variation: str) -> list[Any]:
        if variation == "transposition":
            return [_with_pitch_delta(item, 2.0) for item in items]
        if variation == "inversion":
            pivot = _numeric_attr(items[0], ("pitch", "midi_pitch", "pitch_midi", "scale_degree"))
            return [_with_pitch_value(item, (2.0 * pivot) - _numeric_attr(
                item,
                ("pitch", "midi_pitch", "pitch_midi", "scale_degree"),
            )) for item in items]
        if variation == "retrograde":
            sources = list(reversed(items))
            return [_with_pitch_and_duration(target, source) for target, source in zip(items, sources)]
        if variation == "rhythmic augmentation":
            return [_with_duration_factor(item, 2.0) for item in items]
        if variation == "re-voicing":
            return [_with_revoicing(item) for item in items]
        if variation == "partial fragmentation":
            return [_with_duration_factor(item, 0.5) for item in items]
        return items

    def _annotate_items(
        self,
        items: list[Any],
        *,
        motif_hash: str,
        variation: str,
        repeated: bool,
    ) -> list[Any]:
        return [
            _with_metadata(
                item,
                {
                    "motif_memory_hash": motif_hash,
                    "motif_memory_variation": variation,
                    "motif_memory_repeated": str(repeated).lower(),
                },
            )
            for item in items
        ]


def _has_attr(source: object, name: str) -> bool:
    return getattr(source, name, None) is not None


def _metadata_mapping(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _is_motif_sequence(value: object) -> bool:
    if not isinstance(value, (list, tuple)):
        return False
    return all(_is_motif_item(item) for item in value)


def _is_motif_item(value: object) -> bool:
    if isinstance(value, Event):
        return True
    has_pitch = any(hasattr(value, attr) for attr in ("pitch", "midi_pitch", "pitch_midi", "scale_degree"))
    has_duration = any(
        hasattr(value, attr)
        for attr in ("nominal_dur_sec", "nominal_sec", "duration_sec", "dur_sec", "length_rows")
    )
    return has_pitch and has_duration


def _looks_like_tracker_lane(value: object) -> bool:
    return _has_attr(value, "role") and _has_attr(value, "steps")


def _replace_sequence(original: Any, items: list[Any]) -> Any:
    if isinstance(original, tuple):
        return tuple(items)
    if isinstance(original, list):
        original[:] = items
        return original
    return items


def _replace_or_set(source: Any, **updates: Any) -> Any:
    if is_dataclass(source) and not isinstance(source, (Event, type)):
        return replace(source, **updates)
    for name, value in updates.items():
        setattr(source, name, value)
    return source


def _numeric_attr(source: object, names: tuple[str, ...]) -> float:
    for name in names:
        value = getattr(source, name, None)
        if value is not None:
            return float(value)
    return 0.0


def _first_existing_attr(source: object, names: tuple[str, ...]) -> str | None:
    for name in names:
        if hasattr(source, name):
            return name
    return None


def _coerce_like(existing: object, value: float) -> object:
    if isinstance(existing, int):
        return int(round(value))
    return value


def _with_pitch_value(item: Any, value: float) -> Any:
    attr = _first_existing_attr(item, ("pitch", "midi_pitch", "pitch_midi", "scale_degree"))
    if attr is None:
        return item
    return _replace_or_set(item, **{attr: _coerce_like(getattr(item, attr), value)})


def _with_pitch_delta(item: Any, delta: float) -> Any:
    attr = _first_existing_attr(item, ("pitch", "midi_pitch", "pitch_midi", "scale_degree"))
    if attr is None:
        return item
    return _with_pitch_value(item, float(getattr(item, attr)) + delta)


def _with_duration_factor(item: Any, factor: float) -> Any:
    updates: dict[str, object] = {}
    for attr in ("nominal_dur_sec", "nominal_sec", "duration_sec", "dur_sec", "length_rows"):
        value = getattr(item, attr, None)
        if value is None:
            continue
        scaled = float(value) * factor
        if isinstance(value, int):
            updates[attr] = max(1, int(round(scaled)))
        else:
            updates[attr] = max(0.0, scaled)
    if not updates:
        return item
    return _replace_or_set(item, **updates)


def _with_pitch_and_duration(target: Any, source: Any) -> Any:
    pitch_attr = _first_existing_attr(target, ("pitch", "midi_pitch", "pitch_midi", "scale_degree"))
    duration_attrs = (
        "nominal_dur_sec",
        "nominal_sec",
        "duration_sec",
        "dur_sec",
        "length_rows",
    )
    updates: dict[str, object] = {}
    if pitch_attr is not None:
        source_pitch = _numeric_attr(source, ("pitch", "midi_pitch", "pitch_midi", "scale_degree"))
        updates[pitch_attr] = _coerce_like(getattr(target, pitch_attr), source_pitch)
    for attr in duration_attrs:
        source_value = getattr(source, attr, None)
        target_value = getattr(target, attr, None)
        if source_value is not None and target_value is not None:
            updates[attr] = _coerce_like(target_value, float(source_value))
    if not updates:
        return target
    return _replace_or_set(target, **updates)


def _with_revoicing(item: Any) -> Any:
    octave_shift = getattr(item, "octave_shift", None)
    if octave_shift is not None:
        return _replace_or_set(item, octave_shift=int(octave_shift) + 1)
    return _with_pitch_delta(item, 12.0)


def _with_metadata(item: Any, updates: Mapping[str, str]) -> Any:
    metadata = getattr(item, "metadata", None)
    if not isinstance(metadata, dict):
        return item
    return _replace_or_set(item, metadata={**metadata, **updates})


def _phrase_group_key(step: Any) -> str:
    metadata = getattr(step, "metadata", None)
    if not isinstance(metadata, Mapping):
        return "lane"
    for key in ("motif_id", "phrase_id", "phrase_index", "repeat_cycle"):
        value = metadata.get(key)
        if value:
            return f"{key}:{value}"
    return "lane"


def _contiguous_groups(steps: Sequence[Any]) -> list[list[Any]]:
    groups: list[list[Any]] = []
    current_key: str | None = None
    current_group: list[Any] = []
    for step in steps:
        key = _phrase_group_key(step)
        if current_group and key != current_key:
            groups.append(current_group)
            current_group = []
        current_key = key
        current_group.append(step)
    if current_group:
        groups.append(current_group)
    return groups
