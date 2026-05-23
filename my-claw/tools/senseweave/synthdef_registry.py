"""Verified sound palette and SynthDef registry.

Single authoritative source for every voice's synthesis method, timbral tags,
safe role mappings, register range, macro controls, spectral expectations,
and quarantine status.  Covers subtractive, additive, FM, wavetable,
physical-model, and granular methods.

Quarantined voices must never reach the live audio graph without being
resolved to their safe substitute first.

Diagnostic surface (depth-2): :class:`VoiceShape`,
:class:`SynthDefRegistryReport`, and the band/build/summary helpers expose a
JSON-safe view of the in-memory registry for operator and test consumers
without changing any existing lookup or quarantine resolution behavior.
"""
from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RegisterRange:
    """Usable pitch range for a voice (Hz)."""

    min_hz: float
    max_hz: float

    @property
    def octave_span(self) -> float:
        if self.min_hz <= 0:
            return 0.0
        return math.log2(self.max_hz / self.min_hz)


@dataclass(frozen=True)
class MacroControl:
    """A single user-facing control axis on a SynthDef."""

    name: str
    default: float
    min_val: float = 0.0
    max_val: float = 1.0


@dataclass(frozen=True)
class SpectralProfile:
    """Expected frequency-domain characteristics of a voice."""

    fundamental_weight: float   # 0-1, prominence of the fundamental
    harmonic_rolloff_db: float  # dB per octave, negative = steeper
    noise_floor: float          # 0-1, inharmonic / noise content
    bandwidth: str              # "narrow", "medium", "wide"


@dataclass(frozen=True)
class SynthDefEntry:
    """Complete registry record for one voice."""

    voice_name: str
    synthdef_name: str
    synthesis_method: str       # subtractive | additive | fm | wavetable | physical_model | granular
    timbral_tags: tuple[str, ...]
    safe_roles: tuple[str, ...]
    register: RegisterRange
    macro_controls: tuple[MacroControl, ...]
    spectral: SpectralProfile
    quarantined: bool = False
    quarantine_reason: str = ""
    safe_substitute: str = ""   # voice_name of the fallback when quarantined


# ---------------------------------------------------------------------------
# Shared macro controls (all voices expose these via OSC)
# ---------------------------------------------------------------------------

_COMMON_MACROS: tuple[MacroControl, ...] = (
    MacroControl("freq", 440.0, 20.0, 20000.0),
    MacroControl("amp", 0.06, 0.0, 1.0),
    MacroControl("attack", 0.01, 0.001, 10.0),
    MacroControl("release", 1.0, 0.001, 30.0),
)


def _macros(*extras: MacroControl) -> tuple[MacroControl, ...]:
    return _COMMON_MACROS + extras


# ---------------------------------------------------------------------------
# Required synthesis methods — the palette must cover all six
# ---------------------------------------------------------------------------

REQUIRED_METHODS: frozenset[str] = frozenset({
    "subtractive",
    "additive",
    "fm",
    "wavetable",
    "physical_model",
    "granular",
})


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

