"""Capstone cycle planning for the EMSD track."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from .artistic_identity import ArtisticIdentity, derive_artistic_identity
from .dsp_scene_lab import DSPScene, scene_for_phase
from .mix_engine import MixProfile, build_mix_profile
from .procedural_arc import ARC_PHASES, ArcDirective, directive_for_elapsed
from .sample_lab import SamplePlan, plan_environmental_sampling
from .sound_palette_lab import PatchStudy, study_for_patch


@dataclass(frozen=True)
class CapstonePhasePlan:
    phase_name: str
    family_name: str
    patch_name: str
    arc: ArcDirective
    palette: PatchStudy
    mix: MixProfile
    sampling: SamplePlan
    dsp: DSPScene


@dataclass(frozen=True)
class CapstoneCyclePlan:
    phases: tuple[CapstonePhasePlan, ...]
    identity: ArtisticIdentity
    marathon_distinctness_axes: tuple[str, ...]


_FAMILY_BY_PHASE = {
    "Divination": "drift",
    "Emergence": "ember",
    "Conversation": "bloom",
    "Convergence": "pulse",
    "Crystallization": "nocturne",
}

_PATCH_BY_PHASE = {
    "Divination": "house_monastery",
    "Emergence": "house_chamber",
    "Conversation": "house_garden",
    "Convergence": "house_procession",
    "Crystallization": "house_monastery",
}

_SOURCE_BY_PHASE = {
    "Divination": "room_mic",
    "Emergence": "room_mic",
    "Conversation": "theramini_in",
    "Convergence": "room_mic",
    "Crystallization": "room_mic",
}


def build_capstone_cycle(
    *,
    cadence_state: str,
    occupancy_state: str,
    theramini_present: bool = False,
    repertoire_songs: Sequence[Mapping[str, object]] = (),
) -> CapstoneCyclePlan:
    identity = derive_artistic_identity(repertoire_songs)
    phases: list[CapstonePhasePlan] = []
    for phase in ARC_PHASES:
        patch_name = _PATCH_BY_PHASE[phase.name]
        source_name = _SOURCE_BY_PHASE[phase.name]
        if cadence_state == "away_practice" and phase.name in {"Convergence", "Crystallization"}:
            source_name = "self_bus"
        phases.append(
            CapstonePhasePlan(
                phase_name=phase.name,
                family_name=_FAMILY_BY_PHASE[phase.name],
                patch_name=patch_name,
                arc=directive_for_elapsed(
                    phase.start_minute + 0.01,
                    cadence_state=cadence_state,
                    audience_attention=0.75 if phase.name == "Conversation" and occupancy_state.startswith("occupied") else 0.25,
                ),
                palette=study_for_patch(
                    patch_name=patch_name,
                    cadence_state=cadence_state,
                    family_name=_FAMILY_BY_PHASE[phase.name],
                    occupancy_state=occupancy_state,
                ),
                mix=build_mix_profile(
                    cadence_state=cadence_state,
                    patch_name=patch_name,
                    theramini_present=theramini_present and phase.name in {"Conversation", "Convergence"},
                    phase_name=phase.name,
                ),
                sampling=plan_environmental_sampling(
                    source_name=source_name,
                    cadence_state=cadence_state,
                    intensity=phase.density,
                ),
                dsp=scene_for_phase(phase.name, cadence_state=cadence_state),
            )
        )
    return CapstoneCyclePlan(
        phases=tuple(phases),
        identity=identity,
        marathon_distinctness_axes=("family", "patch", "sampling", "dsp", "mix"),
    )
