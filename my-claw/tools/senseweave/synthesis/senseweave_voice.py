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

Diagnostic surface (depth-2): VoiceADSRSnapshot, VoiceNoteSnapshot,
and VoicePlanReport turn one voice state snapshot into a stable
operator-readable summary without changing the live OSC path.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


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
    "swell": "sw_choir",    # has doneAction:2
    "stab": "sw_pluck",     # has doneAction:2
    "rhythmic": "sw_pluck", # has doneAction:2
    "breath": "sw_breath",  # has doneAction:2
    "shimmer": "sw_kotekan",# has doneAction:2
    "warm": "sw_bowed",     # has doneAction:2
    "bell": "sw_bell_warm", # has doneAction:2
    "gong": "sw_gong",      # has doneAction:2
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
        """Release the active note and report success to list filtering."""
        if self.osc:
            self.osc.send_message("/n_free", [note.node_id])
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


# === DIAGNOSTIC / REPORT SURFACE (depth-2) ===

_VOICE_REGISTER_BANDS: tuple[str, ...] = ("pedal", "bass", "middle", "upper")
_VOICE_AMP_BANDS: tuple[str, ...] = ("silent", "quiet", "medium", "loud")


@dataclass(frozen=True)
class VoiceADSRSnapshot:
    """Resolved view of one ADSR envelope, including derived band labels."""
    preset_name: str | None
    attack: float
    decay: float
    sustain: float
    release: float
    total_duration: float
    is_percussive: bool
    envelope_band: str


@dataclass(frozen=True)
class VoiceNoteSnapshot:
    """Resolved view of one currently sounding note."""
    node_id: int
    freq: float
    synth: str
    amp: float
    register_band: str
    amp_band: str
    envelope: VoiceADSRSnapshot
    elapsed_seconds: float


@dataclass(frozen=True)
class VoicePlanReport:
    """End-to-end snapshot of one SenseweaveVoice instrument."""
    timbre: str
    synth: str
    preset_name: str | None
    envelope: VoiceADSRSnapshot
    max_polyphony: int
    active_count: int
    polyphony_band: str
    is_playing: bool
    notes: tuple[VoiceNoteSnapshot, ...]
    mean_amp: float
    total_amp: float
    lowest_frequency_hz: float
    highest_frequency_hz: float
    register_band_counts: dict[str, int]
    amp_band_counts: dict[str, int]
    synth_counts: dict[str, int]


def voice_envelope_band(adsr: ADSR) -> str:
    """Classify an ADSR envelope by its attack/sustain shape."""
    if adsr.is_percussive:
        return "percussive"
    if adsr.attack >= 2.0:
        return "long_attack"
    if adsr.attack >= 1.0:
        return "medium_attack"
    return "short_attack"


def voice_amp_band(amp: float) -> str:
    """Classify an amplitude into silent/quiet/medium/loud."""
    if amp <= 0.0:
        return "silent"
    if amp <= 0.05:
        return "quiet"
    if amp <= 0.1:
        return "medium"
    return "loud"


def voice_register_band(frequency_hz: float) -> str:
    """Classify a frequency into pedal, bass, middle, or upper register."""
    if frequency_hz < 65.4:
        return "pedal"
    if frequency_hz < 130.8:
        return "bass"
    if frequency_hz < 523.3:
        return "middle"
    return "upper"


def voice_polyphony_band(active_count: int, max_polyphony: int) -> str:
    """Classify polyphony pressure as idle/sparse/filling/full."""
    if active_count <= 0:
        return "idle"
    if max_polyphony <= 0:
        return "full"
    ratio = active_count / max_polyphony
    if ratio < 0.5:
        return "sparse"
    if ratio < 1.0:
        return "filling"
    return "full"


def preset_name_for_adsr(adsr: ADSR) -> str | None:
    """Return the canonical preset name matching an ADSR, or None."""
    for name, preset in PRESETS.items():
        if preset == adsr:
            return name
    return None


def preset_envelope_band(name: str) -> str:
    """Return the envelope band for a named preset, or 'unknown'."""
    preset = PRESETS.get(name)
    if preset is None:
        return "unknown"
    return voice_envelope_band(preset)


