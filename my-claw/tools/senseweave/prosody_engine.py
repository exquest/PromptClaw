"""Short textual framing for CypherClaw songs and scenes."""
from __future__ import annotations

_SCENE_HOOK_VARIANTS = {
    "hold the light": {
        "Recap": "the light still holds",
        "Release": "the light still holds",
        "Afterglow": "light still held",
        "Resolution": "light still held",
    },
    "carry the light": {
        "Recap": "the light keeps moving",
        "Release": "the light keeps moving",
        "Afterglow": "light carried on",
        "Resolution": "light carried on",
    },
    "let the light hover": {
        "Recap": "the light still hovers",
        "Release": "the light still hovers",
        "Afterglow": "light hovering",
        "Resolution": "light hovering",
    },
    "keep the line open": {
        "Recap": "the line stays open",
        "Release": "the line stays open",
        "Afterglow": "line still open",
        "Resolution": "line still open",
    },
    "leave the line open": {
        "Recap": "the line stays open",
        "Release": "the line stays open",
        "Afterglow": "line still open",
        "Resolution": "line still open",
    },
    "let the line ring": {
        "Recap": "the line keeps ringing",
        "Release": "the line keeps ringing",
        "Afterglow": "line still ringing",
        "Resolution": "line still ringing",
    },
    "hold the line wide": {
        "Recap": "the line stays wide",
        "Release": "the line stays wide",
        "Afterglow": "line held wide",
        "Resolution": "line held wide",
    },
    "answer the room": {
        "Recap": "the room answers back",
        "Release": "the room answers back",
        "Afterglow": "room still answering",
        "Resolution": "room still answering",
    },
    "keep the room open": {
        "Recap": "the room stays open",
        "Release": "the room stays open",
        "Afterglow": "room still open",
        "Resolution": "room still open",
    },
    "let the room answer": {
        "Recap": "the room answers back",
        "Release": "the room answers back",
        "Afterglow": "room still answering",
        "Resolution": "room still answering",
    },
    "leave the room awake": {
        "Recap": "the room stays awake",
        "Release": "the room stays awake",
        "Afterglow": "room still awake",
        "Resolution": "room still awake",
    },
}

_HOOK_SUBJECTS = {
    "hold the light": "light",
    "carry the light": "light",
    "let the light hover": "light",
    "keep the line open": "line",
    "leave the line open": "line",
    "let the line ring": "line",
    "hold the line wide": "line",
    "answer the room": "room",
    "keep the room open": "room",
    "let the room answer": "room",
    "leave the room awake": "room",
    "hold the dark": "dark",
    "let the dark breathe": "dark",
    "leave the dark wide": "dark",
}

_CADENCE_RESIDUE = {
    "line": {
        "authentic": "line at rest",
        "deceptive": "line turning aside",
        "dominant": "line still reaching",
        "half": "line still reaching",
        "plagal": "line settling open",
    },
    "room": {
        "authentic": "room at rest",
        "deceptive": "room turned aside",
        "dominant": "room still listening",
        "half": "room still listening",
        "plagal": "room settling open",
    },
    "light": {
        "authentic": "light at rest",
        "deceptive": "light turned aside",
        "dominant": "light still leaning",
        "half": "light still leaning",
        "plagal": "light settling down",
    },
    "dark": {
        "authentic": "dark at rest",
        "deceptive": "dark turned aside",
        "dominant": "dark still leaning",
        "half": "dark still leaning",
        "plagal": "dark settling low",
    },
}

_PATCH_DENSITY_BIAS = {
    "house_monastery": -1,
    "house_chamber": -1,
    "house_garden": 0,
    "house_procession": 1,
    "house_workshop": 1,
}

_SPARSE_HOOK_VARIANTS = {
    "keep the line open": "line open",
    "leave the line open": "line open",
    "let the line ring": "line ringing",
    "keep the room open": "room open",
    "let the room answer": "room listening",
    "answer the room": "room listening",
    "hold the light": "light held",
    "carry the light": "light carried",
}

