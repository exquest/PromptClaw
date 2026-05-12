"""ContinuousLearner — learn by performing, reflect in real-time, evolve.

No separation between practice and performance. Every note is both.
Every song teaches the next one. The system reflects, adjusts, and grows
while playing.

Wraps the MelodicMind and LLMAdvisor into a feedback loop:
  PLAY → RECORD → REFLECT → ADJUST → EVALUATE → EVOLVE → PLAY
"""
from __future__ import annotations

import json
import math
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence


@dataclass
class PlayedNote:
    """A note that was actually played."""
    freq: float
    duration: float
    accent: bool
    voice: str
    timestamp: float
    chord_context: list[int] | None = None


@dataclass
class SongRecord:
    """Record of a complete song for evaluation."""
    song_num: int
    key: str
    feel: str
    bpm: float
    notes: list[PlayedNote] = field(default_factory=list)
    started_at: float = 0.0
    critique: str = ""
    score: float = 0.0
    adjustments_made: list[str] = field(default_factory=list)
    context_tags: list[str] = field(default_factory=list)


@dataclass
class GrowthState:
    """Tracks how the system is evolving over time."""
    total_songs: int = 0
    total_notes: int = 0
    keys_explored: set = field(default_factory=set)
    feels_explored: set = field(default_factory=set)
    chromatic_notes_ratio: float = 0.0
    avg_phrase_variety: float = 0.0
    recent_critiques: list[str] = field(default_factory=list)
    recent_ear_metrics: list[dict[str, float]] = field(default_factory=list)
    parameter_history: list[dict] = field(default_factory=list)

    # Current parameter adjustments from learning
    chromatic_adjustment: float = 0.0    # -0.2 to +0.2
    tempo_adjustment: float = 0.0        # -20 to +20 BPM
    leap_adjustment: float = 0.0         # -0.1 to +0.1
    rest_adjustment: float = 0.0         # -0.05 to +0.05


GROWTH_PATH = Path("/home/user/cypherclaw-data/state/growth_journal.json")