def voice_synth_for_timbre(timbre: str) -> str:
    """Return the synth configured for a timbre, falling back to pad."""
    if timbre in TIMBRE_MAP:
        return TIMBRE_MAP[timbre]
    return TIMBRE_MAP["pad"]


def summarize_active_notes(notes: list[ActiveNote]) -> dict[str, Any]:
    """Aggregate active notes into stable numeric and categorical metrics."""
    register_counts = {band: 0 for band in _VOICE_REGISTER_BANDS}
    amp_counts = {band: 0 for band in _VOICE_AMP_BANDS}
    synth_counts: dict[str, int] = {}
    total_amp = 0.0
    min_freq = 0.0
    max_freq = 0.0
    count = 0

    for note in notes:
        register_counts[voice_register_band(note.freq)] += 1
        amp_counts[voice_amp_band(note.amp)] += 1
        synth_counts[note.synth] = synth_counts.get(note.synth, 0) + 1
        total_amp += note.amp
        min_freq = note.freq if count == 0 else min(min_freq, note.freq)
        max_freq = note.freq if count == 0 else max(max_freq, note.freq)
        count += 1

    mean_amp = total_amp / count if count else 0.0
    return {
        "count": count,
        "total_amp": round(total_amp, 4),
        "mean_amp": round(mean_amp, 4),
        "lowest_frequency_hz": round(min_freq, 4),
        "highest_frequency_hz": round(max_freq, 4),
        "register_band_counts": register_counts,
        "amp_band_counts": amp_counts,
        "synth_counts": synth_counts,
    }


def voice_polyphony_pressure(active_count: int, max_polyphony: int) -> float:
    """Return active/max as a clamped saturation ratio in [0.0, 1.0]."""
    if max_polyphony <= 0:
        return 1.0
    if active_count <= 0:
        return 0.0
    ratio = active_count / max_polyphony
    if ratio > 1.0:
        return 1.0
    return round(ratio, 4)


def is_voice_idle(voice: SenseweaveVoice) -> bool:
    """Return True when the voice has no sounding notes."""
    if voice.is_playing:
        return False
    if voice.active_count > 0:
        return False
    return True


def build_voice_adsr_snapshot(adsr: ADSR) -> VoiceADSRSnapshot:
    """Resolve an ADSR envelope into a frozen diagnostic snapshot."""
    preset_name = preset_name_for_adsr(adsr)
    if preset_name is None:
        envelope_band = voice_envelope_band(adsr)
    else:
        envelope_band = preset_envelope_band(preset_name)
    return VoiceADSRSnapshot(
        preset_name=preset_name,
        attack=adsr.attack,
        decay=adsr.decay,
        sustain=adsr.sustain,
        release=adsr.release,
        total_duration=adsr.total_duration,
        is_percussive=adsr.is_percussive,
        envelope_band=envelope_band,
    )


def build_voice_note_snapshot(note: ActiveNote, now: float) -> VoiceNoteSnapshot:
    """Resolve an active note into a frozen diagnostic snapshot."""
    elapsed = now - note.started_at
    if elapsed < 0.0:
        elapsed = 0.0
    return VoiceNoteSnapshot(
        node_id=note.node_id,
        freq=note.freq,
        synth=note.synth,
        amp=note.amp,
        register_band=voice_register_band(note.freq),
        amp_band=voice_amp_band(note.amp),
        envelope=build_voice_adsr_snapshot(note.adsr),
        elapsed_seconds=round(elapsed, 4),
    )


