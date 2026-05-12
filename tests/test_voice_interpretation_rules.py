"""Tests for voice_interpretation_rules.py -- source-to-music mappings."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.voice_interpretation_rules import (
    KNOWN_SOURCES,
    MusicalMapping,
    canonical_source,
    interpret_all,
    interpret_source,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_MUSICAL_FIELDS = ("pitch", "rhythm", "density", "harmony", "timbre", "mix", "deference")


def _assert_bounds(mapping: MusicalMapping) -> None:
    """Every musical field must be in [0, 1]."""
    for field in _MUSICAL_FIELDS:
        value = getattr(mapping, field)
        assert 0.0 <= value <= 1.0, f"{mapping.source}.{field} = {value} out of [0,1]"


# ---------------------------------------------------------------------------
# Room mic: quiet vs noisy
# ---------------------------------------------------------------------------


def test_quiet_room_yields_sparse_high_deference() -> None:
    m = interpret_source("room_mic", {"activity_level": "quiet", "recent_transient": False})
    _assert_bounds(m)
    assert m.source == "room_mic"
    assert m.density < 0.3
    assert m.rhythm < 0.25
    assert m.deference > 0.6
    assert m.pitch > 0.5  # quiet room = higher register


def test_noisy_room_yields_dense_assertive() -> None:
    m = interpret_source("room_mic", {"activity_level": "active", "recent_transient": True})
    _assert_bounds(m)
    assert m.density > 0.5
    assert m.rhythm > 0.5
    assert m.deference < 0.5
    assert m.mix > 0.4


def test_room_transient_boosts_energy() -> None:
    quiet = interpret_source("room_mic", {"activity_level": "quiet", "recent_transient": False})
    transient = interpret_source("room_mic", {"activity_level": "quiet", "recent_transient": True})
    assert transient.rhythm > quiet.rhythm
    assert transient.density > quiet.density


def test_room_speech_boosts_energy() -> None:
    no_speech = interpret_source("room_mic", {"activity_level": "moderate"})
    speech = interpret_source("room_mic", {"activity_level": "moderate", "speech_detected": True})
    assert speech.mix >= no_speech.mix
    assert speech.density >= no_speech.density


# ---------------------------------------------------------------------------
# Perform-VE condenser alias resolves to room_mic
# ---------------------------------------------------------------------------


def test_perform_ve_condenser_is_room_mic() -> None:
    assert canonical_source("perform_ve_condenser") == "room_mic"
    m = interpret_source("perform_ve_condenser", {"activity_level": "quiet"})
    assert m.source == "room_mic"
    _assert_bounds(m)


def test_room_perform_ve_alias() -> None:
    assert canonical_source("room_perform_ve") == "room_mic"


# ---------------------------------------------------------------------------
# Contact / membrane mic: vibration types
# ---------------------------------------------------------------------------


def test_contact_rain_vibration() -> None:
    m = interpret_source("contact_mic", {"vibration_type": "rain"})
    _assert_bounds(m)
    assert m.source == "contact_mic"
    assert m.rhythm > 0.5
    assert m.density > 0.5
    assert m.timbre < 0.6  # rain is not harsh


def test_contact_wind_vibration() -> None:
    m = interpret_source("contact_mic", {"vibration_type": "wind"})
    _assert_bounds(m)
    assert m.rhythm < 0.3
    assert m.density < 0.3
    assert m.deference > 0.6


def test_contact_impact_vibration() -> None:
    m = interpret_source("contact_mic", {"vibration_type": "impact"})
    _assert_bounds(m)
    assert m.rhythm > 0.7
    assert m.mix > 0.5
    assert m.deference < 0.4


def test_contact_active_without_profile() -> None:
    m = interpret_source("contact_mic", {"activity_level": "active", "recent_transient": True})
    _assert_bounds(m)
    assert m.rhythm > 0.5
    assert m.density > 0.4


def test_membrane_mic_alias() -> None:
    assert canonical_source("membrane_mic") == "contact_mic"
    m = interpret_source("membrane_mic", {"vibration_type": "impact"})
    assert m.source == "contact_mic"
    assert m.rhythm > 0.7


# ---------------------------------------------------------------------------
# Garden mic: inactivity, rain, wind
# ---------------------------------------------------------------------------


def test_garden_inactive_yields_minimal() -> None:
    m = interpret_source("garden_mic", {"activity_level": "quiet"})
    _assert_bounds(m)
    assert m.source == "garden_mic"
    assert m.density < 0.15
    assert m.rhythm < 0.15
    assert m.mix < 0.2
    assert m.deference > 0.7


def test_garden_rain_weather() -> None:
    m = interpret_source("garden_mic", {"weather": "rain"})
    _assert_bounds(m)
    assert m.rhythm > 0.5
    assert m.density > 0.5
    assert m.deference > 0.5  # rain is atmospheric, not assertive


def test_garden_wind_weather() -> None:
    m = interpret_source("garden_mic", {"weather": "wind"})
    _assert_bounds(m)
    assert m.density < 0.3
    assert m.rhythm < 0.2
    assert m.deference > 0.7


def test_garden_active_is_moderate() -> None:
    m = interpret_source("garden_mic", {"activity_level": "active"})
    _assert_bounds(m)
    assert m.density > 0.2
    assert m.rhythm > 0.2
    assert m.deference < 0.7


# ---------------------------------------------------------------------------
# Theramini: active vs idle
# ---------------------------------------------------------------------------


def test_theramini_active_leads() -> None:
    m = interpret_source("theramini_in", {"is_playing": True})
    _assert_bounds(m)
    assert m.source == "theramini_in"
    assert m.mix > 0.5
    assert m.deference < 0.3
    assert m.density > 0.2


def test_theramini_idle_yields() -> None:
    m = interpret_source("theramini_in", {"is_playing": False})
    _assert_bounds(m)
    assert m.mix == 0.0
    assert m.deference == 1.0
    assert m.rhythm == 0.0
    assert m.density == 0.0


def test_theramini_high_note_shifts_pitch() -> None:
    low = interpret_source("theramini_in", {"is_playing": True, "pitch_note": "C2"})
    high = interpret_source("theramini_in", {"is_playing": True, "pitch_note": "C6"})
    assert high.pitch > low.pitch


# ---------------------------------------------------------------------------
# Archive / self-bus: recall
# ---------------------------------------------------------------------------


def test_archive_active_recall() -> None:
    m = interpret_source("archive", {"is_playing": True, "rms": 0.3})
    _assert_bounds(m)
    assert m.source == "archive"
    assert m.mix > 0.2
    assert m.density > 0.2
    assert m.deference > 0.3  # archive is respectful but present


def test_archive_idle_is_silent() -> None:
    m = interpret_source("archive", {"is_playing": False})
    _assert_bounds(m)
    assert m.mix == 0.0
    assert m.density == 0.0
    assert m.deference == 1.0


def test_archive_clicks_suppressed() -> None:
    m = interpret_source("archive", {"is_playing": True, "has_clicks": True})
    _assert_bounds(m)
    assert m.mix == 0.0  # clicks = muted


def test_archive_age_warms_timbre() -> None:
    young = interpret_source("archive", {"is_playing": True, "age_factor": 0.0})
    old = interpret_source("archive", {"is_playing": True, "age_factor": 1.0})
    assert old.timbre < young.timbre  # older material is warmer (lower timbre)


# ---------------------------------------------------------------------------
# Network / weather
# ---------------------------------------------------------------------------


def test_network_quiet_is_background() -> None:
    m = interpret_source("network", {"activity": "quiet"})
    _assert_bounds(m)
    assert m.source == "network"
    assert m.mix < 0.25
    assert m.deference > 0.6


def test_network_storm_is_energetic() -> None:
    m = interpret_source("network", {"activity": "storm"})
    _assert_bounds(m)
    assert m.rhythm > 0.4
    assert m.density > 0.3
    assert m.deference < 0.5


def test_network_bps_derives_activity() -> None:
    quiet = interpret_source("network", {"bytes_per_second": 5000})
    busy = interpret_source("network", {"bytes_per_second": 2_000_000})
    assert busy.density > quiet.density
    assert busy.rhythm > quiet.rhythm


def test_network_weather_rain_shifts_timbre() -> None:
    clear = interpret_source("network", {"activity": "moderate", "weather": "clear"})
    rain = interpret_source("network", {"activity": "moderate", "weather": "rain"})
    assert rain.timbre < clear.timbre  # rain is darker


def test_network_weather_storm_adds_tension() -> None:
    calm = interpret_source("network", {"activity": "moderate", "weather": "clear"})
    storm = interpret_source("network", {"activity": "moderate", "weather": "storm"})
    assert storm.harmony > calm.harmony


def test_network_latency_adds_tension() -> None:
    low_lat = interpret_source("network", {"activity": "moderate", "latency_ms": 10})
    high_lat = interpret_source("network", {"activity": "moderate", "latency_ms": 400})
    assert high_lat.harmony > low_lat.harmony


# ---------------------------------------------------------------------------
# Unified interpreter and edge cases
# ---------------------------------------------------------------------------


def test_interpret_all_returns_all_provided() -> None:
    states = {
        "room_mic": {"activity_level": "quiet"},
        "theramini_in": {"is_playing": True},
        "network": {"activity": "busy"},
    }
    result = interpret_all(states)
    assert set(result.keys()) == {"room_mic", "theramini_in", "network"}
    for mapping in result.values():
        _assert_bounds(mapping)


def test_interpret_all_resolves_aliases() -> None:
    result = interpret_all({"perform_ve_condenser": {"activity_level": "active"}})
    assert "room_mic" in result
    assert result["room_mic"].source == "room_mic"


def test_unknown_source_raises() -> None:
    try:
        interpret_source("nonexistent_mic", {})
        assert False, "Expected KeyError"
    except KeyError:
        pass


def test_empty_state_produces_valid_mapping() -> None:
    """Every source must handle an empty state dict gracefully."""
    for source in KNOWN_SOURCES:
        m = interpret_source(source, {})
        _assert_bounds(m)


def test_all_sources_have_interpreters() -> None:
    """Every known source name must have a registered interpreter."""
    for source in KNOWN_SOURCES:
        m = interpret_source(source, {})
        assert m.source == source
