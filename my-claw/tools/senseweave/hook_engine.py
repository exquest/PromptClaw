"""Hook and phrase-pair planning for CypherClaw songs."""
from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True)
class HookProfile:
    title: str
    text_hook: str
    hook_class: str
    contour: tuple[int, ...]
    rhythm: tuple[float, ...]
    timbral_tags: tuple[str, ...]
    groove_family: str
    anchor_degrees: tuple[int, ...]
    answer_degrees: tuple[int, ...]
    section_intent: str


@dataclass(frozen=True)
class _TitlePhrase:
    modifier: str
    noun: str
    cadence_tags: tuple[str, ...] = ()
    profile_tags: tuple[str, ...] = ()
    hook_tags: tuple[str, ...] = ()


_HOOK_TYPES: dict[str, tuple[str, ...]] = {
    "nocturne": ("contour", "lyric"),
    "ember": ("lyric", "contour", "rhythmic"),
    "drift": ("contour", "lyric"),
    "bloom": ("rhythmic", "contour", "interval"),
    "pulse": ("rhythmic", "interval", "contour"),
    "forge": ("interval", "rhythmic", "contour"),
    "default": ("contour", "rhythmic", "lyric"),
}


_HOOK_CONTOURS = {
    "contour": (1, 3, 5, 3),
    "rhythmic": (1, 1, 5, 3),
    "lyric": (1, 2, 3, 5),
    "interval": (1, 5, 3, 6),
}

_RHYTHM_BY_GROOVE = {
    "lyric": (1.0, 1.0, 1.0, 1.0),
    "rolling": (0.75, 0.75, 1.0, 1.5),
    "suspended": (2.0, 2.0, 4.0),
    "procession": (1.5, 0.5, 1.0, 1.0),
    "study": (0.5, 0.5, 1.0, 1.0, 1.0),
}

_TIMBRAL_TAGS = {
    "nocturne": ("dark", "soft", "glass"),
    "ember": ("warm", "close", "wood"),
    "drift": ("hollow", "wandering", "breath"),
    "bloom": ("bright", "open", "bell"),
    "pulse": ("kinetic", "electric", "wire"),
    "forge": ("bent", "metallic", "edge"),
    "default": ("clear", "steady"),
}

_HOOK_ANCHORS: dict[str, tuple[tuple[int, ...], ...]] = {
    "contour": ((1, 3, 5, 3), (1, 4, 5, 3), (3, 5, 6, 5)),
    "rhythmic": ((1, 1, 5, 3), (1, 5, 5, 3), (3, 3, 5, 1)),
    "lyric": ((1, 2, 3, 5), (1, 3, 2, 5), (3, 2, 1, 3)),
    "interval": ((1, 5, 3, 6), (1, 6, 4, 5), (3, 7, 5, 6)),
}

_GROOVE_BY_FAMILY = {
    "nocturne": "suspended",
    "ember": "lyric",
    "drift": "rolling",
    "bloom": "rolling",
    "pulse": "procession",
    "forge": "study",
    "default": "lyric",
}

_SECTION_INTENT = {
    "sleep": "hush then release",
    "wind_down": "soften and settle",
    "wake_ramp": "gather and rise",
    "occupied_day": "open and answer",
    "away_practice": "study and transform",
}

_TITLE_MODIFIERS = {
    "nocturne": ("Quiet", "Faded", "Night", "Slow"),
    "ember": ("Warm", "Small", "Red", "Held"),
    "drift": ("Soft", "Wandering", "Low", "Silver"),
    "bloom": ("Open", "Glass", "Garden", "Bright"),
    "pulse": ("Moving", "Electric", "Processional", "Day"),
    "forge": ("Bent", "Strange", "Arc", "Hidden"),
    "default": ("Quiet", "Open", "Near", "Held"),
}

_TITLE_NOUNS = {
    "sleep": ("Rooms", "Signals", "Lamps", "Machines"),
    "wind_down": ("Windows", "Breath", "Threads", "Rain"),
    "wake_ramp": ("Stairs", "Kitchen", "Hands", "Light"),
    "occupied_day": ("Figures", "Rooms", "Patterns", "Machines"),
    "away_practice": ("Workshop", "Circuit", "Studies", "Engines"),
}

_HOOK_LINES = {
    "sleep": ("hold the dark", "let it soften", "keep the room low"),
    "wind_down": ("hold the light", "let it settle", "stay with the room"),
    "wake_ramp": ("wake the room", "follow the light", "gather the day"),
    "occupied_day": ("hold the light", "keep the line open", "answer the room"),
    "away_practice": ("bend the pattern", "follow the wire", "test the edges"),
}

