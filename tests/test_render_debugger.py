"""Tests for the SenseWeave render localization debugger."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Mapping, Sequence

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

from senseweave.generative_scores import Note, Phrase, Score
from senseweave.render import ProblemRegion, localize_rule_impacts
from senseweave.render import debugger


def _score() -> Score:
    return Score(
        phrases=[
            Phrase(
                notes=[Note(1, 1.0, False), Note(3, 1.0, False)],
                voice="pluck",
                dynamic="mf",
                role="melody",
            ),
            Phrase(
                notes=[Note(5, 2.0, False)],
                voice="bell",
                dynamic="mp",
                role="color",
            ),
        ],
        key="C",
        tempo_bpm=120.0,
        mood="neutral",
        created_at=0.0,
    )


def _rule_ids(rules: Sequence[object]) -> set[str]:
    return {getattr(rule, "rule_id", rule) for rule in rules}


def _render_debug_score(
    score: Score,
    *,
    seeds: Mapping[str, int] | None,
    rules: Sequence[object],
) -> Score:
    del seeds
    active = _rule_ids(rules)
    first_phrase_notes = [Note(note.scale_degree, note.duration_beats, note.accent) for note in score.phrases[0].notes]
    second_phrase_voice = score.phrases[1].voice
    if "melody_leap" in active:
        first_phrase_notes[1] = Note(7, 1.5, first_phrase_notes[1].accent)
    if "accent_flip" in active:
        first_phrase_notes[1] = Note(
            first_phrase_notes[1].scale_degree,
            first_phrase_notes[1].duration_beats,
            True,
        )
    if "color_shift" in active:
        second_phrase_voice = "pad"
    return Score(
        phrases=[
            Phrase(
                notes=first_phrase_notes,
                voice=score.phrases[0].voice,
                dynamic=score.phrases[0].dynamic,
                role=score.phrases[0].role,
            ),
            Phrase(
                notes=[
                    Note(
                        score.phrases[1].notes[0].scale_degree,
                        score.phrases[1].notes[0].duration_beats,
                        score.phrases[1].notes[0].accent,
                    )
                ],
                voice=second_phrase_voice,
                dynamic=score.phrases[1].dynamic,
                role=score.phrases[1].role,
            ),
        ],
        key=score.key,
        tempo_bpm=score.tempo_bpm,
        mood=score.mood,
        created_at=score.created_at,
    )


def test_localize_rule_impacts_runs_single_and_pair_ablation() -> None:
    report = localize_rule_impacts(
        _score(),
        {"interpretation": 7},
        active_rules=("melody_leap", "accent_flip", "color_shift"),
        renderer=_render_debug_score,
        problem_region=ProblemRegion.from_selection(
            note_indices=[(0, 1)],
            include_global=False,
        ),
        max_combination_size=2,
    )

    assert len(report.ablation_runs) == 6
    assert report.top_rule is not None
    assert report.top_rule.rule_id == "melody_leap"
    assert report.top_rule.single_impact == 2.0
    assert report.top_rule.combination_impact == 3.0
    assert report.ranked_rules[-1].rule_id == "color_shift"
    assert report.ranked_rules[-1].single_impact == 0.0
    assert report.ablation_runs[0].disabled_rules == ("melody_leap",)
    assert "note" in report.ablation_runs[0].summary


def test_debugger_cli_writes_json_report(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    renderer_file = tmp_path / "debug_renderer_fixture.py"
    renderer_file.write_text(
        "\n".join(
            [
                "from senseweave.generative_scores import Note, Phrase, Score",
                "",
                "def render(score, *, seeds, rules):",
                "    del seeds",
                "    active = {getattr(rule, 'rule_id', rule) for rule in rules}",
                "    degree = 5 if 'melody_leap' in active else score.phrases[0].notes[0].scale_degree",
                "    voice = 'pad' if 'color_shift' in active else score.phrases[1].voice",
                "    return Score(",
                "        phrases=[",
                "        Phrase(",
                "            notes=[Note(degree, score.phrases[0].notes[0].duration_beats, False)],",
                "            voice=score.phrases[0].voice,",
                "            dynamic=score.phrases[0].dynamic,",
                "            role=score.phrases[0].role,",
                "        ),",
                "        Phrase(",
                "            notes=[Note(score.phrases[1].notes[0].scale_degree, 1.0, False)],",
                "            voice=voice,",
                "            dynamic=score.phrases[1].dynamic,",
                "            role=score.phrases[1].role,",
                "        ),",
                "        ],",
                "        key=score.key,",
                "        tempo_bpm=score.tempo_bpm,",
                "        mood=score.mood,",
                "        created_at=score.created_at,",
                "    )",
            ]
        )
    )
    monkeypatch.syspath_prepend(str(tmp_path))

    score_file = tmp_path / "score.json"
    score_file.write_text(
        json.dumps(
            {
                "phrases": [
                    {
                        "notes": [
                            {
                                "scale_degree": 1,
                                "duration_beats": 1.0,
                                "accent": False,
                            }
                        ],
                        "voice": "pluck",
                        "dynamic": "mf",
                        "role": "melody",
                    },
                    {
                        "notes": [
                            {
                                "scale_degree": 4,
                                "duration_beats": 1.0,
                                "accent": False,
                            }
                        ],
                        "voice": "bell",
                        "dynamic": "mp",
                        "role": "color",
                    }
                ],
                "key": "C",
                "tempo_bpm": 120.0,
                "mood": "neutral",
                "created_at": 0.0,
            }
        )
    )
    output = tmp_path / "report.json"

    exit_code = debugger.main(
        [
            "--score",
            str(score_file),
            "--renderer",
            "debug_renderer_fixture:render",
            "--rules",
            "melody_leap,color_shift",
            "--note",
            "0:0",
            "--max-combination-size",
            "1",
            "--output",
            str(output),
        ]
    )

    report = json.loads(output.read_text())
    assert exit_code == 0
    assert report["ranked_rules"][0]["rule_id"] == "melody_leap"
    assert report["ranked_rules"][0]["single_impact"] == 1.0
    assert report["ablation_runs"][0]["summary"] == "1 note scale_degree change(s)"