class ContinuousLearner:
    """The learning loop that wraps every performance."""

    def __init__(self, llm_advisor=None):
        self.llm = llm_advisor
        self.current_song: SongRecord | None = None
        self.recent_songs: list[SongRecord] = []
        self.growth = self._load_growth()
        self._note_buffer: list[PlayedNote] = []
        self._last_reflect_time = 0.0
        self.reflect_interval = 30.0  # seconds between micro-critiques

    # === RECORD ===

    def start_song(
        self,
        song_num: int,
        key: str,
        feel: str,
        bpm: float,
        *,
        context_tags: Sequence[str] | None = None,
    ) -> None:
        """Call when a new song begins."""
        self.current_song = SongRecord(
            song_num=song_num, key=key, feel=feel, bpm=bpm,
            started_at=time.time(),
            context_tags=[str(tag) for tag in (context_tags or []) if str(tag).strip()],
        )
        self._note_buffer.clear()
        self.growth.total_songs += 1
        self.growth.keys_explored.add(key)
        self.growth.feels_explored.add(feel)

    def record_note(self, freq: float, duration: float, accent: bool,
                    voice: str = "pluck", chord: list[int] | None = None) -> None:
        """Call every time a note is played."""
        note = PlayedNote(
            freq=freq, duration=duration, accent=accent,
            voice=voice, timestamp=time.time(), chord_context=chord,
        )
        self._note_buffer.append(note)
        if self.current_song:
            self.current_song.notes.append(note)
        self.growth.total_notes += 1

    # === REFLECT (in real-time, every 30s) ===

    def maybe_reflect(self) -> dict | None:
        """Call frequently. Returns adjustment dict if it's time to reflect."""
        now = time.time()
        if now - self._last_reflect_time < self.reflect_interval:
            return None
        if len(self._note_buffer) < 8:
            return None

        self._last_reflect_time = now
        return self._micro_critique()

    def _micro_critique(self) -> dict:
        """Analyze recent notes and suggest adjustments."""
        recent = self._note_buffer[-16:]
        adjustments = {}

        # Self-analysis (no LLM needed)
        freqs = [n.freq for n in recent if n.freq > 0]
        if len(freqs) >= 4:
            # Check for repetition
            intervals = [freqs[i+1] / freqs[i] for i in range(len(freqs)-1) if freqs[i] > 0]
            unique_intervals = len(set(round(iv, 3) for iv in intervals))
            variety = unique_intervals / max(len(intervals), 1)

            if variety < 0.3:
                adjustments["critique"] = "too repetitive — more variety needed"
                adjustments["chromatic_bump"] = 0.05
                adjustments["leap_bump"] = 0.03
            elif variety > 0.8:
                adjustments["critique"] = "too scattered — find a thread"
                adjustments["chromatic_bump"] = -0.03
                adjustments["leap_bump"] = -0.02

            # Check for stepwise monotony
            steps = sum(1 for iv in intervals if 0.85 < iv < 1.15)
            step_ratio = steps / max(len(intervals), 1)
            if step_ratio > 0.8:
                adjustments["critique"] = "too stepwise — try some leaps"
                adjustments["leap_bump"] = 0.05
            elif step_ratio < 0.2:
                adjustments["critique"] = "too jumpy — more stepwise motion"
                adjustments["leap_bump"] = -0.05

            # Check rhythm variety
            durs = [n.duration for n in recent]
            unique_durs = len(set(round(d, 2) for d in durs))
            if unique_durs <= 2:
                adjustments["critique"] = "rhythmically flat — vary note lengths"
                adjustments["rest_bump"] = 0.02

        # LLM critique if available and we have enough data
        if self.llm and len(freqs) >= 8:
            try:
                key = self.current_song.key if self.current_song else "C"
                feel = self.current_song.feel if self.current_song else "waltz"
                llm_critique = self.llm.critique_phrase(freqs[:8], key, feel)
                if llm_critique:
                    adjustments["llm_critique"] = llm_critique
                    # Parse LLM response for actionable keywords
                    lower = llm_critique.lower()
                    if "chromatic" in lower or "color" in lower:
                        adjustments["chromatic_bump"] = adjustments.get("chromatic_bump", 0) + 0.03
                    if "predictable" in lower or "boring" in lower or "safe" in lower:
                        adjustments["chromatic_bump"] = adjustments.get("chromatic_bump", 0) + 0.05
                        adjustments["leap_bump"] = adjustments.get("leap_bump", 0) + 0.03
                    if "too much" in lower or "chaotic" in lower or "random" in lower:
                        adjustments["chromatic_bump"] = adjustments.get("chromatic_bump", 0) - 0.05
                    if "rest" in lower or "space" in lower or "breathe" in lower:
                        adjustments["rest_bump"] = adjustments.get("rest_bump", 0) + 0.03
            except Exception:
                pass

        if adjustments:
            self._apply_adjustments(adjustments)

        return adjustments

    def _apply_adjustments(self, adj: dict) -> None:
        """Apply micro-adjustments to growth state."""
        if "chromatic_bump" in adj:
            self.growth.chromatic_adjustment = max(-0.2, min(0.2,
                self.growth.chromatic_adjustment + adj["chromatic_bump"]))
        if "leap_bump" in adj:
            self.growth.leap_adjustment = max(-0.1, min(0.1,
                self.growth.leap_adjustment + adj["leap_bump"]))
        if "rest_bump" in adj:
            self.growth.rest_adjustment = max(-0.05, min(0.05,
                self.growth.rest_adjustment + adj["rest_bump"]))

        critique = adj.get("critique", adj.get("llm_critique", ""))
        if critique:
            self.growth.recent_critiques.append(critique)
            if len(self.growth.recent_critiques) > 20:
                self.growth.recent_critiques.pop(0)

        if self.current_song:
            self.current_song.adjustments_made.append(str(adj))

    # === EVALUATE (end of song) ===

    def end_song(self, memory=None) -> dict:
        """Call when a song ends. Evaluates and stores fragments."""
        if not self.current_song:
            return {}

        song = self.current_song
        result = {"song_num": song.song_num, "notes_played": len(song.notes)}
        from ..ear_engine import analyze_played_notes

        result["ear_metrics"] = analyze_played_notes(song.notes)
        self.growth.recent_ear_metrics.append(dict(result["ear_metrics"]))
        if len(self.growth.recent_ear_metrics) > 20:
            self.growth.recent_ear_metrics = self.growth.recent_ear_metrics[-20:]

        # Find the best 4-note fragment
        if len(song.notes) >= 4:
            best_fragment, best_score = self._find_best_fragment(song.notes)
            result["best_fragment"] = [n.freq for n in best_fragment]
            result["fragment_score"] = best_score

            # Store if good enough
            if memory and best_score > 0.5:
                tags = " ".join(song.context_tags).strip()
                context = f"{song.key}_{song.feel}_{time.strftime('%H')}"
                if tags:
                    context = f"{context} {tags}"
                memory.store_fragment(
                    [n.freq for n in best_fragment],
                    context,
                    best_score,
                )
                result["fragment_stored"] = True

        # LLM end-of-song evaluation
        if self.llm and len(song.notes) >= 8:
            try:
                freqs = [n.freq for n in song.notes[:16] if n.freq > 0]
                score = self.llm.evaluate_fragment(freqs[:8])
                song.score = score
                result["llm_score"] = score
            except Exception:
                pass

        # Record parameter state for growth tracking
        self.growth.parameter_history.append({
            "song": song.song_num,
            "time": time.time(),
            "chromatic_adj": self.growth.chromatic_adjustment,
            "leap_adj": self.growth.leap_adjustment,
            "rest_adj": self.growth.rest_adjustment,
            "score": song.score,
            "ear_metrics": dict(result["ear_metrics"]),
        })
        if len(self.growth.parameter_history) > 100:
            self.growth.parameter_history = self.growth.parameter_history[-50:]

        self.recent_songs.append(song)
        if len(self.recent_songs) > 10:
            self.recent_songs.pop(0)

        self._save_growth()
        self.current_song = None
        return result

    def recent_fragments(
        self,
        *,
        context_tags: Sequence[str] | None = None,
        count: int = 6,
        min_score: float = 0.45,
    ) -> list[dict]:
        """Return strong recent fragments, preferring songs with matching context tags."""
        normalized = {
            str(tag).strip().lower()
            for tag in (context_tags or [])
            if str(tag).strip()
        }
        matches: list[tuple[int, float, float, dict]] = []
        fallbacks: list[tuple[float, float, dict]] = []
        for song in reversed(self.recent_songs):
            if len(song.notes) < 4:
                continue
            fragment, score = self._find_best_fragment(song.notes)
            if score < min_score:
                continue
            song_tags = {
                str(tag).strip().lower()
                for tag in song.context_tags
                if str(tag).strip()
            }
            context = f"{song.key}_{song.feel}_{time.strftime('%H', time.localtime(song.started_at or time.time()))}"
            if song.context_tags:
                context = f"{context} {' '.join(song.context_tags)}"
            payload = {
                "notes": [note.freq for note in fragment],
                "context": context,
                "score": score,
                "stored_at": song.started_at,
                "root": fragment[0].freq if fragment else 0.0,
            }
            match_count = len(normalized & song_tags)
            if match_count > 0:
                matches.append((match_count, score, song.started_at, payload))
            else:
                fallbacks.append((score, song.started_at, payload))

        if matches:
            matches.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
            return [payload for *_meta, payload in matches[:count]]

        fallbacks.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [payload for *_meta, payload in fallbacks[:count]]

    def _find_best_fragment(self, notes: list[PlayedNote]) -> tuple[list[PlayedNote], float]:
        """Find the most interesting 4-note fragment in a song."""
        best = notes[:4]
        best_score = 0.0

        for i in range(len(notes) - 3):
            fragment = notes[i:i+4]
            freqs = [n.freq for n in fragment if n.freq > 0]
            if len(freqs) < 3:
                continue

            score = 0.0
            # Variety of intervals
            intervals = [freqs[j+1] / freqs[j] for j in range(len(freqs)-1) if freqs[j] > 0]
            unique = len(set(round(iv, 2) for iv in intervals))
            score += unique * 0.2

            # Has a leap (interval > major third)
            has_leap = any(iv > 1.26 or iv < 0.79 for iv in intervals)
            if has_leap:
                score += 0.2

            # Has chromatic motion (small intervals)
            has_chromatic = any(0.94 < iv < 1.06 and iv != 1.0 for iv in intervals)
            if has_chromatic:
                score += 0.15

            # Rhythmic variety
            durs = [n.duration for n in fragment]
            if len(set(round(d, 2) for d in durs)) > 1:
                score += 0.15

            # Has an accent
            if any(n.accent for n in fragment):
                score += 0.1

            score = min(1.0, score)
            if score > best_score:
                best_score = score
                best = fragment

        return best, best_score

    # === EVOLVE (inform the next song) ===

    def get_adjustments_for_mind(self) -> dict:
        """Return current parameter adjustments for MelodicMind.

        The composer calls this before each song to get learned adjustments.
        """
        return {
            "chromatic_adjustment": self.growth.chromatic_adjustment,
            "leap_adjustment": self.growth.leap_adjustment,
            "rest_adjustment": self.growth.rest_adjustment,
            "songs_played": self.growth.total_songs,
            "keys_explored": len(self.growth.keys_explored),
            "feels_explored": len(self.growth.feels_explored),
        }

    def suggest_exploration(self) -> dict | None:
        """Suggest something new to try based on what's been explored."""
        all_keys = {"C", "D", "E", "F", "G", "A", "Bb", "B"}
        all_feels = {"waltz", "ragtime", "nocturne", "ballad", "beguine", "march"}

        unexplored_keys = all_keys - self.growth.keys_explored
        unexplored_feels = all_feels - self.growth.feels_explored

        suggestions = {}
        if unexplored_keys:
            suggestions["try_key"] = random.choice(list(unexplored_keys))
        if unexplored_feels:
            suggestions["try_feel"] = random.choice(list(unexplored_feels))

        # If we've been too safe (low chromatic), suggest more color
        if self.growth.chromatic_adjustment < -0.1:
            suggestions["push_chromatic"] = True

        return suggestions if suggestions else None

    # === PERSISTENCE ===

    def _load_growth(self) -> GrowthState:
        try:
            if GROWTH_PATH.exists():
                data = json.loads(GROWTH_PATH.read_text())
                gs = GrowthState()
                gs.total_songs = data.get("total_songs", 0)
                gs.total_notes = data.get("total_notes", 0)
                gs.keys_explored = set(data.get("keys_explored", []))
                gs.feels_explored = set(data.get("feels_explored", []))
                gs.chromatic_adjustment = data.get("chromatic_adjustment", 0.0)
                gs.leap_adjustment = data.get("leap_adjustment", 0.0)
                gs.rest_adjustment = data.get("rest_adjustment", 0.0)
                gs.recent_critiques = data.get("recent_critiques", [])
                gs.recent_ear_metrics = data.get("recent_ear_metrics", [])
                gs.parameter_history = data.get("parameter_history", [])
                return gs
        except (json.JSONDecodeError, OSError):
            pass
        return GrowthState()

    def _save_growth(self) -> None:
        try:
            GROWTH_PATH.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "total_songs": self.growth.total_songs,
                "total_notes": self.growth.total_notes,
                "keys_explored": list(self.growth.keys_explored),
                "feels_explored": list(self.growth.feels_explored),
                "chromatic_adjustment": self.growth.chromatic_adjustment,
                "leap_adjustment": self.growth.leap_adjustment,
                "rest_adjustment": self.growth.rest_adjustment,
                "recent_critiques": self.growth.recent_critiques,
                "recent_ear_metrics": self.growth.recent_ear_metrics[-20:],
                "parameter_history": self.growth.parameter_history[-50:],
                "saved_at": time.time(),
            }
            tmp = GROWTH_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            os.replace(str(tmp), str(GROWTH_PATH))
        except OSError:
            pass