_HOOK_IMAGE_FIELDS = {
    "hold the dark": "dark",
    "let the dark breathe": "dark",
    "leave the dark wide": "dark",
    "let it soften": "dark",
    "keep the room low": "room",
    "leave the room low": "room",
    "let the room breathe low": "room",
    "keep the room breathing": "room",
    "hold the light": "light",
    "carry the light": "light",
    "let the light hover": "light",
    "leave the light wide": "light",
    "follow the light": "light",
    "let the light lead": "light",
    "move with the light": "light",
    "wake the room": "room",
    "gather the room": "room",
    "lift the room slowly": "room",
    "wake the room gently": "room",
    "keep the room open": "room",
    "let the room answer": "room",
    "leave the room awake": "room",
    "answer the room": "room",
    "stay with the room": "room",
    "keep with the room": "room",
    "listen with the room": "room",
    "keep the line open": "line",
    "leave the line open": "line",
    "let the line ring": "line",
    "let the line widen": "line",
    "bend the pattern": "pattern",
    "turn the pattern": "pattern",
    "tilt the pattern": "pattern",
    "let the pattern break": "pattern",
    "follow the wire": "wire",
    "trace the wire": "wire",
    "keep to the wire": "wire",
    "let the wire lead": "wire",
    "test the edges": "edge",
    "trace the edges": "edge",
    "lean on the edges": "edge",
    "let the edges answer": "edge",
    "gather the day": "day",
    "open the day": "day",
    "let the day arrive": "day",
    "carry the day in": "day",
}

_IMAGE_FIELD_NOUNS = {
    "dark": ("Night", "Lamps", "Shadow", "Dark"),
    "light": ("Light", "Lamps", "Windows", "Glass"),
    "room": ("Rooms", "Windows", "Corners", "Thresholds"),
    "line": ("Lines", "Threads", "Wires", "Circuits"),
    "pattern": ("Patterns", "Figures", "Circuits", "Studies"),
    "wire": ("Wires", "Circuits", "Signals", "Engines"),
    "edge": ("Edges", "Corners", "Signals", "Thresholds"),
    "day": ("Day", "Stairs", "Hands", "Kitchen"),
}

_IMAGE_FIELD_MODIFIERS = {
    "dark": ("Quiet", "Faded", "Night", "Low"),
    "light": ("Bright", "Clear", "Pale", "Glass"),
    "room": ("Open", "Quiet", "Near", "Inner"),
    "line": ("Open", "Bright", "Fine", "Electric"),
    "pattern": ("Bent", "Hidden", "Shifting", "Broken"),
    "wire": ("Live", "Bright", "Electric", "Wired"),
    "edge": ("Sharp", "Outer", "Bent", "Hidden"),
    "day": ("Early", "Open", "Morning", "Moving"),
}