def build_voice_plan_report(
    voice: SenseweaveVoice,
    *,
    now: float | None = None,
) -> VoicePlanReport:
    """Build one end-to-end snapshot of a live SenseweaveVoice."""
    clock = time.time() if now is None else now
    envelope = build_voice_adsr_snapshot(voice.adsr)
    note_snapshots = tuple(
        build_voice_note_snapshot(n, clock) for n in voice._active_notes
    )
    summary = summarize_active_notes(voice._active_notes)
    return VoicePlanReport(
        timbre=voice.timbre,
        synth=voice_synth_for_timbre(voice.timbre),
        preset_name=envelope.preset_name,
        envelope=envelope,
        max_polyphony=voice.max_polyphony,
        active_count=voice.active_count,
        polyphony_band=voice_polyphony_band(
            voice.active_count, voice.max_polyphony
        ),
        is_playing=voice.is_playing,
        notes=note_snapshots,
        mean_amp=float(summary["mean_amp"]),
        total_amp=float(summary["total_amp"]),
        lowest_frequency_hz=float(summary["lowest_frequency_hz"]),
        highest_frequency_hz=float(summary["highest_frequency_hz"]),
        register_band_counts=dict(summary["register_band_counts"]),
        amp_band_counts=dict(summary["amp_band_counts"]),
        synth_counts=dict(summary["synth_counts"]),
    )


def _adsr_snapshot_dict(snapshot: VoiceADSRSnapshot) -> dict[str, Any]:
    """Render a VoiceADSRSnapshot as a JSON-safe dict."""
    return {
        "preset_name": snapshot.preset_name,
        "attack": snapshot.attack,
        "decay": snapshot.decay,
        "sustain": snapshot.sustain,
        "release": snapshot.release,
        "total_duration": snapshot.total_duration,
        "is_percussive": snapshot.is_percussive,
        "envelope_band": snapshot.envelope_band,
    }


def _note_snapshot_dict(snapshot: VoiceNoteSnapshot) -> dict[str, Any]:
    """Render a VoiceNoteSnapshot as a JSON-safe dict."""
    return {
        "node_id": snapshot.node_id,
        "freq": snapshot.freq,
        "synth": snapshot.synth,
        "amp": snapshot.amp,
        "register_band": snapshot.register_band,
        "amp_band": snapshot.amp_band,
        "envelope": _adsr_snapshot_dict(snapshot.envelope),
        "elapsed_seconds": snapshot.elapsed_seconds,
    }


def dominant_register_band(report: VoicePlanReport) -> str | None:
    """Return the register band with the most active notes, or None."""
    if not report.notes:
        return None
    best_band: str | None = None
    best_count = 0
    for band in _VOICE_REGISTER_BANDS:
        count = report.register_band_counts.get(band, 0)
        if count > best_count:
            best_count = count
            best_band = band
    return best_band


def dominant_amp_band(report: VoicePlanReport) -> str | None:
    """Return the amp band with the most active notes, or None."""
    if not report.notes:
        return None
    best_band: str | None = None
    best_count = 0
    for band in _VOICE_AMP_BANDS:
        count = report.amp_band_counts.get(band, 0)
        if count > best_count:
            best_count = count
            best_band = band
    return best_band


def dominant_synth(report: VoicePlanReport) -> str | None:
    """Return the synth with the most active notes, or None."""
    if not report.synth_counts:
        return None
    best_synth: str | None = None
    best_count = 0
    for synth, count in report.synth_counts.items():
        if count > best_count:
            best_count = count
            best_synth = synth
    return best_synth


def summarize_voice_plan_report(report: VoicePlanReport) -> dict[str, Any]:
    """Return a JSON-safe operator summary for a voice plan report."""
    notes_list: list[dict[str, Any]] = []
    for note in report.notes:
        notes_list.append(_note_snapshot_dict(note))
    return {
        "timbre": report.timbre,
        "synth": report.synth,
        "preset_name": report.preset_name,
        "envelope": _adsr_snapshot_dict(report.envelope),
        "max_polyphony": report.max_polyphony,
        "active_count": report.active_count,
        "polyphony_band": report.polyphony_band,
        "is_playing": report.is_playing,
        "notes": notes_list,
        "mean_amp": report.mean_amp,
        "total_amp": report.total_amp,
        "lowest_frequency_hz": report.lowest_frequency_hz,
        "highest_frequency_hz": report.highest_frequency_hz,
        "register_band_counts": dict(report.register_band_counts),
        "amp_band_counts": dict(report.amp_band_counts),
        "synth_counts": dict(report.synth_counts),
    }
