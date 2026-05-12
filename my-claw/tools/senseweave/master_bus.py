"""Translate EMSD scene and mix intent into live master-bus control."""
from __future__ import annotations

from typing import Any, Mapping

from .emsd_runtime import EMSDLiveContext


MASTER_NODE_ID = 99999
DEFAULT_MASTER_BUS_VALUES = {
    "amp": 5.0,
    "sampler_amp": 1.0,
    "sampler_bypass_comp": 1.0,
    "drive": 0.15,
    "warmth": 0.35,
    "reverb": 0.05,
    "room": 0.5,
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _automation_default(
    scene: Any,
    lane_name: str,
    default: float,
    *,
    automation_values: Mapping[str, float] | None = None,
) -> float:
    if automation_values is not None and lane_name in automation_values:
        try:
            return float(automation_values[lane_name])
        except (TypeError, ValueError):
            return default
    for lane in getattr(getattr(scene, "pattern", None), "automation", ()):
        if getattr(lane, "name", "") == lane_name:
            try:
                return float(getattr(lane, "default", default))
            except (TypeError, ValueError):
                return default
    return default


def master_bus_values_for_scene(
    scene: Any,
    *,
    context: EMSDLiveContext | None,
    theramini_active: bool = False,
    automation_values: Mapping[str, float] | None = None,
) -> dict[str, float]:
    """Return the live `sw_master_smooth` parameter set for one scene."""
    scene_master_amp = _automation_default(scene, "master_amp", 0.6, automation_values=automation_values)
    scene_reverb_send = _automation_default(scene, "reverb_send", 0.12, automation_values=automation_values)
    scene_density = _automation_default(scene, "density", 0.35, automation_values=automation_values)
    sampler_amp = round(_clamp(scene_master_amp, 0.05, 1.0), 3)
    sampler_bypass_comp = round(
        _clamp(
            _automation_default(scene, "sampler_bypass_comp", 1.0, automation_values=automation_values),
            0.0,
            1.0,
        ),
        3,
    )
    if context is None:
        return {
            "amp": round(_clamp(scene_master_amp * 3.2, 0.8, 5.0), 3),
            "sampler_amp": sampler_amp,
            "sampler_bypass_comp": sampler_bypass_comp,
            "drive": round(_clamp(0.12 + scene_density * 0.04, 0.05, 0.35), 3),
            "warmth": round(_clamp(0.28 + (1.0 - scene_density) * 0.12, 0.12, 0.7), 3),
            "reverb": round(_clamp(0.04 + scene_reverb_send * 0.6, 0.02, 0.24), 3),
            "room": round(_clamp(0.4 + scene_reverb_send * 0.8, 0.25, 0.95), 3),
        }

    mix = context.phase_plan.mix
    lufs_tightness = _clamp(((-mix.target_lufs) - 14.0) / 10.0, 0.0, 1.0)
    ceiling_tightness = _clamp(abs(float(mix.peak_ceiling_dbtp) + 1.0) / 2.0, 0.0, 1.0)
    comp_strength = _clamp((float(mix.bus_comp_ratio) - 1.0) / 4.0, 0.0, 1.0)
    duck_strength = _clamp(float(mix.theramini_duck_db) / 6.0, 0.0, 1.0) if theramini_active else 0.0

    amp = scene_master_amp * (3.8 - (lufs_tightness * 0.65) - (duck_strength * 0.22))
    drive = 0.1 + (scene_density * 0.05) + (comp_strength * 0.09) + (ceiling_tightness * 0.03)
    warmth = 0.2 + ((1.0 - scene_density) * 0.16) + ((1.0 - comp_strength) * 0.05)
    reverb = 0.03 + (scene_reverb_send * 0.62) + ((1.0 - scene_density) * 0.03)
    room = 0.34 + (scene_reverb_send * 0.85) + (ceiling_tightness * 0.08)

    return {
        "amp": round(_clamp(amp, 0.8, 5.0), 3),
        "sampler_amp": sampler_amp,
        "sampler_bypass_comp": sampler_bypass_comp,
        "drive": round(_clamp(drive, 0.05, 0.35), 3),
        "warmth": round(_clamp(warmth, 0.12, 0.72), 3),
        "reverb": round(_clamp(reverb, 0.02, 0.24), 3),
        "room": round(_clamp(room, 0.25, 0.95), 3),
    }


def master_bus_n_set_args(
    scene: Any,
    *,
    context: EMSDLiveContext | None,
    theramini_active: bool = False,
    automation_values: Mapping[str, float] | None = None,
) -> list[float | int | str]:
    values = master_bus_values_for_scene(
        scene,
        context=context,
        theramini_active=theramini_active,
        automation_values=automation_values,
    )
    return [
        MASTER_NODE_ID,
        "amp",
        values["amp"],
        "sampler_amp",
        values["sampler_amp"],
        "sampler_bypass_comp",
        values["sampler_bypass_comp"],
        "drive",
        values["drive"],
        "warmth",
        values["warmth"],
        "reverb",
        values["reverb"],
        "room",
        values["room"],
    ]


def master_bus_s_new_args(values: dict[str, float] | None = None) -> list[float | int | str]:
    seeded = dict(DEFAULT_MASTER_BUS_VALUES)
    if values:
        seeded.update(values)
    return [
        "sw_master_smooth",
        MASTER_NODE_ID,
        1,
        0,
        "drive",
        seeded["drive"],
        "warmth",
        seeded["warmth"],
        "reverb",
        seeded["reverb"],
        "room",
        seeded["room"],
        "amp",
        seeded["amp"],
        "sampler_amp",
        seeded["sampler_amp"],
        "sampler_bypass_comp",
        seeded["sampler_bypass_comp"],
    ]


def seed_master_bus_node(client: Any, values: dict[str, float] | None = None) -> dict[str, float]:
    seeded = dict(DEFAULT_MASTER_BUS_VALUES)
    if values:
        seeded.update(values)
    client.send_message("/s_new", master_bus_s_new_args(seeded))
    return seeded


def apply_master_bus_scene(
    client: Any,
    scene: Any,
    *,
    context: EMSDLiveContext | None,
    theramini_active: bool = False,
    automation_values: Mapping[str, float] | None = None,
) -> dict[str, float]:
    values = master_bus_values_for_scene(
        scene,
        context=context,
        theramini_active=theramini_active,
        automation_values=automation_values,
    )
    client.send_message(
        "/n_set",
        master_bus_n_set_args(
            scene,
            context=context,
            theramini_active=theramini_active,
            automation_values=automation_values,
        ),
    )
    return values