_IMAGE_FIELD_TITLE_PHRASES: dict[str, tuple[_TitlePhrase, ...]] = {
    "dark": (
        _TitlePhrase("Quiet", "Shadow", ("sleep", "wind_down"), ("settling", "stillness")),
        _TitlePhrase("Faded", "Lamps", ("sleep", "wind_down"), ("settling", "stillness")),
        _TitlePhrase("Low", "Night", ("sleep", "wind_down"), ("settling", "stillness")),
        _TitlePhrase("Quiet", "Night", ("sleep", "wind_down"), ("open_day",)),
    ),
    "light": (
        _TitlePhrase("Bright", "Glass", ("wake_ramp", "occupied_day"), ("open_day", "lift")),
        _TitlePhrase("Clear", "Windows", ("wake_ramp", "occupied_day"), ("open_day", "lift"), ("rhythmic", "contour")),
        _TitlePhrase("Pale", "Lamps", ("sleep", "wind_down"), ("settling", "stillness"), ("lyric", "contour")),
        _TitlePhrase("Low", "Light", ("sleep", "wind_down"), ("settling", "stillness"), ("lyric", "contour")),
        _TitlePhrase("Quiet", "Glass", ("wind_down",), ("settling",), ("lyric",)),
        _TitlePhrase("Soft", "Windows", ("wind_down",), ("settling",), ("lyric", "contour")),
    ),
    "room": (
        _TitlePhrase("Open", "Thresholds", ("occupied_day", "wake_ramp"), ("open_day", "lift")),
        _TitlePhrase("Near", "Rooms", ("occupied_day",), ("open_day",)),
        _TitlePhrase("Quiet", "Rooms", ("sleep", "wind_down"), ("settling", "stillness")),
        _TitlePhrase("Inner", "Corners", ("sleep", "wind_down"), ("settling", "stillness")),
        _TitlePhrase("Early", "Kitchen", ("wake_ramp",), ("lift",)),
        _TitlePhrase("Morning", "Rooms", ("wake_ramp",), ("open_day",)),
    ),
    "line": (
        _TitlePhrase("Fine", "Lines", ("occupied_day",), ("open_day", "settling"), ("contour", "lyric")),
        _TitlePhrase("Open", "Threads", ("occupied_day", "wake_ramp"), ("open_day", "lift"), ("lyric",)),
        _TitlePhrase("Electric", "Circuits", ("occupied_day", "away_practice"), ("open_day", "lift", "procession", "experiment"), ("rhythmic", "interval")),
        _TitlePhrase("Bright", "Wires", ("occupied_day", "wake_ramp"), ("open_day", "lift", "procession"), ("rhythmic", "interval")),
        _TitlePhrase("Quiet", "Threads", ("wind_down",), ("settling",), ("lyric", "contour")),
        _TitlePhrase("Moving", "Lines", ("occupied_day", "wake_ramp"), ("open_day", "lift", "procession"), ("rhythmic",)),
    ),
    "pattern": (
        _TitlePhrase("Bent", "Patterns", ("away_practice",), ("experiment",)),
        _TitlePhrase("Hidden", "Figures", ("away_practice",), ("experiment",)),
        _TitlePhrase("Shifting", "Studies", ("away_practice",), ("open_day", "experiment")),
        _TitlePhrase("Broken", "Circuits", ("away_practice",), ("experiment",)),
    ),
    "wire": (
        _TitlePhrase("Live", "Wires", ("away_practice",), ("lift", "experiment")),
        _TitlePhrase("Electric", "Circuits", ("occupied_day", "away_practice"), ("lift", "experiment")),
        _TitlePhrase("Bright", "Signals", ("wake_ramp", "occupied_day"), ("open_day", "lift")),
        _TitlePhrase("Wired", "Engines", ("away_practice",), ("experiment",)),
    ),
    "edge": (
        _TitlePhrase("Sharp", "Edges", ("away_practice",), ("experiment",)),
        _TitlePhrase("Outer", "Corners", ("occupied_day",), ("open_day",)),
        _TitlePhrase("Hidden", "Thresholds", ("wind_down", "away_practice"), ("settling", "experiment")),
        _TitlePhrase("Bent", "Signals", ("away_practice",), ("experiment",)),
    ),
    "day": (
        _TitlePhrase("Early", "Day", ("wake_ramp",), ("lift",)),
        _TitlePhrase("Morning", "Stairs", ("wake_ramp",), ("lift", "open_day")),
        _TitlePhrase("Open", "Hands", ("occupied_day",), ("open_day",)),
        _TitlePhrase("Moving", "Kitchen", ("wake_ramp", "occupied_day"), ("lift",)),
    ),
}


