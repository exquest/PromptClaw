"""Cast planning for CypherClaw's character-driven tracker orchestration."""
from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Protocol, Sequence

CORE_ROLES = ("melody", "rhythm", "harmony")
SUPPORT_ROLES = ("foundation", "color", "texture", "counter_melody", "accent", "punctuation")

SAMPLER_SYNTH = "sw_sampler"
SAMPLER_METADATA_KEY = "sampler_sample"


class _SampleSelectorLike(Protocol):
    def select(self, *args: Any, **kwargs: Any) -> Any: ...


def _ranked_character_ids(
    all_chars: Mapping[str, Mapping[str, object]],
    cast_history: Sequence[str],
) -> list[str]:
    scores: dict[str, int] = {}
    for cid, char in all_chars.items():
        voice = char.get("voice", {})
        if not isinstance(voice, Mapping) or not voice.get("synth"):
            continue
        try:
            recency = cast_history.index(cid)
        except ValueError:
            recency = 999
        scores[cid] = recency
    return sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)


def select_cast_ids(
    all_chars: Mapping[str, Mapping[str, object]],
    cast_history: Sequence[str],
    *,
    mood_energy: float = 0.5,
    max_chars: int = 6,
    preferred_synths: Sequence[str] = (),
    voice_count_target: int | None = None,
    sample_selector: _SampleSelectorLike | None = None,
    sample_select_kwargs: Mapping[str, Any] | None = None,
    cast_metadata: MutableMapping[str, Any] | None = None,
) -> list[str]:
    """Choose a cast with core roles plus at least one support role.

    `preferred_synths` (e.g. SIGNATURE_VOICES from artist_identity) shifts
    the ranking so characters whose voice.synth is in the preferred set
    rank higher. `voice_count_target` sets the cast size directly,
    overriding the energy-based default — used by ArtistMode to enforce
    its 2/3/4-voice limits.

    When the chosen cast contains a `sw_sampler` voice and both
    `sample_selector` and `cast_metadata` are provided, this calls
    `sample_selector.select(**sample_select_kwargs)` and stores a
    minimal sample summary (`id`, `path`, `source`, `duration_sec`)
    under `cast_metadata["sampler_sample"]`. Without a sampler in the
    cast, or when either argument is omitted, `cast_metadata` is left
    untouched.
    """

    if voice_count_target is not None:
        cast_size = max(1, min(int(voice_count_target), max_chars))
    else:
        cast_size = max(4, min(8, int(2 + mood_energy * 6)))
        cast_size = min(cast_size, max_chars)
    ranked = _ranked_character_ids(all_chars, cast_history)
    if preferred_synths:
        preferred_set = set(preferred_synths)
        def _preferred_first(cid: str) -> int:
            voice = all_chars[cid].get("voice", {}) or {}
            synth = voice.get("synth", "") if isinstance(voice, Mapping) else ""
            return 0 if synth in preferred_set else 1
        ranked = sorted(ranked, key=_preferred_first)
    cast: list[str] = []
    used_roles: set[str] = set()

    for role in CORE_ROLES:
        if len(cast) >= cast_size:
            break
        for cid in ranked:
            if cid in cast:
                continue
            char = all_chars[cid]
            voice = char.get("voice", {})
            if isinstance(voice, Mapping) and voice.get("role") == role:
                cast.append(cid)
                used_roles.add(role)
                break

    for cid in ranked:
        if len(cast) >= cast_size:
            break
        if cid in cast:
            continue
        char = all_chars[cid]
        voice = char.get("voice", {})
        if isinstance(voice, Mapping) and voice.get("role") in SUPPORT_ROLES:
            cast.append(cid)
            break

    for cid in ranked:
        if len(cast) >= cast_size:
            break
        if cid not in cast:
            cast.append(cid)

    if sample_selector is not None and cast_metadata is not None:
        has_sampler = any(
            _voice_synth(all_chars[cid]) == SAMPLER_SYNTH for cid in cast
        )
        if has_sampler:
            kwargs = dict(sample_select_kwargs or {})
            sample = sample_selector.select(**kwargs)
            if sample is not None:
                cast_metadata[SAMPLER_METADATA_KEY] = _summarize_sample(sample)

    return cast


