"""Concrete narrative-to-music handoff for one commissioned piece."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from inner_life.world_model import WorldModel

from .piece_commission import PieceCommission


@dataclass(frozen=True)
class PieceBrief:
    image_field: tuple[str, ...]
    dramatic_premise: str
    conflict: str
    desired_payoff: str
    residue: str
    ending_feeling: str
    motion_character: str
    hook_pressure: float
    through_composed_pressure: float
    section_beats: tuple[str, ...]
    narrative_scale: str
    # Narrative-derived authoring inputs (empty when narrative state absent)
    opening_beat: str = ""
    turn_beat: str = ""
    payoff_beat: str = ""
    residue_beat: str = ""
    motif_development: str = ""
    sound_palette: str = ""


_DEFAULT_IMAGE_FIELDS = {
    "sleep": ("room", "dark", "lamp"),
    "wind_down": ("window", "thread", "room"),
    "wake_ramp": ("kitchen", "stairs", "light"),
    "occupied_day": ("room", "window", "hands"),
    "away_practice": ("wire", "study", "edge"),
}


def _interesting_words(text: str) -> list[str]:
    words: list[str] = []
    for raw in text.replace(",", " ").replace(".", " ").split():
        word = raw.strip().lower()
        if len(word) < 4:
            continue
        if word in {"with", "near", "into", "from", "that", "this"}:
            continue
        if word not in words:
            words.append(word)
    return words


_PHASE_BEAT_TEMPLATES: dict[str, dict[str, str]] = {
    "build": {
        "opening": "{lead} begins to gather presence",
        "turn": "{lead} finds an unexpected edge",
        "payoff": "a clear shape emerges from {lead}",
        "residue": "a faint outline of {lead} lingers",
    },
    "rise": {
        "opening": "{lead} opens wider, pulling new threads",
        "turn": "a second voice answers {lead}",
        "payoff": "{lead} commits to its direction",
        "residue": "the threads keep vibrating after {lead} passes",
    },
    "climax": {
        "opening": "{lead} arrives fully, nothing held back",
        "turn": "everything building in {lead} breaks open",
        "payoff": "{lead} speaks its whole name",
        "residue": "the room remembers {lead} at full voice",
    },
    "resolve": {
        "opening": "{lead} begins to release what it held",
        "turn": "the last tension in {lead} unwinds",
        "payoff": "{lead} settles into its final shape",
        "residue": "an echo of {lead} fades through the room",
    },
    "rest": {
        "opening": "{lead} is barely there, just a whisper",
        "turn": "even the whisper of {lead} starts to dissolve",
        "payoff": "silence accepts what {lead} offered",
        "residue": "the room breathes where {lead} was",
    },
}

_MOTIF_DEVELOPMENT: dict[str, str] = {
    "build": "germinal",
    "rise": "expansive",
    "climax": "declarative",
    "resolve": "recapitulative",
    "rest": "minimal",
}

_PALETTE_BASE: dict[str, str] = {
    "build": "sparse textures, room tone",
    "rise": "layered voices, rising warmth",
    "climax": "full ensemble, bright attacks",
    "resolve": "thinning layers, soft releases",
    "rest": "near-silence, breath",
}


def _derive_narrative_fields(
    lead_image: str,
    arc_phase: str,
    mood: float,
    creative_energy: float,
    curiosity: float,
) -> dict[str, str]:
    """Derive concrete beat descriptions and palette from narrative state."""
    templates = _PHASE_BEAT_TEMPLATES.get(arc_phase, _PHASE_BEAT_TEMPLATES["build"])
    beats = {
        key: template.format(lead=lead_image)
        for key, template in templates.items()
    }
    motif_dev = _MOTIF_DEVELOPMENT.get(arc_phase, "germinal")
    if curiosity > 0.7:
        motif_dev = f"{motif_dev}, exploratory"
    elif curiosity < 0.3:
        motif_dev = f"{motif_dev}, restrained"

    palette = _PALETTE_BASE.get(arc_phase, "moderate textures")
    if mood > 0.3 and creative_energy > 0.6:
        palette = f"{palette}, bright and open"
    elif mood > 0.3:
        palette = f"{palette}, warm"
    elif mood < -0.3 and creative_energy > 0.6:
        palette = f"{palette}, tense"
    elif mood < -0.3:
        palette = f"{palette}, dark"

    return {
        "opening_beat": beats["opening"],
        "turn_beat": beats["turn"],
        "payoff_beat": beats["payoff"],
        "residue_beat": beats["residue"],
        "motif_development": motif_dev,
        "sound_palette": palette,
    }


def _iter_world_words(world: WorldModel) -> Iterable[str]:
    for value in (
        world.observer_description,
        world.identity_hint,
        world.current_movement,
        world.cadence_state,
        world.day_phase,
        world.time_of_day,
    ):
        for word in _interesting_words(str(value or "")):
            yield word


def _beats_for_mode(mode: str, scale: str) -> tuple[str, ...]:
    if mode == "hook_led":
        if scale == "single_image":
            return ("opening image", "statement", "arrival", "residue")
        return ("opening image", "statement", "lift", "arrival", "turn", "payoff", "residue")
    if mode == "hybrid":
        return ("opening image", "statement", "complication", "turn", "payoff", "residue")
    if scale == "ritual":
        return ("opening image", "emergence", "complication", "break", "turn", "return", "payoff", "residue")
    return ("opening image", "emergence", "complication", "turn", "payoff", "residue")


def build_piece_brief(
    *,
    world: WorldModel | Mapping[str, object],
    commission: PieceCommission,
    family: str,
    cadence_state: str,
    progression_profile: str,
    repertoire_hint: Mapping[str, object] | None = None,
    narrative: Mapping[str, object] | None = None,
) -> PieceBrief:
    if isinstance(world, Mapping):
        world = WorldModel(
            observer_description=str(world.get("observer_description", "") or ""),
            identity_hint=str(world.get("identity_hint", "") or ""),
            current_movement=str(world.get("current_movement", "") or ""),
            cadence_state=str(world.get("cadence_state", cadence_state) or cadence_state),
            day_phase=str(world.get("day_phase", "") or ""),
            time_of_day=str(world.get("time_of_day", "") or ""),
            occupancy_state=str(world.get("occupancy_state", "") or ""),
            attention_score=float(world.get("attention_score", 0.0) or 0.0),
        )

    words = list(_iter_world_words(world))
    image_field = tuple((words + list(_DEFAULT_IMAGE_FIELDS.get(cadence_state, ("room", "signal", family))))[:4])
    lead_image = image_field[0] if image_field else "room"
    second_image = image_field[1] if len(image_field) > 1 else family
    recalled = str((repertoire_hint or {}).get("source_title", "") or "").strip()
    premise = f"{lead_image} holds while {second_image} keeps changing"
    if world.occupancy_state == "occupied_active":
        conflict = f"attention keeps pulling the {lead_image} open"
    elif world.occupancy_state == "likely_asleep":
        conflict = f"the {lead_image} tries not to wake the room"
    elif cadence_state == "away_practice":
        conflict = f"the {lead_image} studies its own edges"
    else:
        conflict = f"the {lead_image} is trying to stay open under pressure"
    payoff = f"let the {lead_image} resolve without closing"
    residue = f"leave a trace of {lead_image} and {second_image}"
    if recalled:
        residue = f"leave {recalled.lower()} as a trace in the {lead_image}"

    through_pressure = 0.25 + (0.45 if commission.composition_mode == "through_composed" else 0.18 if commission.composition_mode == "hybrid" else 0.0)
    through_pressure += 0.12 if commission.form_class in {"extended", "suite"} else 0.0

    hook = commission.hook_pressure
    narrative_fields: dict[str, str] = {}

    if narrative:
        arc_phase = str(narrative.get("arc_phase", "") or "")
        mood = float(narrative.get("mood", 0.0) or 0.0)
        creative_energy = float(narrative.get("creative_energy", 0.5) or 0.5)
        curiosity = float(narrative.get("curiosity", 0.5) or 0.5)

        if arc_phase:
            narrative_fields = _derive_narrative_fields(
                lead_image, arc_phase, mood, creative_energy, curiosity,
            )
            # Nudge pressures based on inner-life state
            if creative_energy > 0.6:
                hook = min(1.0, hook + 0.08)
            elif creative_energy < 0.3:
                hook = max(0.0, hook - 0.08)
            if curiosity > 0.7:
                through_pressure += 0.06

    return PieceBrief(
        image_field=image_field,
        dramatic_premise=premise,
        conflict=conflict,
        desired_payoff=payoff,
        residue=residue,
        ending_feeling=commission.ending_family.replace("_", " "),
        motion_character=commission.groove_identity.replace("_", " "),
        hook_pressure=round(min(1.0, hook), 3),
        through_composed_pressure=round(min(1.0, through_pressure), 3),
        section_beats=_beats_for_mode(commission.composition_mode, commission.narrative_scale),
        narrative_scale=commission.narrative_scale,
        opening_beat=narrative_fields.get("opening_beat", ""),
        turn_beat=narrative_fields.get("turn_beat", ""),
        payoff_beat=narrative_fields.get("payoff_beat", ""),
        residue_beat=narrative_fields.get("residue_beat", ""),
        motif_development=narrative_fields.get("motif_development", ""),
        sound_palette=narrative_fields.get("sound_palette", ""),
    )
