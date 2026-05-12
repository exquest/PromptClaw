"""Artistic identity portfolio reporting and surface snapshots.

Derives comprehensive identity summaries from repertoire data, practice
history, and growth state.  Pure functions — no I/O, no state files.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Mapping, Sequence

from .artistic_identity import ArtisticIdentity, derive_artistic_identity
from .practice_curriculum import _BLOCKS


@dataclass(frozen=True)
class PortfolioReport:
    """Full artistic identity and repertoire portfolio summary."""

    # Core identity (reuses existing derivation)
    identity: ArtisticIdentity

    # Repertoire metrics
    total_songs: int
    total_promoted: int
    preferred_forms: tuple[str, ...]
    preferred_modes: tuple[str, ...]
    signature_motif_count: int

    # Practice coverage
    practice_blocks_visited: tuple[str, ...]
    course_codes_covered: tuple[str, ...]

    # Growth metrics
    keys_explored: tuple[str, ...]
    families_explored: tuple[str, ...]

    # Ear quality averages
    avg_hook_clarity: float
    avg_cadence_strength: float
    avg_development_score: float


@dataclass(frozen=True)
class SurfaceSnapshot:
    """Data for face/operator display surfaces."""

    song_title: str
    section_caption: str
    practice_block: str
    artistic_intent: str


def _top_values(
    songs: Sequence[Mapping[str, object]],
    key: str,
    n: int = 2,
) -> tuple[str, ...]:
    """Return top-n most common non-empty string values for *key*."""
    counts: Counter[str] = Counter()
    for song in songs:
        val = str(song.get(key, "")).strip()
        if val:
            counts[val] += 1
    return tuple(name for name, _ in counts.most_common(n))


def _unique_motif_ids(songs: Sequence[Mapping[str, object]]) -> int:
    """Count unique motif IDs across all score tree summaries."""
    seen: set[str] = set()
    for song in songs:
        summary = song.get("score_tree_summary")
        if not isinstance(summary, dict):
            continue
        ids = summary.get("motif_ids")
        if isinstance(ids, (list, tuple)):
            for mid in ids:
                val = str(mid).strip()
                if val:
                    seen.add(val)
    return len(seen)


def _practice_coverage(
    songs: Sequence[Mapping[str, object]],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Return (blocks_visited, course_codes_covered) from song practice history."""
    blocks: set[str] = set()
    for song in songs:
        pb = str(song.get("practice_block", "")).strip()
        if pb:
            blocks.add(pb)
    codes: set[str] = set()
    for block_key, block in _BLOCKS.items():
        if block_key in blocks:
            codes.update(block.course_codes)
    return tuple(sorted(blocks)), tuple(sorted(codes))


def _ear_averages(
    songs: Sequence[Mapping[str, object]],
) -> tuple[float, float, float]:
    """Return (avg_hook_clarity, avg_cadence_strength, avg_development_score)."""
    hook_sum = 0.0
    cadence_sum = 0.0
    dev_sum = 0.0
    count = 0
    for song in songs:
        metrics = song.get("ear_metrics")
        if not isinstance(metrics, dict):
            continue
        has_any = False
        hc = metrics.get("hook_clarity")
        cs = metrics.get("cadence_strength")
        ds = metrics.get("development_score")
        if hc is not None or cs is not None or ds is not None:
            has_any = True
        if has_any:
            hook_sum += float(hc or 0.0)
            cadence_sum += float(cs or 0.0)
            dev_sum += float(ds or 0.0)
            count += 1
    if count == 0:
        return 0.0, 0.0, 0.0
    return hook_sum / count, cadence_sum / count, dev_sum / count


def _keys_explored(
    songs: Sequence[Mapping[str, object]],
    growth: Mapping[str, object] | None,
) -> tuple[str, ...]:
    """Extract explored keys from growth state or songs."""
    if growth is not None:
        raw = growth.get("keys_explored")
        if isinstance(raw, (list, tuple, set)):
            result = tuple(str(k) for k in raw if str(k).strip())
            if result:
                return result
    keys: set[str] = set()
    for song in songs:
        k = str(song.get("key", "")).strip()
        if k:
            keys.add(k)
    return tuple(sorted(keys))


def _families_explored(
    songs: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    """Extract unique families from songs."""
    fams: set[str] = set()
    for song in songs:
        f = str(song.get("family", "")).strip()
        if f:
            fams.add(f)
    return tuple(sorted(fams))


def derive_portfolio_report(
    songs: Sequence[Mapping[str, object]],
    *,
    promoted_songs: Sequence[Mapping[str, object]] = (),
    growth: Mapping[str, object] | None = None,
) -> PortfolioReport:
    """Build a portfolio report from repertoire and growth data."""
    identity = derive_artistic_identity(songs)
    blocks_visited, codes_covered = _practice_coverage(songs)
    avg_hc, avg_cs, avg_ds = _ear_averages(songs)

    return PortfolioReport(
        identity=identity,
        total_songs=len(songs),
        total_promoted=len(promoted_songs),
        preferred_forms=_top_values(songs, "form_class"),
        preferred_modes=_top_values(songs, "composition_mode"),
        signature_motif_count=_unique_motif_ids(songs),
        practice_blocks_visited=blocks_visited,
        course_codes_covered=codes_covered,
        keys_explored=_keys_explored(songs, growth),
        families_explored=_families_explored(songs),
        avg_hook_clarity=avg_hc,
        avg_cadence_strength=avg_cs,
        avg_development_score=avg_ds,
    )


def derive_surface_snapshot(
    *,
    current_song: Mapping[str, object] | None = None,
    identity: ArtisticIdentity | None = None,
    practice_block: str = "",
    section_function: str = "",
) -> SurfaceSnapshot:
    """Build face/operator display snapshot from current song context."""
    song_title = ""
    if current_song is not None:
        song_title = str(current_song.get("title", "")).strip()

    artistic_intent = ""
    if identity is not None:
        artistic_intent = identity.statement

    return SurfaceSnapshot(
        song_title=song_title,
        section_caption=section_function,
        practice_block=practice_block,
        artistic_intent=artistic_intent,
    )