_ENTRIES: tuple[SynthDefEntry, ...] = (
    # -- Subtractive ----------------------------------------------------------
    SynthDefEntry(
        voice_name="pluck",
        synthdef_name="sw_pluck",
        synthesis_method="subtractive",
        timbral_tags=("articulate", "woody", "clear"),
        safe_roles=("melody", "bass", "counter", "figuration"),
        register=RegisterRange(65.4, 1046.5),       # C2–C6
        macro_controls=_macros(
            MacroControl("brightness", 0.72, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.85,
            harmonic_rolloff_db=-6.0,
            noise_floor=0.05,
            bandwidth="narrow",
        ),
    ),
    SynthDefEntry(
        voice_name="breath",
        synthdef_name="sw_breath",
        synthesis_method="subtractive",
        timbral_tags=("airy", "diffuse", "intimate"),
        safe_roles=("color",),
        register=RegisterRange(110.0, 880.0),        # A2–A5
        macro_controls=_macros(
            MacroControl("brightness", 0.28, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.25,
            harmonic_rolloff_db=-2.0,
            noise_floor=0.45,
            bandwidth="wide",
        ),
    ),
    SynthDefEntry(
        voice_name="morph",
        synthdef_name="morph_voice",
        synthesis_method="subtractive",
        timbral_tags=("hybrid", "blend", "morphing"),
        safe_roles=("melody", "color"),
        register=RegisterRange(65.4, 1046.5),        # C2–C6
        macro_controls=_macros(
            MacroControl("morph_x", 0.0, 0.0, 1.0),
            MacroControl("morph_curve", 1.0, 0.0, 1.0),
            MacroControl("pulse_width", 0.5, 0.05, 0.95),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.50,
            harmonic_rolloff_db=-3.0,
            noise_floor=0.05,
            bandwidth="medium",
        ),
    ),

    # -- Additive -------------------------------------------------------------
    SynthDefEntry(
        voice_name="choir",
        synthdef_name="sw_choir",
        synthesis_method="additive",
        timbral_tags=("air", "choral", "soft"),
        safe_roles=("melody", "color", "counter"),
        register=RegisterRange(130.8, 1046.5),       # C3–C6
        macro_controls=_macros(
            MacroControl("brightness", 0.44, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.50,
            harmonic_rolloff_db=-4.0,
            noise_floor=0.12,
            bandwidth="medium",
        ),
    ),

    # -- FM -------------------------------------------------------------------
    SynthDefEntry(
        voice_name="kotekan",
        synthdef_name="sw_kotekan",
        synthesis_method="fm",
        timbral_tags=("spark", "percussive", "bright"),
        safe_roles=("melody", "bass", "counter", "figuration"),
        register=RegisterRange(261.6, 2093.0),       # C4–C7
        macro_controls=_macros(
            MacroControl("mod_index", 0.5, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.40,
            harmonic_rolloff_db=-4.0,
            noise_floor=0.02,
            bandwidth="medium",
        ),
    ),
    SynthDefEntry(
        voice_name="gong",
        synthdef_name="sw_gong",
        synthesis_method="fm",
        timbral_tags=("resonant", "metallic", "deep"),
        safe_roles=("foundation",),
        register=RegisterRange(32.7, 261.6),          # C1–C4
        macro_controls=_macros(
            MacroControl("mod_index", 0.6, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.35,
            harmonic_rolloff_db=-2.0,
            noise_floor=0.20,
            bandwidth="wide",
        ),
        quarantined=True,
        quarantine_reason="node leak: doneAction:2 unreliable on long resonant tails",
        safe_substitute="bowed",
    ),
    SynthDefEntry(
        voice_name="bell",
        synthdef_name="sw_bell_warm",
        synthesis_method="fm",
        timbral_tags=("glass", "ringing", "bright"),
        safe_roles=("melody",),
        register=RegisterRange(261.6, 4186.0),        # C4–C8
        macro_controls=_macros(
            MacroControl("mod_index", 0.55, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.55,
            harmonic_rolloff_db=-3.0,
            noise_floor=0.04,
            bandwidth="medium",
        ),
        quarantined=True,
        quarantine_reason="node leak: doneAction:2 unreliable on long resonant tails",
        safe_substitute="bowed",
    ),

    # -- Wavetable / waveshaping ----------------------------------------------
    SynthDefEntry(
        voice_name="pad",
        synthdef_name="sw_pad",
        synthesis_method="wavetable",
        timbral_tags=("lush", "stable", "wide"),
        safe_roles=("color",),
        register=RegisterRange(65.4, 523.3),          # C2–C5
        macro_controls=_macros(
            MacroControl("brightness", 0.41, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.80,
            harmonic_rolloff_db=-5.0,
            noise_floor=0.03,
            bandwidth="narrow",
        ),
    ),
    SynthDefEntry(
        voice_name="metal",
        synthdef_name="sw_metal",
        synthesis_method="wavetable",
        timbral_tags=("hard", "shimmer", "sharp"),
        safe_roles=("counter",),
        register=RegisterRange(130.8, 2093.0),        # C3–C7
        macro_controls=_macros(
            MacroControl("brightness", 0.76, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.30,
            harmonic_rolloff_db=-1.5,
            noise_floor=0.08,
            bandwidth="wide",
        ),
        quarantined=True,
        quarantine_reason="no deployed SynthDef",
        safe_substitute="choir",
    ),

    # -- Physical model -------------------------------------------------------
    SynthDefEntry(
        voice_name="bowed",
        synthdef_name="sw_bowed",
        synthesis_method="physical_model",
        timbral_tags=("warm", "sustained", "resonant"),
        safe_roles=("melody", "bass", "counter", "foundation"),
        register=RegisterRange(65.4, 880.0),          # C2–A5
        macro_controls=_macros(
            MacroControl("brightness", 0.34, 0.0, 1.0),
            MacroControl("pressure", 0.5, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.70,
            harmonic_rolloff_db=-3.0,
            noise_floor=0.15,
            bandwidth="medium",
        ),
    ),
    SynthDefEntry(
        voice_name="tabla_tin",
        synthdef_name="sw_tabla_tin",
        synthesis_method="physical_model",
        timbral_tags=("pulse", "skin", "tight"),
        safe_roles=("bass", "rhythm"),
        register=RegisterRange(130.8, 880.0),         # C3–A5
        macro_controls=_macros(
            MacroControl("damping", 0.4, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.65,
            harmonic_rolloff_db=-8.0,
            noise_floor=0.18,
            bandwidth="narrow",
        ),
    ),
    SynthDefEntry(
        voice_name="tabla_ge",
        synthdef_name="sw_tabla_ge",
        synthesis_method="physical_model",
        timbral_tags=("body", "earth", "thump"),
        safe_roles=("bass", "rhythm"),
        register=RegisterRange(55.0, 440.0),          # A1–A4
        macro_controls=_macros(
            MacroControl("damping", 0.5, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.75,
            harmonic_rolloff_db=-10.0,
            noise_floor=0.20,
            bandwidth="narrow",
        ),
        quarantined=True,
        quarantine_reason="no deployed SynthDef",
        safe_substitute="tabla_tin",
    ),

    # -- Granular -------------------------------------------------------------
    SynthDefEntry(
        voice_name="grain",
        synthdef_name="sw_grain",
        synthesis_method="granular",
        timbral_tags=("cloud", "spray", "textural"),
        safe_roles=("color",),
        register=RegisterRange(65.4, 1046.5),         # C2–C6
        macro_controls=_macros(
            MacroControl("grain_size", 0.05, 0.001, 0.5),
            MacroControl("density", 0.5, 0.0, 1.0),
        ),
        spectral=SpectralProfile(
            fundamental_weight=0.30,
            harmonic_rolloff_db=-3.0,
            noise_floor=0.50,
            bandwidth="wide",
        ),
        quarantined=True,
        quarantine_reason="no deployed SynthDef",
        safe_substitute="breath",
    ),
)


# ---------------------------------------------------------------------------
# Indexed lookups
# ---------------------------------------------------------------------------

SYNTHDEF_REGISTRY: dict[str, SynthDefEntry] = {e.voice_name: e for e in _ENTRIES}


def get_entry(voice_name: str) -> SynthDefEntry:
    """Look up a registry entry by voice name.  Raises KeyError if unknown."""
    return SYNTHDEF_REGISTRY[voice_name]


def resolve_voice(voice_name: str) -> SynthDefEntry:
    """Return the live-safe entry for *voice_name*.

    If the voice is quarantined the entry for its safe substitute is returned
    instead, guaranteeing the caller never receives a quarantined voice.
    """
    entry = SYNTHDEF_REGISTRY[voice_name]
    if entry.quarantined:
        return SYNTHDEF_REGISTRY[entry.safe_substitute]
    return entry


def entries_by_method(method: str) -> tuple[SynthDefEntry, ...]:
    """All entries using a given synthesis method (including quarantined)."""
    return tuple(e for e in _ENTRIES if e.synthesis_method == method)


def live_voices() -> tuple[SynthDefEntry, ...]:
    """All non-quarantined entries safe for live playback."""
    return tuple(e for e in _ENTRIES if not e.quarantined)


def quarantined_voices() -> tuple[SynthDefEntry, ...]:
    """All entries currently in quarantine."""
    return tuple(e for e in _ENTRIES if e.quarantined)


def voices_for_role(role: str) -> tuple[SynthDefEntry, ...]:
    """Non-quarantined entries whose safe_roles include *role*."""
    return tuple(
        e for e in _ENTRIES
        if not e.quarantined and role in e.safe_roles
    )


def covered_methods() -> frozenset[str]:
    """Set of synthesis methods represented in the registry."""
    return frozenset(e.synthesis_method for e in _ENTRIES)


# ---------------------------------------------------------------------------
# Depth-2 diagnostic surface
# ---------------------------------------------------------------------------

# Canonical method ordering used by the report. Mirrors REQUIRED_METHODS
# but as a stable tuple for deterministic JSON output.
_CANONICAL_METHODS: tuple[str, ...] = (
    "subtractive",
    "additive",
    "fm",
    "wavetable",
    "physical_model",
    "granular",
)

_REGISTER_BAND_KEYS: tuple[str, ...] = ("low", "mid", "high")


def register_band(min_hz: float) -> str:
    """Map a register minimum frequency (Hz) to a stable named band."""
    if min_hz < 130.8:
        return "low"
    if min_hz < 523.3:
        return "mid"
    return "high"


def fundamental_band(weight: float) -> str:
    """Map a spectral fundamental weight to a stable named band."""
    if weight < 0.4:
        return "weak"
    if weight <= 0.7:
        return "balanced"
    return "strong"


def noise_band(noise_floor: float) -> str:
    """Map a spectral noise floor to a stable named band."""
    if noise_floor < 0.1:
        return "clean"
    if noise_floor <= 0.3:
        return "textured"
    return "noisy"


def rolloff_band(harmonic_rolloff_db: float) -> str:
    """Map a harmonic rolloff (dB/octave, negative) to a stable named band."""
    if harmonic_rolloff_db > -3.0:
        return "gentle"
    if harmonic_rolloff_db >= -6.0:
        return "moderate"
    return "steep"


@dataclass(frozen=True)
class VoiceShape:
    """Resolved diagnostic view of a single :class:`SynthDefEntry`."""

    voice_name: str
    synthdef_name: str
    synthesis_method: str
    timbral_tags: tuple[str, ...]
    safe_roles: tuple[str, ...]
    register_min_hz: float
    register_max_hz: float
    octave_span: float
    register_band: str
    bandwidth: str
    fundamental_weight: float
    fundamental_band: str
    noise_floor: float
    noise_band: str
    harmonic_rolloff_db: float
    rolloff_band: str
    macro_control_count: int
    macro_control_names: tuple[str, ...]
    quarantined: bool
    quarantine_reason: str
    safe_substitute: str
    runtime_voice_name: str


@dataclass(frozen=True)
class SynthDefRegistryReport:
    """Aggregate diagnostic view of the entire SynthDef registry."""

    total_count: int
    live_count: int
    quarantined_count: int
    methods: tuple[str, ...]
    method_counts: dict[str, int]
    live_method_counts: dict[str, int]
    roles: tuple[str, ...]
    role_live_voices: dict[str, tuple[str, ...]]
    register_band_counts: dict[str, int]
    lowest_register_voice: str
    highest_register_voice: str
    quarantine_reasons: tuple[str, ...]
    runtime_voice_map: dict[str, str]
    missing_required_methods: tuple[str, ...]
    voices: tuple[VoiceShape, ...]


def build_voice_shape(entry: SynthDefEntry) -> VoiceShape:
    """Resolve one registry entry into a typed :class:`VoiceShape`."""
    if entry.quarantined:
        runtime_voice_name = resolve_voice(entry.voice_name).voice_name
    else:
        runtime_voice_name = entry.voice_name
    macro_names: list[str] = []
    for control in entry.macro_controls:
        macro_names.append(control.name)
    return VoiceShape(
        voice_name=entry.voice_name,
        synthdef_name=entry.synthdef_name,
        synthesis_method=entry.synthesis_method,
        timbral_tags=entry.timbral_tags,
        safe_roles=entry.safe_roles,
        register_min_hz=entry.register.min_hz,
        register_max_hz=entry.register.max_hz,
        octave_span=round(entry.register.octave_span, 4),
        register_band=register_band(entry.register.min_hz),
        bandwidth=entry.spectral.bandwidth,
        fundamental_weight=entry.spectral.fundamental_weight,
        fundamental_band=fundamental_band(entry.spectral.fundamental_weight),
        noise_floor=entry.spectral.noise_floor,
        noise_band=noise_band(entry.spectral.noise_floor),
        harmonic_rolloff_db=entry.spectral.harmonic_rolloff_db,
        rolloff_band=rolloff_band(entry.spectral.harmonic_rolloff_db),
        macro_control_count=len(entry.macro_controls),
        macro_control_names=tuple(macro_names),
        quarantined=entry.quarantined,
        quarantine_reason=entry.quarantine_reason,
        safe_substitute=entry.safe_substitute,
        runtime_voice_name=runtime_voice_name,
    )


def build_synthdef_registry_report() -> SynthDefRegistryReport:
    """Build the registry-wide :class:`SynthDefRegistryReport`."""
    voices = tuple(build_voice_shape(entry) for entry in _ENTRIES)

    method_counts: dict[str, int] = {method: 0 for method in _CANONICAL_METHODS}
    live_method_counts: dict[str, int] = {method: 0 for method in _CANONICAL_METHODS}
    register_band_counts: dict[str, int] = {band: 0 for band in _REGISTER_BAND_KEYS}

    for entry in _ENTRIES:
        if entry.synthesis_method in method_counts:
            method_counts[entry.synthesis_method] += 1
            if not entry.quarantined:
                live_method_counts[entry.synthesis_method] += 1
        register_band_counts[register_band(entry.register.min_hz)] += 1

    role_order: list[str] = []
    role_live_voices: dict[str, list[str]] = {}
    for entry in _ENTRIES:
        if entry.quarantined:
            continue
        for role in entry.safe_roles:
            if role not in role_live_voices:
                role_live_voices[role] = []
                role_order.append(role)
            role_live_voices[role].append(entry.voice_name)

    quarantine_reasons: list[str] = []
    runtime_voice_map: dict[str, str] = {}
    for entry in _ENTRIES:
        if not entry.quarantined:
            continue
        if entry.quarantine_reason and entry.quarantine_reason not in quarantine_reasons:
            quarantine_reasons.append(entry.quarantine_reason)
        runtime_voice_map[entry.voice_name] = resolve_voice(entry.voice_name).voice_name

    lowest_voice = _ENTRIES[0].voice_name
    highest_voice = _ENTRIES[0].voice_name
    lowest_min = _ENTRIES[0].register.min_hz
    highest_max = _ENTRIES[0].register.max_hz
    for entry in _ENTRIES[1:]:
        if entry.register.min_hz < lowest_min:
            lowest_min = entry.register.min_hz
            lowest_voice = entry.voice_name
        if entry.register.max_hz > highest_max:
            highest_max = entry.register.max_hz
            highest_voice = entry.voice_name

    missing_methods = tuple(
        sorted(method for method, count in method_counts.items() if count == 0)
    )

    live_total = sum(1 for entry in _ENTRIES if not entry.quarantined)
    quarantined_total = sum(1 for entry in _ENTRIES if entry.quarantined)

    return SynthDefRegistryReport(
        total_count=len(_ENTRIES),
        live_count=live_total,
        quarantined_count=quarantined_total,
        methods=_CANONICAL_METHODS,
        method_counts=method_counts,
        live_method_counts=live_method_counts,
        roles=tuple(role_order),
        role_live_voices={role: tuple(names) for role, names in role_live_voices.items()},
        register_band_counts=register_band_counts,
        lowest_register_voice=lowest_voice,
        highest_register_voice=highest_voice,
        quarantine_reasons=tuple(quarantine_reasons),
        runtime_voice_map=runtime_voice_map,
        missing_required_methods=missing_methods,
        voices=voices,
    )


def summarize_synthdef_registry_report(
    report: SynthDefRegistryReport,
) -> dict[str, object]:
    """Render a :class:`SynthDefRegistryReport` as a JSON-safe summary."""
    voices_payload: list[dict[str, object]] = []
    for shape in report.voices:
        voices_payload.append(
            {
                "voice_name": shape.voice_name,
                "synthdef_name": shape.synthdef_name,
                "synthesis_method": shape.synthesis_method,
                "timbral_tags": list(shape.timbral_tags),
                "safe_roles": list(shape.safe_roles),
                "register_min_hz": shape.register_min_hz,
                "register_max_hz": shape.register_max_hz,
                "octave_span": shape.octave_span,
                "register_band": shape.register_band,
                "bandwidth": shape.bandwidth,
                "fundamental_weight": shape.fundamental_weight,
                "fundamental_band": shape.fundamental_band,
                "noise_floor": shape.noise_floor,
                "noise_band": shape.noise_band,
                "harmonic_rolloff_db": shape.harmonic_rolloff_db,
                "rolloff_band": shape.rolloff_band,
                "macro_control_count": shape.macro_control_count,
                "macro_control_names": list(shape.macro_control_names),
                "quarantined": shape.quarantined,
                "quarantine_reason": shape.quarantine_reason,
                "safe_substitute": shape.safe_substitute,
                "runtime_voice_name": shape.runtime_voice_name,
            }
        )
    return {
        "total_count": report.total_count,
        "live_count": report.live_count,
        "quarantined_count": report.quarantined_count,
        "methods": list(report.methods),
        "method_counts": dict(report.method_counts),
        "live_method_counts": dict(report.live_method_counts),
        "roles": list(report.roles),
        "role_live_voices": {
            role: list(names) for role, names in report.role_live_voices.items()
        },
        "register_band_counts": dict(report.register_band_counts),
        "lowest_register_voice": report.lowest_register_voice,
        "highest_register_voice": report.highest_register_voice,
        "quarantine_reasons": list(report.quarantine_reasons),
        "runtime_voice_map": dict(report.runtime_voice_map),
        "missing_required_methods": list(report.missing_required_methods),
        "voices": voices_payload,
    }