def _rng_for_inputs(
    family: str,
    progression_profile: str,
    cadence_state: str,
    song_num: int,
    mood: Mapping[str, float],
) -> random.Random:
    payload = "|".join(
        [
            family,
            progression_profile,
            cadence_state,
            str(song_num),
            f"{float(mood.get('energy', 0.5)):.3f}",
            f"{float(mood.get('valence', 0.5)):.3f}",
            f"{float(mood.get('arousal', 0.5)):.3f}",
        ]
    )
    digest = hashlib.sha256(payload.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _answer_for_anchor(anchor: tuple[int, ...], *, hook_class: str) -> tuple[int, ...]:
    answered = list(anchor)
    if not answered:
        return ()
    if hook_class == "rhythmic":
        answered[-1] = 1
    elif hook_class == "interval":
        answered = [max(1, min(8, degree - 1 if i % 2 else degree)) for i, degree in enumerate(answered)]
        answered[-1] = 1 if answered[-1] > 3 else 3
    else:
        if len(answered) >= 2:
            answered[-2] = max(1, min(8, answered[-2] - 1))
        answered[-1] = 1 if answered[-1] >= 4 else 3
    return tuple(answered)


_HOOK_VERB_ANSWERS = {
    "hold": "carry",
    "keep": "leave",
    "let": "leave",
    "follow": "answer",
    "wake": "gather",
    "bend": "turn",
    "test": "trace",
}

_HOOK_TEXT_FIXES = {
    "answer the again": "keep the room open",
    "open the room open": "keep the room open",
    "carry the room wide": "keep the room open",
    "hold the room wide": "keep the room open",
    "carry the line wide": "keep the line open",
    "hold the line wide": "keep the line open",
}

_HOOK_PHRASE_ANSWERS = {
    "hold the dark": ("carry the dark", "let the dark breathe", "leave the dark wide"),
    "let it soften": ("leave it soft", "let it loosen", "keep it low"),
    "keep the room low": ("leave the room low", "let the room breathe low", "keep the room breathing"),
    "hold the light": ("carry the light", "let the light hover", "leave the light wide"),
    "let it settle": ("leave it still", "let it fall quiet", "let it drift still"),
    "stay with the room": ("stay with the room", "keep with the room", "listen with the room"),
    "wake the room": ("gather the room", "lift the room slowly", "wake the room gently"),
    "follow the light": ("carry the light", "let the light lead", "move with the light"),
    "gather the day": ("open the day", "let the day arrive", "carry the day in"),
    "keep the line open": ("leave the line open", "let the line ring", "let the line widen"),
    "keep the room open": ("keep the room open", "let the room answer", "leave the room awake"),
    "answer the room": ("keep the room open", "let the room answer", "leave the room awake"),
    "bend the pattern": ("turn the pattern", "tilt the pattern", "let the pattern break"),
    "follow the wire": ("trace the wire", "keep to the wire", "let the wire lead"),
    "test the edges": ("trace the edges", "lean on the edges", "let the edges answer"),
}


def _normalize_hook_text(text: str) -> str:
    cleaned = " ".join(word for word in str(text).split() if word).strip()
    if not cleaned:
        return ""
    return _HOOK_TEXT_FIXES.get(cleaned.lower(), cleaned)


def _image_field_for_hook(text: str) -> str:
    return _HOOK_IMAGE_FIELDS.get(_normalize_hook_text(text).lower(), "")


def _title_modifier_for_field(
    rng: random.Random,
    *,
    family_key: str,
    image_field: str,
) -> str:
    if image_field in _IMAGE_FIELD_MODIFIERS:
        return rng.choice(_IMAGE_FIELD_MODIFIERS[image_field])
    return rng.choice(_TITLE_MODIFIERS[family_key])


def _score_title_phrase(
    phrase: _TitlePhrase,
    *,
    cadence_key: str,
    progression_profile: str,
    source_title: str,
    hook_class: str,
) -> float:
    score = 0.0
    if phrase.cadence_tags:
        score += 3.0 if cadence_key in phrase.cadence_tags else -1.0
    else:
        score += 0.5
    if phrase.profile_tags:
        score += 3.0 if progression_profile in phrase.profile_tags else -1.0
    else:
        score += 0.5
    if phrase.hook_tags:
        score += 2.0 if hook_class in phrase.hook_tags else -0.5

    normalized_source = " ".join(source_title.split()).strip().lower()
    candidate = f"{phrase.modifier} {phrase.noun}".lower()
    if normalized_source:
        if candidate == normalized_source:
            score -= 100.0
        source_words = set(normalized_source.split())
        if phrase.modifier.lower() in source_words:
            score -= 0.5
        if phrase.noun.lower() in source_words:
            score -= 0.75
    return score


def _title_for_field(
    rng: random.Random,
    *,
    family_key: str,
    cadence_key: str,
    progression_profile: str,
    image_field: str,
    source_title: str,
    song_num: int,
    hook_class: str,
) -> tuple[str, str]:
    phrases = _IMAGE_FIELD_TITLE_PHRASES.get(image_field)
    if phrases:
        scored = sorted(
            (
                (
                    _score_title_phrase(
                        phrase,
                        cadence_key=cadence_key,
                        progression_profile=progression_profile,
                        source_title=source_title,
                        hook_class=hook_class,
                    ),
                    index,
                    phrase,
                )
                for index, phrase in enumerate(phrases)
            ),
            key=lambda item: (item[0], -item[1]),
            reverse=True,
        )
        if scored:
            best_score = scored[0][0]
            shortlist = [phrase for score, _index, phrase in scored if score >= best_score - 0.75]
            if shortlist:
                shortlist = sorted(shortlist, key=lambda phrase: f"{phrase.modifier} {phrase.noun}")
                payload = "|".join(
                    [str(song_num), image_field, cadence_key, progression_profile, source_title, hook_class]
                )
                rotation_seed = int.from_bytes(hashlib.sha256(payload.encode("utf-8")).digest()[:8], "big")
                chosen = shortlist[rotation_seed % len(shortlist)]
                return chosen.modifier, chosen.noun

    modifier = _title_modifier_for_field(rng, family_key=family_key, image_field=image_field)
    if image_field in _IMAGE_FIELD_NOUNS:
        return modifier, rng.choice(_IMAGE_FIELD_NOUNS[image_field])
    return modifier, rng.choice(_TITLE_NOUNS.get(cadence_key, _TITLE_NOUNS["occupied_day"]))


def _answer_variant_index(
    variants: tuple[str, ...],
    *,
    family: str,
    cadence_state: str,
    song_num: int,
    mood: Mapping[str, float],
) -> int:
    if len(variants) <= 1:
        return 0
    family_offset = sum(ord(char) for char in family) % len(variants)
    cadence_offset = sum(ord(char) for char in cadence_state) % len(variants)
    mood_offset = (
        int(round(float(mood.get("energy", 0.5)) * 10.0))
        + int(round(float(mood.get("valence", 0.5)) * 20.0))
        + int(round(float(mood.get("arousal", 0.5)) * 30.0))
    ) % len(variants)
    return (song_num + family_offset + cadence_offset + mood_offset) % len(variants)


def _answer_hook_text(
    text: str,
    *,
    family: str = "",
    cadence_state: str = "",
    song_num: int = 0,
    mood: Mapping[str, float] | None = None,
) -> str:
    cleaned = _normalize_hook_text(text)
    if not cleaned:
        return text
    mood_map = mood or {}
    variants = _HOOK_PHRASE_ANSWERS.get(cleaned.lower())
    if variants is not None:
        return variants[
            _answer_variant_index(
                variants,
                family=family,
                cadence_state=cadence_state,
                song_num=song_num,
                mood=mood_map,
            )
        ]
    words = cleaned.split()
    if not words:
        return text
    first = words[0].lower()
    replacement = _HOOK_VERB_ANSWERS.get(first)
    if replacement is not None:
        words[0] = replacement
        return " ".join(words)
    return cleaned


def build_hook_profile(
    *,
    family: str,
    progression_profile: str,
    cadence_state: str,
    song_num: int,
    mood: Mapping[str, float],
    repertoire_hint: Mapping[str, object] | None = None,
) -> HookProfile:
    """Return deterministic title/hook/phrase-pair material for one song."""

    family_key = family if family in _HOOK_TYPES else "default"
    cadence_key = cadence_state if cadence_state in _HOOK_LINES else "occupied_day"
    rng = _rng_for_inputs(family, progression_profile, cadence_state, song_num, mood)
    hook_class = rng.choice(_HOOK_TYPES[family_key])
    anchor = rng.choice(_HOOK_ANCHORS[hook_class])
    answer = _answer_for_anchor(anchor, hook_class=hook_class)
    text_hook = rng.choice(_HOOK_LINES[cadence_key])
    if repertoire_hint:
        hint_type = str(repertoire_hint.get("hook_class", "") or repertoire_hint.get("hook_class", "") or "")
        if hint_type in _HOOK_ANCHORS:
            hook_class = hint_type
            anchor = rng.choice(_HOOK_ANCHORS[hook_class])
            answer = _answer_for_anchor(anchor, hook_class=hook_class)
        hinted_hook = str(repertoire_hint.get("hook_text", "") or "").strip()
        if hinted_hook:
            if str(repertoire_hint.get("mode", "") or "") == "answer":
                text_hook = _answer_hook_text(
                    hinted_hook,
                    family=family,
                    cadence_state=cadence_state,
                    song_num=song_num,
                    mood=mood,
                )
            else:
                text_hook = _normalize_hook_text(hinted_hook)
    image_field = _image_field_for_hook(text_hook)
    modifier, noun = _title_for_field(
        rng,
        family_key=family_key,
        cadence_key=cadence_key,
        progression_profile=progression_profile,
        image_field=image_field,
        source_title=str(repertoire_hint.get("source_title", "") or "") if repertoire_hint else "",
        song_num=song_num,
        hook_class=hook_class,
    )
    return HookProfile(
        title=f"{modifier} {noun}",
        text_hook=_normalize_hook_text(text_hook),
        hook_class=hook_class,
        contour=_HOOK_CONTOURS.get(hook_class, anchor),
        rhythm=_RHYTHM_BY_GROOVE.get(_GROOVE_BY_FAMILY.get(family_key, "lyric"), (1.0, 1.0, 1.0, 1.0)),
        anchor_degrees=anchor,
        answer_degrees=answer,
        timbral_tags=_TIMBRAL_TAGS.get(family_key, ("clear", "steady")),
        groove_family=_GROOVE_BY_FAMILY.get(family_key, "lyric"),
        section_intent=_SECTION_INTENT.get(cadence_key, "open and answer"),
    )
