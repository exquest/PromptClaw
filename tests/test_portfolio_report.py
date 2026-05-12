"""Tests for artistic identity portfolio reporting and surface snapshots."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.artistic_identity import ArtisticIdentity
from senseweave.portfolio_report import (
    PortfolioReport,
    SurfaceSnapshot,
    derive_portfolio_report,
    derive_surface_snapshot,
)


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

def _sample_songs() -> list[dict]:
    return [
        {
            "title": "Quiet Rooms",
            "family": "bloom",
            "patch_name": "house_garden",
            "hook_text": "keep the room open",
            "form_class": "song",
            "composition_mode": "hook_led",
            "practice_block": "harmony_lab",
            "ear_metrics": {
                "hook_clarity": 0.85,
                "cadence_strength": 0.70,
                "development_score": 0.55,
            },
            "score_tree_summary": {
                "motif_ids": ["m1", "m2"],
                "section_functions": ["exposition", "development"],
            },
        },
        {
            "title": "Near Thresholds",
            "family": "bloom",
            "patch_name": "house_garden",
            "hook_text": "the threshold hums",
            "form_class": "song",
            "composition_mode": "hook_led",
            "practice_block": "melody_lab",
            "ear_metrics": {
                "hook_clarity": 0.75,
                "cadence_strength": 0.80,
                "development_score": 0.45,
            },
            "score_tree_summary": {
                "motif_ids": ["m1", "m3"],
                "section_functions": ["exposition", "recapitulation"],
            },
        },
        {
            "title": "Moving Lines",
            "family": "ember",
            "patch_name": "house_chamber",
            "hook_text": "let the line ring",
            "form_class": "micro",
            "composition_mode": "through_composed",
            "practice_block": "harmony_lab",
            "ear_metrics": {
                "hook_clarity": 0.60,
                "cadence_strength": 0.65,
                "development_score": 0.70,
            },
            "score_tree_summary": {
                "motif_ids": ["m4"],
                "section_functions": ["exposition"],
            },
        },
    ]


# ---------------------------------------------------------------------------
# AC1: Portfolio report derives identity from repertoire metrics
# ---------------------------------------------------------------------------


class TestPortfolioReportFromRepertoire:
    def test_identity_included(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert isinstance(report.identity, ArtisticIdentity)
        assert report.identity.signature_families[0] == "bloom"
        assert report.identity.signature_patches[0] == "house_garden"

    def test_total_songs_counted(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert report.total_songs == 3

    def test_promoted_count(self) -> None:
        promoted = [_sample_songs()[0]]
        report = derive_portfolio_report(_sample_songs(), promoted_songs=promoted)
        assert report.total_promoted == 1

    def test_preferred_forms_extracted(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert "song" in report.preferred_forms
        assert isinstance(report.preferred_forms, tuple)

    def test_preferred_modes_extracted(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert "hook_led" in report.preferred_modes
        assert isinstance(report.preferred_modes, tuple)

    def test_motif_count(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        # m1, m2, m3, m4 = 4 unique motifs
        assert report.signature_motif_count == 4

    def test_practice_blocks_visited(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert "harmony_lab" in report.practice_blocks_visited
        assert "melody_lab" in report.practice_blocks_visited

    def test_course_codes_from_practice(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        # harmony_lab -> EMSD-110, EMSD-302; melody_lab -> EMSD-110, EMSD-303
        assert "EMSD-110" in report.course_codes_covered
        assert "EMSD-302" in report.course_codes_covered
        assert "EMSD-303" in report.course_codes_covered

    def test_families_explored_from_songs(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert "bloom" in report.families_explored
        assert "ember" in report.families_explored

    def test_keys_explored_from_growth(self) -> None:
        growth = {"keys_explored": ["C", "D", "G"]}
        report = derive_portfolio_report(_sample_songs(), growth=growth)
        assert "C" in report.keys_explored
        assert "G" in report.keys_explored

    def test_keys_explored_fallback_to_songs(self) -> None:
        songs = [dict(s, key="Am") for s in _sample_songs()[:1]]
        report = derive_portfolio_report(songs)
        assert "Am" in report.keys_explored

    def test_avg_ear_metrics(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        # hook_clarity: (0.85 + 0.75 + 0.60) / 3 ≈ 0.733
        assert 0.70 < report.avg_hook_clarity < 0.77
        # cadence_strength: (0.70 + 0.80 + 0.65) / 3 ≈ 0.717
        assert 0.70 < report.avg_cadence_strength < 0.73
        # development_score: (0.55 + 0.45 + 0.70) / 3 ≈ 0.567
        assert 0.55 < report.avg_development_score < 0.58

    def test_report_is_frozen(self) -> None:
        report = derive_portfolio_report(_sample_songs())
        assert isinstance(report, PortfolioReport)


# ---------------------------------------------------------------------------
# AC3: Stable identity summaries without hallucinated missing data
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    def test_empty_songs(self) -> None:
        report = derive_portfolio_report([])
        assert report.total_songs == 0
        assert report.total_promoted == 0
        assert report.avg_hook_clarity == 0.0
        assert report.avg_cadence_strength == 0.0
        assert report.avg_development_score == 0.0
        assert report.signature_motif_count == 0
        assert len(report.practice_blocks_visited) == 0
        assert len(report.course_codes_covered) == 0
        # Identity should still have sensible defaults
        assert len(report.identity.signature_families) > 0
        assert report.identity.statement != ""

    def test_songs_missing_optional_fields(self) -> None:
        sparse_songs = [
            {"title": "Bare Song", "family": "bloom"},
            {"title": "Another", "family": "ember", "patch_name": "house_chamber"},
        ]
        report = derive_portfolio_report(sparse_songs)
        assert report.total_songs == 2
        assert report.avg_hook_clarity == 0.0
        assert report.signature_motif_count == 0
        assert len(report.preferred_forms) == 0

    def test_songs_with_empty_string_fields(self) -> None:
        songs = [
            {
                "title": "Test",
                "family": "bloom",
                "form_class": "",
                "composition_mode": "",
                "practice_block": "",
                "ear_metrics": {},
            },
        ]
        report = derive_portfolio_report(songs)
        assert report.total_songs == 1
        assert len(report.preferred_forms) == 0
        assert len(report.preferred_modes) == 0
        assert len(report.practice_blocks_visited) == 0

    def test_corrupt_score_tree_summary(self) -> None:
        songs = [
            {
                "title": "Corrupt",
                "family": "bloom",
                "score_tree_summary": {"missing_motif_ids": True},
            },
        ]
        report = derive_portfolio_report(songs)
        assert report.signature_motif_count == 0

    def test_growth_state_with_list_keys(self) -> None:
        growth = {"keys_explored": ["C", "D"], "feels_explored": ["calm"]}
        report = derive_portfolio_report([], growth=growth)
        assert "C" in report.keys_explored
        assert "D" in report.keys_explored

    def test_none_growth_state(self) -> None:
        report = derive_portfolio_report(_sample_songs(), growth=None)
        # Should fall back to extracting from songs
        assert isinstance(report.keys_explored, tuple)

    def test_no_division_by_zero_on_empty_metrics(self) -> None:
        songs = [{"title": "No Metrics", "family": "bloom"}]
        report = derive_portfolio_report(songs)
        assert report.avg_hook_clarity == 0.0
        assert report.avg_cadence_strength == 0.0
        assert report.avg_development_score == 0.0


# ---------------------------------------------------------------------------
# AC2: Surface snapshot for face/operator display
# ---------------------------------------------------------------------------


class TestSurfaceSnapshot:
    def test_full_snapshot(self) -> None:
        identity = ArtisticIdentity(
            signature_families=("bloom",),
            signature_patches=("house_garden",),
            signature_images=("room",),
            statement="CypherClaw leans toward bloom forms, speaks through house_garden, and returns to room imagery.",
        )
        snap = derive_surface_snapshot(
            current_song={"title": "Quiet Rooms"},
            identity=identity,
            practice_block="Harmony Lab",
            section_function="Exposition",
        )
        assert snap.song_title == "Quiet Rooms"
        assert snap.section_caption == "Exposition"
        assert snap.practice_block == "Harmony Lab"
        assert "bloom" in snap.artistic_intent

    def test_idle_snapshot_no_song(self) -> None:
        snap = derive_surface_snapshot()
        assert snap.song_title == ""
        assert snap.section_caption == ""
        assert snap.practice_block == ""
        assert snap.artistic_intent == ""

    def test_snapshot_no_identity(self) -> None:
        snap = derive_surface_snapshot(
            current_song={"title": "Test Song"},
            practice_block="Ear Lab",
        )
        assert snap.song_title == "Test Song"
        assert snap.practice_block == "Ear Lab"
        assert snap.artistic_intent == ""

    def test_snapshot_no_current_song_with_identity(self) -> None:
        identity = ArtisticIdentity(
            signature_families=("ember",),
            signature_patches=("house_chamber",),
            signature_images=("line",),
            statement="CypherClaw leans toward ember forms.",
        )
        snap = derive_surface_snapshot(identity=identity)
        assert snap.song_title == ""
        assert snap.artistic_intent != ""

    def test_snapshot_is_frozen(self) -> None:
        snap = derive_surface_snapshot()
        assert isinstance(snap, SurfaceSnapshot)