def assemble_cast(
    all_chars: Mapping[str, Mapping[str, object]],
    cast_history: Sequence[str],
    *,
    piece: object | None = None,
    mood_energy: float = 0.5,
    max_chars: int = 6,
    preferred_synths: Sequence[str] = (),
    voice_count_target: int | None = None,
    sample_selector: _SampleSelectorLike | None = None,
    sample_select_kwargs: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return assembled cast entries plus any derived cast metadata.

    `piece` is an optional piece-like mapping/object used to derive sampler
    selector kwargs (`mode`, `arc_phase`, `mood`, `target_character`) and,
    when the caller does not pass them explicitly, `preferred_synths` and
    `voice_count_target`.
    """

    resolved_preferred_synths = tuple(preferred_synths) or _string_tuple(
        _piece_value(piece, "preferred_synths")
    )
    resolved_voice_count_target = voice_count_target
    if resolved_voice_count_target is None:
        resolved_voice_count_target = _coerce_int(
            _piece_value(piece, "voice_count_target")
            or _piece_value(piece, "mode_voice_count_target")
        )

    resolved_mood_energy = mood_energy
    piece_mood = _piece_value(piece, "mood")
    if isinstance(piece_mood, Mapping):
        try:
            resolved_mood_energy = float(piece_mood.get("energy", mood_energy))
        except (TypeError, ValueError):
            resolved_mood_energy = mood_energy

    resolved_sample_select_kwargs = _sample_select_kwargs_from_piece(piece)
    if sample_select_kwargs:
        resolved_sample_select_kwargs.update(dict(sample_select_kwargs))

    metadata: dict[str, Any] = {}
    cast_ids = select_cast_ids(
        all_chars,
        cast_history,
        mood_energy=resolved_mood_energy,
        max_chars=max_chars,
        preferred_synths=resolved_preferred_synths,
        voice_count_target=resolved_voice_count_target,
        sample_selector=sample_selector,
        sample_select_kwargs=resolved_sample_select_kwargs or None,
        cast_metadata=metadata,
    )
    sampler_summary = metadata.get(SAMPLER_METADATA_KEY)
    cast = [
        _assemble_cast_entry(
            cid,
            all_chars[cid],
            sampler_summary=sampler_summary,
        )
        for cid in cast_ids
    ]
    return cast, metadata


def _voice_synth(char: Mapping[str, object]) -> str:
    voice = char.get("voice", {}) if isinstance(char, Mapping) else {}
    if not isinstance(voice, Mapping):
        return ""
    synth = voice.get("synth", "")
    return synth if isinstance(synth, str) else ""


def _piece_value(piece: object | None, key: str) -> object | None:
    if piece is None:
        return None
    metadata: object | None = None
    if isinstance(piece, Mapping):
        if key in piece:
            return piece.get(key)
        metadata = piece.get("metadata")
    else:
        if hasattr(piece, key):
            return getattr(piece, key)
        metadata = getattr(piece, "metadata", None)
    if isinstance(metadata, Mapping):
        return metadata.get(key)
    return None


def _string_tuple(raw: object) -> tuple[str, ...]:
    if isinstance(raw, str):
        value = raw.strip()
        return (value,) if value else ()
    if not isinstance(raw, Sequence):
        return ()
    values: list[str] = []
    for item in raw:
        if isinstance(item, str):
            value = item.strip()
            if value:
                values.append(value)
    return tuple(values)


def _coerce_int(raw: object) -> int | None:
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _sample_select_kwargs_from_piece(piece: object | None) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}

    mode = _piece_value(piece, "mode") or _piece_value(piece, "artist_mode")
    if isinstance(mode, str) and mode.strip():
        kwargs["mode"] = mode.strip()

    arc_phase = _piece_value(piece, "arc_phase")
    if isinstance(arc_phase, str) and arc_phase.strip():
        kwargs["arc_phase"] = arc_phase.strip()

    mood = _piece_value(piece, "mood")
    if isinstance(mood, Mapping):
        kwargs["mood"] = dict(mood)

    target_character = _string_tuple(_piece_value(piece, "target_character"))
    if not target_character:
        target_character = _string_tuple(_piece_value(piece, "patch_name"))
    if target_character:
        kwargs["target_character"] = target_character

    return kwargs


def _assemble_cast_entry(
    cid: str,
    char: Mapping[str, object],
    *,
    sampler_summary: object,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"id": cid, "char_name": cid}
    voice = char.get("voice", {}) if isinstance(char, Mapping) else {}
    if isinstance(voice, Mapping):
        entry.update(voice)
    if _voice_synth(char) == SAMPLER_SYNTH and isinstance(sampler_summary, Mapping):
        entry["sample_record"] = dict(sampler_summary)
    return entry


def _summarize_sample(sample: Any) -> dict[str, Any]:
    sample_id = getattr(sample, "sample_id", None) or getattr(sample, "id", None)
    path = getattr(sample, "path", None)
    duration_sec = getattr(sample, "duration_sec", None)
    if duration_sec is None:
        frame_count = getattr(sample, "frame_count", None)
        sample_rate = getattr(sample, "sample_rate", None)
        if isinstance(frame_count, (int, float)) and isinstance(sample_rate, (int, float)):
            if float(sample_rate) > 0.0:
                duration_sec = float(frame_count) / float(sample_rate)
    return {
        "id": sample_id,
        "path": str(path) if path is not None else None,
        "source": getattr(sample, "source", None),
        "duration_sec": duration_sec,
    }
