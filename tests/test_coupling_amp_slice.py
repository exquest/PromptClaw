"""DSP-free cross-voice coupling slice (the seam wired into duet_composer).

The full PRD coupling feature scales each voice's *modulator depths*
(vibrato/tremolo) by ``1 + strength*affect``. The live cypherclaw melodic
synthdefs have NO modulation surface (fire-and-forget; freq/amp/env only), so
the deployed slice rides the one control that exists — ``amp`` — exactly as the
expression and fatigue layers do. These tests pin that DSP-free recipe:

  * each note READS the ensemble's recent max-pooled affect, THEN contributes
    its own intensity (read-before-write — a note couples to *others'* recent
    activity, not itself);
  * the bus max-pools across voices and slow-decays in gaps;
  * the amp multiplier is bounded and identity when the flag is OFF.

The writer/reader internals themselves are covered by
``test_affective_state_bus`` and ``test_two_voice_coupling_integration``; this
file guards the composition the composer depends on.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import pytest

from senseweave.affective_state_bus import (
    DEFAULT_COUPLING_STRENGTH,
    AffectiveStateBusWriter,
    coupling_multiplier_from_bus_value,
)


class _NoopClient:
    """In-process stand-in: the composer flushes the writer to read the
    pooled/decayed affect but never round-trips to scsynth (no synthdef reads
    bus 100), so `/c_set` writes are dropped."""

    def send_message(self, address: str, args: list) -> None:  # noqa: D401
        pass


def _coupling_note(writer: AffectiveStateBusWriter, voice_id: str, intensity: float, *, now: float) -> float:
    """Mirror the play_voice seam: read ensemble affect, scale, then contribute.

    Returns the amp multiplier the note would receive.
    """
    client = _NoopClient()
    affect = writer.flush(client, now=now)
    mult = coupling_multiplier_from_bus_value(affect)
    writer.update(voice_id, intensity, now=now)
    return mult


class TestCouplingAmpSlice:
    def test_first_note_couples_to_nothing(self) -> None:
        """An opening note (empty bus) sees affect 0 -> multiplier 1.0."""
        writer = AffectiveStateBusWriter(enabled=True)
        mult = _coupling_note(writer, "melody|pluck", 0.9, now=0.0)
        assert mult == pytest.approx(1.0)

    def test_note_couples_to_others_recent_activity(self) -> None:
        """After other voices play intensely, a new note's amp swells."""
        writer = AffectiveStateBusWriter(enabled=True)
        # Two voices contribute high intensity at t=0..0.5 (within the 2s window).
        _coupling_note(writer, "melody|pluck", 0.9, now=0.0)
        _coupling_note(writer, "counter|bowed", 0.9, now=0.5)
        # A third note at t=1.0 reads the max-pooled affect from the prior two.
        mult = _coupling_note(writer, "bass|drone", 0.2, now=1.0)
        assert mult == pytest.approx(1.0 + DEFAULT_COUPLING_STRENGTH * 0.9)
        assert 1.0 < mult <= 1.0 + DEFAULT_COUPLING_STRENGTH

    def test_bus_max_pools_across_voices(self) -> None:
        """The loudest active voice sets the ensemble affect (max-pool)."""
        writer = AffectiveStateBusWriter(enabled=True)
        _coupling_note(writer, "melody|pluck", 0.3, now=0.0)
        _coupling_note(writer, "counter|bowed", 0.8, now=0.1)
        mult = _coupling_note(writer, "bass|drone", 0.1, now=0.2)
        assert mult == pytest.approx(1.0 + DEFAULT_COUPLING_STRENGTH * 0.8)

    def test_coupling_decays_when_ensemble_goes_quiet(self) -> None:
        """A long gap with no notes lets the swell decay back toward base amp."""
        writer = AffectiveStateBusWriter(enabled=True)
        _coupling_note(writer, "melody|pluck", 0.9, now=0.0)
        # Next note at t=0.5 sees the prior activity (boosted)...
        near = _coupling_note(writer, "melody|pluck", 0.9, now=0.5)
        # ...but a note after a long gap (window pruned, bus decayed ~4 taus)
        # sees essentially base amp again.
        far = _coupling_note(writer, "melody|pluck", 0.0, now=20.5)
        assert near > far
        assert far == pytest.approx(1.0, abs=0.05)

    def test_multiplier_bounded_for_phase_intensity_range(self) -> None:
        """Scene-phase M in [0, 0.9] keeps the boost in [1.0, 1.45]."""
        assert coupling_multiplier_from_bus_value(0.0) == pytest.approx(1.0)
        assert coupling_multiplier_from_bus_value(0.9) == pytest.approx(1.45)

    def test_disabled_writer_is_inert(self) -> None:
        """Flag OFF -> writer no-op -> every note's multiplier is identity 1.0."""
        writer = AffectiveStateBusWriter(enabled=False)
        first = _coupling_note(writer, "melody|pluck", 0.9, now=0.0)
        second = _coupling_note(writer, "counter|bowed", 0.9, now=0.5)
        assert first == pytest.approx(1.0)
        assert second == pytest.approx(1.0)

    def test_read_before_write_excludes_self(self) -> None:
        """A lone voice never couples to its own just-played note."""
        writer = AffectiveStateBusWriter(enabled=True)
        # Same voice plays repeatedly; each note reads only PRIOR contributions.
        first = _coupling_note(writer, "melody|pluck", 0.9, now=0.0)
        assert first == pytest.approx(1.0)  # nothing before it
        # The second note DOES see the first (it's prior activity), so > 1.0.
        second = _coupling_note(writer, "melody|pluck", 0.9, now=0.3)
        assert second > 1.0
