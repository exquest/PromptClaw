"""SenseweaveVoice — ADSR-controlled texture instrument for the composer.

The senseweave becomes an instrument the composer can play, not a
separate system. The composer decides WHAT to play (pitch, timing,
key). The senseweave decides HOW it sounds (timbre, texture).

ADSR presets:
  pad:       A=3.0  D=0.5  S=0.8  R=4.0  — ambient bed
  swell:     A=2.0  D=0.3  S=0.9  R=2.0  — phrase-length rise
  stab:      A=0.01 D=0.1  S=0.0  R=0.3  — orchestral sforzando
  rhythmic:  A=0.01 D=0.05 S=0.0  R=0.15 — percussive texture hit
  breath:    A=1.5  D=0.3  S=0.6  R=3.0  — wind-like color
  shimmer:   A=0.5  D=0.2  S=0.7  R=1.5  — bright sustained texture
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol


class OSCSender(Protocol):
    """Protocol for sending OSC messages to scsynth."""
    def send_message(self, address: str, args: list) -> None: ...


@dataclass(frozen=True)
class ADSR:
    """Attack-Decay-Sustain-Release envelope."""
    attack: float   # seconds
    decay: float    # seconds
    sustain: float  # 0.0-1.0 (sustain level, not time)
    release: float  # seconds

    @property
    def is_percussive(self) -> bool:
        """True if sustain is 0 — note auto-releases after decay."""
        return self.sustain < 0.01

    @property
    def total_duration(self) -> float:
        """Minimum duration before release begins (attack + decay)."""
        return self.attack + self.decay


# === PRESETS ===

PAD = ADSR(attack=3.0, decay=0.5, sustain=0.8, release=4.0)
SWELL = ADSR(attack=2.0, decay=0.3, sustain=0.9, release=2.0)
STAB = ADSR(attack=0.01, decay=0.1, sustain=0.0, release=0.3)
RHYTHMIC = ADSR(attack=0.01, decay=0.05, sustain=0.0, release=0.15)
BREATH = ADSR(attack=1.5, decay=0.3, sustain=0.6, release=3.0)
SHIMMER = ADSR(attack=0.5, decay=0.2, sustain=0.7, release=1.5)

PRESETS: dict[str, ADSR] = {
    "pad": PAD,
    "swell": SWELL,
    "stab": STAB,
    "rhythmic": RHYTHMIC,
    "breath": BREATH,
    "shimmer": SHIMMER,
}


# === TIMBRES ===
# Which synth to use for each texture type

TIMBRE_MAP: dict[str, str] = {
    "pad": "sw_pad",
    "swell": "sw_choir",
    "stab": "sw_pluck",
    "rhythmic": "sw_pluck",
    "breath": "sw_breath",
    "shimmer": "sw_kotekan",
    "warm": "sw_bowed",
    "bell": "sw_bell_warm",
    "gong": "sw_gong",
}


@dataclass
class ActiveNote:
    """A currently sounding note."""
    node_id: int
    freq: float
    synth: str
    adsr: ADSR
    started_at: float
    amp: float


@dataclass
class SenseweaveVoice:
    """ADSR-controlled senseweave texture instrument.

    The composer triggers notes with specific pitches (always in key).
    The senseweave controls timbre and envelope shape.
    """
    osc: OSCSender | None = None
    timbre: str = "pad"
    adsr: ADSR = field(default_factory=lambda: PAD)
    _active_notes: list[ActiveNote] = field(default_factory=list)
    _next_nid: int = 70000
    max_polyphony: int = 8

    def _nid(self) -> int:
        self._next_nid = (self._next_nid + 1) % 65000 + 70000
        return self._next_nid

    def set_preset(self, name: str) -> None:
        """Set ADSR and timbre from a named preset."""
        if name in PRESETS:
            self.adsr = PRESETS[name]
        if name in TIMBRE_MAP:
            self.timbre = name

    def set_adsr(self, attack: float, decay: float, sustain: float, release: float) -> None:
        """Set custom ADSR envelope."""
        self.adsr = ADSR(
            attack=max(0.001, attack),
            decay=max(0.001, decay),
            sustain=max(0.0, min(1.0, sustain)),
            release=max(0.001, release),
        )

    def set_timbre(self, timbre: str) -> None:
        """Set which synth to use."""
        if timbre in TIMBRE_MAP:
            self.timbre = timbre

    def note_on(self, freq: float, amp: float = 0.06, adsr: ADSR | None = None) -> int:
        """Start a note. Returns node ID for later note_off.

        The freq must be in key — the composer is responsible for this.
        """
        envelope = adsr or self.adsr
        synth = TIMBRE_MAP.get(self.timbre, "sw_pad")
        nid = self._nid()

        # For percussive envelopes (sustain=0), use attack+decay+release as total
        if envelope.is_percussive:
            release = envelope.attack + envelope.decay + envelope.release
        else:
            release = envelope.attack + envelope.decay + envelope.release

        # Scale amplitude by sustain level
        effective_amp = amp * max(envelope.sustain, 0.3)

        if self.osc:
            self.osc.send_message("/s_new", [
                synth, nid, 0, 0,
                "freq", freq,
                "amp", effective_amp,
                "attack", envelope.attack,
                "release", release,
            ])

        note = ActiveNote(
            node_id=nid,
            freq=freq,
            synth=synth,
            adsr=envelope,
            started_at=time.time(),
            amp=effective_amp,
        )
        self._active_notes.append(note)

        # Enforce polyphony limit — release oldest
        while len(self._active_notes) > self.max_polyphony:
            old = self._active_notes.pop(0)
            self._release_note(old)

        return nid

    def note_off(self, node_id: int | None = None) -> None:
        """Release a specific note, or all notes if no ID given."""
        if node_id is None:
            for note in self._active_notes:
                self._release_note(note)
            self._active_notes.clear()
        else:
            self._active_notes = [
                n for n in self._active_notes
                if n.node_id != node_id or not self._release_note(n)
            ]

    def _release_note(self, note: ActiveNote) -> bool:
        """Remove from tracking only. Don't send ANY OSC.

        The synth will be freed naturally when scsynth's envelope
        doneAction triggers, or it will be overwritten by the
        polyphony limit (oldest notes get replaced by new ones).
        """
        # No /n_free, no /n_set — zero OSC messages = zero pops
        return True

    def chord(self, freqs: list[float], amp: float = 0.06, adsr: ADSR | None = None) -> list[int]:
        """Play a chord — multiple notes simultaneously."""
        return [self.note_on(f, amp, adsr) for f in freqs]

    def release_all(self) -> None:
        """Release all active notes."""
        self.note_off()

    @property
    def active_count(self) -> int:
        return len(self._active_notes)

    @property
    def is_playing(self) -> bool:
        return len(self._active_notes) > 0

    # === CONVENIENCE: chord-in-key helpers ===

    def pad_chord(self, root: float, fifth: float, amp: float = 0.05) -> list[int]:
        """Play a sustained pad chord (root + fifth)."""
        return self.chord([root, fifth], amp, PAD)

    def stab_chord(self, root: float, third: float, fifth: float, amp: float = 0.10) -> list[int]:
        """Sharp chord stab (root + third + fifth)."""
        return self.chord([root, third, fifth], amp, STAB)

    def rhythmic_hit(self, freq: float, amp: float = 0.08) -> int:
        """Single percussive texture hit."""
        return self.note_on(freq, amp, RHYTHMIC)

    def breath_tone(self, freq: float, amp: float = 0.04) -> int:
        """Wind-like sustained color."""
        return self.note_on(freq, amp, BREATH)

    def shimmer_note(self, freq: float, amp: float = 0.03) -> int:
        """Bright sustained sparkle."""
        return self.note_on(freq, amp, SHIMMER)

    def swell(self, freq: float, amp: float = 0.06) -> int:
        """Rising swell that sustains."""
        return self.note_on(freq, amp, SWELL)
