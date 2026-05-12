"""Mood/mode/arc-aware deterministic picker over a `SampleLibrary`.

`SampleSelector(library, rng_seed)` exposes :meth:`select` which prefers
samples whose ``arc_phase`` matches and whose ``mood`` overlaps the
target mood (dot-product over the energy/valence/arousal axes), then
falls back to character-tag matches, then to a random pick within the
mode's source preference. Per-mode rolling windows of recently played
samples are excluded via ``avoid_recent``. The same (library state,
rng_seed, kwargs) inputs always produce the same `SampleRecord`.
"""
from __future__ import annotations

import hashlib
import random
from collections import deque
from typing import Mapping, Optional, Union

from senseweave.artist_identity import ArtistMode
from senseweave.sample_library import SampleLibrary, SampleRecord


SOURCE_PREFERENCES: dict[str, tuple[str, ...]] = {
    "solitary": ("self", "contact", "room", "generated", "library"),
    "companion": ("library", "self", "room", "generated"),
    "working_ambience": ("room", "library", "generated"),
    "evening_reflection": ("self", "library", "generated", "theramini"),
    "storm": ("contact", "library", "generated", "room"),
}

MOOD_AXES: tuple[str, ...] = ("energy", "valence", "arousal")


class SampleSelector:
    """Deterministic mood/mode/arc-aware picker over a `SampleLibrary`."""

    def __init__(self, library: SampleLibrary, rng_seed: int) -> None:
        self.library = library
        self.rng_seed = int(rng_seed)
        self._recent: dict[str, deque[str]] = {}

    def select(
        self,
        mode: Union[ArtistMode, str],
        arc_phase: str,
        mood: Mapping[str, float],
        target_character: tuple[str, ...] = (),
        avoid_recent: int = 5,
    ) -> Optional[SampleRecord]:
        mode_name = mode.name if isinstance(mode, ArtistMode) else str(mode)
        preference = SOURCE_PREFERENCES.get(mode_name, ())
        if not preference:
            return None

        recent_ids = self._recent_ids(mode_name, avoid_recent)
        target_score = sum(float(mood.get(axis, 0.0)) for axis in MOOD_AXES)
        target_chars = tuple(target_character)

        # Tier 1: arc_phase + (optional) character_tags, ranked by mood overlap.
        for source in preference:
            tier1 = self._candidates(
                source=source,
                arc_phase=arc_phase,
                target_character=target_chars,
                recent_ids=recent_ids,
            )
            chosen = self._best(tier1, target_score, source, arc_phase)
            if chosen is not None:
                self._remember(mode_name, chosen.sample_id, avoid_recent)
                return chosen

        # Tier 2: character_tags only, ignore arc_phase, ranked by mood overlap.
        if target_chars:
            for source in preference:
                tier2 = self._candidates(
                    source=source,
                    arc_phase=None,
                    target_character=target_chars,
                    recent_ids=recent_ids,
                )
                chosen = self._best(tier2, target_score, source, "any")
                if chosen is not None:
                    self._remember(mode_name, chosen.sample_id, avoid_recent)
                    return chosen

        # Tier 3: random within source preference per-mode.
        for source in preference:
            tier3 = self._candidates(
                source=source,
                arc_phase=None,
                target_character=(),
                recent_ids=recent_ids,
            )
            if tier3:
                chosen = self._random_pick(tier3, source, "fallback")
                self._remember(mode_name, chosen.sample_id, avoid_recent)
                return chosen

        return None

    def _candidates(
        self,
        *,
        source: str,
        arc_phase: Optional[str],
        target_character: tuple[str, ...],
        recent_ids: frozenset[str],
    ) -> list[SampleRecord]:
        kwargs: dict[str, object] = {"source": source}
        if arc_phase is not None:
            kwargs["arc_phase"] = arc_phase
        if target_character:
            kwargs["character_any"] = list(target_character)
        rows = self.library.find(**kwargs)  # type: ignore[arg-type]
        return [r for r in rows if r.sample_id not in recent_ids]

    def _best(
        self,
        candidates: list[SampleRecord],
        target_score: float,
        *salts: str,
    ) -> Optional[SampleRecord]:
        if not candidates:
            return None
        scored = [(_overlap(r, target_score), r) for r in candidates]
        top_score = max(score for score, _ in scored)
        top = [r for score, r in scored if score == top_score]
        if len(top) == 1:
            return top[0]
        return self._random_pick(top, *salts)

    def _random_pick(
        self,
        candidates: list[SampleRecord],
        *salts: str,
    ) -> SampleRecord:
        ordered = sorted(candidates, key=lambda r: r.sample_id)
        h = hashlib.sha256()
        h.update(str(self.rng_seed).encode())
        for s in salts:
            h.update(b"\x00")
            h.update(str(s).encode())
        seed = int.from_bytes(h.digest()[:8], "big")
        return random.Random(seed).choice(ordered)

    def _recent_ids(self, mode_name: str, avoid_recent: int) -> frozenset[str]:
        if avoid_recent <= 0:
            return frozenset()
        window = self._recent.get(mode_name)
        if not window:
            return frozenset()
        return frozenset(list(window)[:avoid_recent])

    def _remember(self, mode_name: str, sample_id: str, avoid_recent: int) -> None:
        if avoid_recent <= 0:
            return
        window = self._recent.get(mode_name)
        if window is None or window.maxlen != avoid_recent:
            window = deque(window or (), maxlen=avoid_recent)
            self._recent[mode_name] = window
        try:
            window.remove(sample_id)
        except ValueError:
            pass
        window.appendleft(sample_id)


def _overlap(record: SampleRecord, target_score: float) -> float:
    if record.mood is None:
        return 0.0
    return float(record.mood) * target_score