_DENSE_HOOK_VARIANTS = {
    "keep the line open": "keep every line open",
    "leave the line open": "leave every line open",
    "keep the room open": "keep the whole room open",
    "let the room answer": "let the whole room answer",
    "answer the room": "let the whole room answer",
    "hold the light": "let the whole light move",
    "carry the light": "carry the light through",
}


def _density_profile(*, patch_name: str, lane_count: int) -> str:
    if lane_count <= 0:
        return "neutral"
    bias = _PATCH_DENSITY_BIAS.get(patch_name, 0)
    if lane_count >= 4 or (bias > 0 and lane_count >= 3):
        return "dense"
    if lane_count <= 2 or (bias < 0 and lane_count <= 3):
        return "sparse"
    return "neutral"


def _scene_hook_caption(
    *,
    text_hook: str,
    scene_name: str,
    cadence_type: str = "",
    patch_name: str = "",
    lane_count: int = 0,
) -> str:
    cleaned = " ".join(word for word in text_hook.split() if word).strip()
    if not cleaned:
        return ""
    density = _density_profile(patch_name=patch_name, lane_count=lane_count)
    if scene_name in {"Emergence", "Theme"}:
        if density == "sparse":
            sparse = _SPARSE_HOOK_VARIANTS.get(cleaned.lower())
            if sparse:
                return sparse[:48].strip()
        if density == "dense":
            dense = _DENSE_HOOK_VARIANTS.get(cleaned.lower())
            if dense:
                return dense[:48].strip()
    subject = _HOOK_SUBJECTS.get(cleaned.lower())
    cadence_key = cadence_type.strip().lower()
    if scene_name in {"Resolution", "Afterglow"} and subject and cadence_key:
        residue = _CADENCE_RESIDUE.get(subject, {}).get(cadence_key)
        if residue:
            return residue[:48].strip()
    variants = _SCENE_HOOK_VARIANTS.get(cleaned.lower())
    if variants and scene_name in variants:
        return variants[scene_name][:48].strip()
    if scene_name in {"Theme"}:
        return cleaned[:48].strip()
    if scene_name in {"Recap", "Release"}:
        return f"{scene_name}: {cleaned}"[:48].strip()
    if scene_name in {"Development", "Bridge"}:
        return f"{scene_name}: {cleaned}"[:48].strip()
    return ""


def compose_song_title(
    *,
    family: str,
    progression_profile: str,
    cadence_state: str,
    song_num: int,
    practice_block: str,
) -> str:
    family_words = {
        "nocturne": "Quiet",
        "ember": "Warm",
        "drift": "Slow",
        "bloom": "Open",
        "pulse": "Moving",
        "forge": "Bent",
    }
    cadence_words = {
        "sleep": "Rooms",
        "wind_down": "Windows",
        "wake_ramp": "Stairs",
        "occupied_day": "Machines",
        "away_practice": "Studies",
    }
    left = family_words.get(family, "Near")
    right = cadence_words.get(cadence_state, "Signals")
    if practice_block:
        left = practice_block.split()[0]
    if progression_profile in {"settling", "stillness"}:
        right = "Lamps"
    elif progression_profile in {"lift", "procession"}:
        right = "Procession"
    return f"{left} {right}"[:40].strip()


def compose_scene_caption(
    *,
    title: str,
    scene_name: str,
    text_hook: str,
    cadence_state: str,
    section_function: str,
    cadence_type: str = "",
    patch_name: str = "",
    lane_count: int = 0,
    practice_block: str,
) -> str:
    if text_hook:
        shaped = _scene_hook_caption(
            text_hook=text_hook,
            scene_name=scene_name,
            cadence_type=cadence_type,
            patch_name=patch_name,
            lane_count=lane_count,
        )
        if shaped:
            return shaped
    if practice_block:
        return f"{scene_name}: {practice_block}"[:48].strip()
    if section_function:
        return f"{scene_name}: {section_function}"[:48].strip()
    if title:
        return f"{scene_name}: {title}"[:48].strip()
    return f"{scene_name} {cadence_state}".strip()[:48]
