"""Catalog for the CypherClaw EMSD curriculum."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ExerciseSpec:
    """Machine-verifiable exercise specification."""

    id: str
    title: str
    objective: str
    template: dict[str, object]
    verifier: str  # "structural", "constraint", "spectral", "temporal"
    expected_features: tuple[str, ...]

    @property
    def expected(self) -> tuple[str, ...]:
        """Backward-compatible alias for older exercise consumers."""
        return self.expected_features


@dataclass(frozen=True)
class Course:
    code: str
    title: str
    credits: int
    semester: int
    category: str
    prerequisites: tuple[str, ...] = ()
    live_modules: tuple[str, ...] = ()
    description: str = ""
    learning_objectives: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    exercises: tuple[ExerciseSpec, ...] = ()

    def course_dir(self, root: str | Path) -> Path:
        return Path(root) / self.code


def _ex(
    id: str,
    title: str,
    objective: str,
    verifier: str,
    expected_features: tuple[str, ...],
    template: dict[str, object] | None = None,
) -> ExerciseSpec:
    submission_template = (
        dict(template)
        if template is not None
        else {feature: True for feature in expected_features}
    )
    return ExerciseSpec(
        id=id, title=title, objective=objective,
        template=submission_template, verifier=verifier,
        expected_features=expected_features,
    )


def _course(
    code: str,
    title: str,
    credits: int,
    semester: int,
    category: str,
    prerequisites: tuple[str, ...] = (),
    live_modules: tuple[str, ...] = (),
    description: str = "",
    learning_objectives: tuple[str, ...] = (),
    topics: tuple[str, ...] = (),
    exercises: tuple[ExerciseSpec, ...] = (),
) -> Course:
    return Course(
        code=code,
        title=title,
        credits=credits,
        semester=semester,
        category=category,
        prerequisites=prerequisites,
        live_modules=live_modules,
        description=description,
        learning_objectives=learning_objectives,
        topics=topics,
        exercises=exercises,
    )


# ---------------------------------------------------------------------------
# Core Concentrate (10 courses)
# ---------------------------------------------------------------------------

_EMSD_101 = _course(
    "EMSD-101", "Foundations of Digital Audio", 3, 1, "core_concentrate",
    (), ("tools/scsynth", "tools/senseweave"),
    description=(
        "Core theory of digital audio: sampling, quantization, MIDI, and "
        "signal representation as the foundation for all CypherClaw synthesis."
    ),
    learning_objectives=(
        "Convert between MIDI note numbers and frequencies using A440 reference",
        "Calculate Nyquist limits for given sample rates",
        "Describe PCM encoding with bit depth and sample rate trade-offs",
        "Identify buffer size impact on audio latency",
    ),
    topics=(
        "PCM encoding and quantization",
        "Nyquist theorem and aliasing",
        "MIDI note numbers and frequency conversion",
        "Audio latency and buffer sizes",
        "Bit depth and dynamic range",
    ),
    exercises=(
        _ex(
            "ex01", "MIDI-Frequency Converter",
            "Implement bidirectional MIDI/frequency conversion with A440 reference "
            "and verify against known pitch values.",
            "constraint",
            ("midi_to_freq", "freq_to_midi", "nyquist_correct"),
        ),
    ),
)

_EMSD_102 = _course(
    "EMSD-102", "Producing Music with SuperCollider", 3, 1, "core_concentrate",
    ("EMSD-101",), ("tools/senseweave/music_tracker.py", "tools/senseweave/music_tracker_runtime.py"),
    description=(
        "Hands-on SuperCollider production: SynthDefs, patterns, buses, groups, "
        "and the server architecture that CypherClaw uses for live synthesis."
    ),
    learning_objectives=(
        "Construct SynthDefs with standard UGen graphs",
        "Schedule events using SuperCollider patterns",
        "Route audio through buses and groups",
        "Build a complete signal chain from oscillator to output",
    ),
    topics=(
        "SynthDef construction and UGen graphs",
        "Pattern system and event scheduling",
        "Server architecture and resource management",
        "Buses, groups, and signal routing",
        "OSC communication protocol",
    ),
    exercises=(
        _ex(
            "ex01", "Tracker Scene Schema",
            "Define a valid tracker scene structure with required fields "
            "for scheduling and playback.",
            "structural",
            ("scene_id", "bpm", "steps", "voices", "duration_bars"),
        ),
    ),
)

_EMSD_201 = _course(
    "EMSD-201", "Sound Design for the Electronic Musician", 3, 2, "core_concentrate",
    ("EMSD-102",), ("tools/senseweave/sound_palette_lab.py",),
    description=(
        "Patch design across synthesis architectures with emphasis on timbre "
        "shaping, filter usage, and envelope design for expressive electronic sound."
    ),
    learning_objectives=(
        "Design patches using subtractive, FM, and additive synthesis",
        "Shape timbre with filter types and resonance settings",
        "Build multi-stage envelopes for amplitude, filter, and pitch",
        "Compare synthesis architectures for different timbral goals",
    ),
    topics=(
        "Subtractive synthesis and filters",
        "FM synthesis and modulator ratios",
        "Additive synthesis and partial control",
        "Filter types, cutoff, and resonance",
        "Envelope design (ADSR, multi-stage)",
        "Modulation routing",
    ),
    exercises=(
        _ex(
            "ex01", "Synthesis Patch Validator",
            "Define a synthesis patch with parameters constrained to safe "
            "ranges across subtractive, FM, and additive architectures.",
            "constraint",
            ("architecture", "oscillator_freq", "filter_cutoff", "envelope_attack", "output_level"),
        ),
    ),
)

_EMSD_202 = _course(
    "EMSD-202", "Sampling and Audio Production", 3, 2, "core_concentrate",
    ("EMSD-201",), ("tools/senseweave/sample_lab.py",),
    description=(
        "Sample acquisition, manipulation, and integration into compositions: "
        "slicing, layering, pitch-shifting, and metadata management."
    ),
    learning_objectives=(
        "Process audio samples with slicing and loop points",
        "Apply pitch-shifting and time-stretching techniques",
        "Build layered sample instruments from multiple sources",
        "Maintain structured sample metadata catalogs",
    ),
    topics=(
        "Sample slicing and region editing",
        "Time-stretching algorithms",
        "Pitch-shifting and transposition",
        "Loop points and crossfade design",
        "Sample layering and velocity mapping",
        "Audio format metadata standards",
    ),
    exercises=(
        _ex(
            "ex01", "Sample Catalog Builder",
            "Create a sample metadata catalog entry with required fields "
            "for library management and playback.",
            "structural",
            ("sample_id", "source_path", "duration_ms", "sample_rate", "channels", "tags"),
        ),
    ),
)

_EMSD_301 = _course(
    "EMSD-301", "Mixing and Mastering for Electronic Music", 3, 3, "core_concentrate",
    ("EMSD-202",), ("tools/senseweave/mix_engine.py",),
    description=(
        "Frequency allocation, dynamic range management, spatial positioning, "
        "and loudness targeting for installation-quality electronic music mixes."
    ),
    learning_objectives=(
        "Allocate frequency bands across mix roles without masking",
        "Apply compression and limiting for dynamic control",
        "Position elements in stereo field with depth and width",
        "Set loudness targets appropriate for installation playback",
    ),
    topics=(
        "Frequency band allocation and EQ strategy",
        "Compression, limiting, and dynamic control",
        "Stereo imaging and spatial positioning",
        "Loudness standards (LUFS) for installation",
        "Master bus processing chain",
        "Sidechain and deference techniques",
    ),
    exercises=(
        _ex(
            "ex01", "Frequency Band Allocator",
            "Allocate frequency bands to mix roles ensuring no critical "
            "masking overlaps between competing elements.",
            "constraint",
            (
                "bass_range", "low_mid_range", "mid_range", "presence_range",
                "master_chain", "no_masking_overlap",
            ),
        ),
    ),
)

_EMSD_302 = _course(
    "EMSD-302", "Composing Electronic Music 1", 3, 3, "core_concentrate",
    ("EMSD-301", "EMSD-110"),
    ("tools/senseweave/tracker_cadence.py", "tools/senseweave/arrangement_engine.py"),
    description=(
        "Formal structure and motivic development: section planning, harmonic "
        "rhythm, phrase construction, and transition design for electronic composition."
    ),
    learning_objectives=(
        "Construct multi-section forms with clear phrase boundaries",
        "Develop motifs through variation and transformation",
        "Plan harmonic progressions with functional intent",
        "Design transitions between contrasting sections",
    ),
    topics=(
        "Musical form (ABA, rondo, through-composed)",
        "Motivic development and variation",
        "Harmonic rhythm and progression",
        "Phrase structure and boundaries",
        "Section transitions and continuity",
        "Cadence and resolution",
    ),
    exercises=(
        _ex(
            "ex01", "Form Structure Builder",
            "Define a multi-section composition form with valid transitions "
            "and at least three distinct sections.",
            "structural",
            (
                "sections", "section_count", "transitions", "progressions",
                "total_duration", "form_label",
            ),
        ),
        _ex(
            "ex02", "Counterpoint Relation Study",
            "Write a two-voice section plan that names the counterpoint relation "
            "and verifies motion, consonance, and phrase-answer behavior.",
            "constraint",
            (
                "counterpoint_relation", "primary_voice", "response_voice",
                "motion_profile", "consonance_policy",
            ),
        ),
    ),
)

_EMSD_303 = _course(
    "EMSD-303", "Composing Electronic Music 2", 3, 4, "core_concentrate",
    ("EMSD-302",),
    ("tools/senseweave/procedural_arc.py", "tools/senseweave/capstone_engine.py"),
    description=(
        "Multi-phase long-form composition with dramatic arc management: density "
        "contour, tension curves, climax construction, and phase-appropriate choices."
    ),
    learning_objectives=(
        "Design density contours across five dramatic arc phases",
        "Manage tension and release over extended durations",
        "Build and resolve climactic passages with controlled intensity",
        "Coordinate production parameters with arc phase intent",
    ),
    topics=(
        "Dramatic arc phases (Divination through Crystallization)",
        "Density contour design and management",
        "Tension-release curves over long durations",
        "Climax construction and resolution",
        "Phase transitions and continuity",
        "Long-form coherence strategies",
    ),
    exercises=(
        _ex(
            "ex01", "Arc Density Profiler",
            "Design a 5-phase density profile with monotonically increasing "
            "density through Convergence and decreasing into Crystallization.",
            "constraint",
            ("phase_count", "divination_density", "convergence_peak", "crystallization_decay", "contour_valid"),
        ),
    ),
)

_EMSD_304 = _course(
    "EMSD-304", "Procedural Music Programming", 3, 4, "core_concentrate",
    ("EMSD-303",), ("tools/senseweave/procedural_arc.py",),
    description=(
        "Algorithmic and generative composition: constraint systems, stochastic "
        "processes, rule-based composition, and parameter automation."
    ),
    learning_objectives=(
        "Encode musical rules as machine-verifiable constraints",
        "Implement stochastic composition with bounded randomness",
        "Design parameter automation curves for long-form evolution",
        "Build self-modifying rule systems with stable output",
    ),
    topics=(
        "Constraint-based composition systems",
        "Stochastic processes and bounded randomness",
        "Markov chains for melodic/harmonic generation",
        "Rule systems and production grammars",
        "Parameter automation and interpolation",
        "Generative algorithm design",
    ),
    exercises=(
        _ex(
            "ex01", "Constraint Rule Validator",
            "Write a composition constraint rule set with valid schema "
            "covering pitch range, rhythm density, and harmonic bounds.",
            "structural",
            ("rules", "rule_count", "pitch_range", "density_bounds", "schema_valid"),
        ),
    ),
)

_EMSD_401 = _course(
    "EMSD-401", "Creative Digital Signal Processing", 3, 5, "core_concentrate",
    ("EMSD-304", "EMSD-L401"), ("tools/senseweave/dsp_scene_lab.py",),
    description=(
        "Custom DSP chains for novel audio effects: spectral processing, "
        "convolution, waveshaping, feedback networks, and real-time DSP design."
    ),
    learning_objectives=(
        "Design DSP processing chains with proper signal flow",
        "Implement spectral processing with FFT analysis/resynthesis",
        "Apply waveshaping and distortion within safe parameter bounds",
        "Build feedback networks with stability controls",
    ),
    topics=(
        "FFT-based spectral processing",
        "Spectral freeze and resynthesis",
        "Convolution and impulse responses",
        "Waveshaping and transfer functions",
        "Ring modulation and AM/FM effects",
        "Feedback network stability",
    ),
    exercises=(
        _ex(
            "ex01", "DSP Chain Designer",
            "Design a DSP processing chain with valid connectivity between "
            "nodes and all parameters within safe operational bounds.",
            "constraint",
            ("chain_nodes", "connectivity_valid", "param_bounds_safe", "input_node", "output_node"),
        ),
    ),
)

_EMSD_499 = _course(
    "EMSD-499", "Capstone — The Living Composition", 3, 8, "core_concentrate",
    ("EMSD-401", "EMSD-304", "EMSD-303"),
    ("tools/senseweave/capstone_engine.py",),
    description=(
        "The culminating 30-minute living composition integrating all EMSD "
        "coursework into a continuously evolving performance."
    ),
    learning_objectives=(
        "Produce a complete 30-minute arc with all five dramatic phases",
        "Integrate score tree, tracker, and runtime modules into unified output",
        "Apply production-course concepts across harmony, rhythm, synthesis, and mix",
        "Store and recall compositions in repertoire memory",
    ),
    topics=(
        "Full arc production (30-minute form)",
        "Integrated score tree and tracker compilation",
        "Runtime module coordination",
        "Repertoire storage and recall",
        "Artistic identity expression",
        "Cross-course synthesis and integration",
    ),
    exercises=(
        _ex(
            "ex01", "Arc Metadata Completeness",
            "Produce full arc metadata for a 30-minute composition covering "
            "all required production fields across five phases.",
            "structural",
            (
                "arc_id", "phase_profiles", "harmonic_plan", "rhythm_plan",
                "synthesis_palette", "mix_roles", "spatial_profile",
            ),
        ),
    ),
)

# ---------------------------------------------------------------------------
# Musicianship (3 courses)
# ---------------------------------------------------------------------------

_EMSD_110 = _course(
    "EMSD-110", "Music Theory for Agents", 3, 1, "musicianship",
    (), ("tools/senseweave/harmonic_planner.py", "tools/senseweave/reharmonizer.py"),
    description=(
        "Formal music theory for machine agents: scales, modes, intervals, "
        "chords, progressions, and functional harmony for algorithmic composition."
    ),
    learning_objectives=(
        "Construct major, minor, and modal scales from chromatic pitch classes",
        "Identify and classify intervals by size and quality",
        "Build triads, seventh chords, and extended harmonies",
        "Label harmonic functions and common cadence patterns",
    ),
    topics=(
        "Chromatic scale and pitch classes",
        "Major, minor, and modal scales",
        "Interval classification and quality",
        "Chord construction (triads through extensions)",
        "Functional harmony and Roman-numeral analysis",
        "Cadence patterns and resolution",
    ),
    exercises=(
        _ex(
            "ex01", "Interval and Scale Matrix",
            "Build an interval matrix and modal scale table that can seed "
            "production-course mode_scale decisions.",
            "constraint",
            (
                "intervals", "scale_degrees", "mode_scale", "root_pitch",
                "valid_step_pattern",
            ),
            template={
                "intervals": ["P1", "m2", "M2", "m3", "M3", "P4", "P5"],
                "scale_degrees": [0, 2, 4, 5, 7, 9, 11],
                "mode_scale": "ionian",
                "root_pitch": "C4",
                "valid_step_pattern": True,
            },
        ),
    ),
)

_EMSD_120 = _course(
    "EMSD-120", "Machine Ear Training", 3, 2, "musicianship",
    ("EMSD-110",), ("tools/senseweave/ear_engine.py", "tools/self_listener.py"),
    description=(
        "Computational listening and audio analysis: spectral recognition, "
        "pitch detection, rhythm tracking, and perceptual quality assessment."
    ),
    learning_objectives=(
        "Analyze spectral content using FFT-based methods",
        "Detect pitch and onset events in audio streams",
        "Evaluate mix quality through loudness and masking metrics",
        "Provide ear-training feedback on CypherClaw's own output",
    ),
    topics=(
        "Spectral analysis and FFT interpretation",
        "Pitch detection algorithms",
        "Onset detection and transient analysis",
        "Beat and tempo tracking",
        "Loudness measurement and metering",
        "Masking detection and correction",
    ),
)

_EMSD_130 = _course(
    "EMSD-130", "Instrument Design — The SuperCollider Synth as Instrument", 3, 2, "musicianship",
    ("EMSD-201",), ("tools/senseweave/instrument_patches.py", "tools/senseweave/voice_shaping.py"),
    description=(
        "Designing playable SuperCollider instruments: SynthDef as instrument, "
        "parameter mapping, voice allocation, and performance ergonomics."
    ),
    learning_objectives=(
        "Design SynthDefs as controllable instruments with expressive parameters",
        "Map MIDI controllers to synthesis parameters with appropriate scaling",
        "Implement polyphonic voice allocation strategies",
        "Optimize instrument response for real-time performance",
    ),
    topics=(
        "SynthDef as playable instrument",
        "MIDI controller mapping and scaling curves",
        "Voice allocation and polyphony management",
        "Parameter range design for expressiveness",
        "Performance latency optimization",
    ),
)

# ---------------------------------------------------------------------------
# Concentrate Electives (2 courses)
# ---------------------------------------------------------------------------

_EMSD_210 = _course(
    "EMSD-210", "Arrangement and Orchestration for Synthesis", 3, 3, "concentrate_elective",
    ("EMSD-110", "EMSD-201"), ("tools/senseweave/arrangement_engine.py",),
    description=(
        "Assigning musical roles to synthesis voices: register allocation, "
        "density management, and arrangement transitions for electronic ensemble."
    ),
    learning_objectives=(
        "Assign distinct roles (bass, pad, lead, texture) to synthesis voices",
        "Manage register allocation to avoid crowding",
        "Control density through doubling and thinning decisions",
        "Design arrangement transitions between sections",
    ),
    topics=(
        "Voice roles and register assignment",
        "Density management and layering",
        "Doubling, thinning, and textural contrast",
        "Arrangement transitions and builds",
        "Orchestration for electronic ensemble",
    ),
    exercises=(
        _ex(
            "ex01", "Chord Voicing Register Plan",
            "Assign chord tones to synthesis voices with explicit spacing, "
            "doubling, register, and mix-role constraints.",
            "constraint",
            (
                "voicings", "register_plan", "voice_roles",
                "spacing_limits", "doubling_policy",
            ),
            template={
                "voicings": {
                    "bass": ["root"],
                    "pad": ["third", "seventh"],
                    "lead": ["ninth"],
                },
                "register_plan": {"bass": "C2-C3", "pad": "G3-E5", "lead": "D5-A5"},
                "voice_roles": ["bass", "pad", "lead"],
                "spacing_limits": {"low_interval_min_semitones": 7},
                "doubling_policy": "double root only below C3",
            },
        ),
    ),
)

_EMSD_220 = _course(
    "EMSD-220", "Time, Rhythm, and Groove", 3, 3, "concentrate_elective",
    ("EMSD-102",), ("tools/senseweave/procedural_arc.py", "tools/senseweave/music_tracker.py"),
    description=(
        "Metric patterns, swing, groove, polyrhythm, and temporal structures "
        "for rhythmic electronic music composition and performance."
    ),
    learning_objectives=(
        "Implement standard and compound meter patterns",
        "Apply swing and groove timing to quantized events",
        "Design polyrhythmic and polymetric structures",
        "Use metric modulation for tempo transitions",
    ),
    topics=(
        "Meter and time signature systems",
        "Subdivision, swing, and shuffle",
        "Groove templates and timing humanization",
        "Polyrhythm and polymeter",
        "Metric modulation techniques",
        "Rhythmic density and phrase breath",
    ),
    exercises=(
        _ex(
            "ex01", "Groove Grid Template",
            "Create a bar-level groove grid with meter, subdivision, swing, "
            "accent, and density metadata for tracker scheduling.",
            "temporal",
            (
                "groove_grid", "meter", "subdivision", "swing_ratio",
                "accent_pattern", "density_profile",
            ),
            template={
                "groove_grid": [1, 0, 0.5, 0, 1, 0, 0.75, 0],
                "meter": "4/4",
                "subdivision": "eighth",
                "swing_ratio": 0.58,
                "accent_pattern": [0, 4, 6],
                "density_profile": "medium",
            },
        ),
    ),
)

# ---------------------------------------------------------------------------
# Specialization (11 courses)
# ---------------------------------------------------------------------------

_EMSD_250 = _course(
    "EMSD-250", "Generative Composition Systems", 3, 4, "specialization",
    ("EMSD-303",), ("tools/senseweave/procedural_arc.py", "tools/senseweave/synthesis/continuous_learner.py"),
    description=(
        "Self-evolving composition systems using continuous learning, "
        "evolutionary algorithms, and adaptive musical decision-making."
    ),
    learning_objectives=(
        "Design feedback loops that refine compositional output over time",
        "Implement aesthetic evaluation metrics for generated music",
        "Build systems that evolve without manual intervention",
        "Balance novelty and coherence in generative output",
    ),
    topics=(
        "Evolutionary algorithms in music",
        "Continuous learning and adaptation",
        "Self-modifying composition rules",
        "Aesthetic fitness functions",
        "Novelty search vs. coherence",
    ),
)

_EMSD_251 = _course(
    "EMSD-251", "The Theramini as Character", 3, 5, "specialization",
    ("EMSD-130", "EMSD-302"), ("tools/senseweave/theramini_duet.py", "tools/duet_composer.py"),
    description=(
        "Musical interpretation of Theramini gestures: pitch tracking, "
        "dynamic response, call-and-response, and accompaniment design."
    ),
    learning_objectives=(
        "Interpret Theramini pitch and volume gestures as musical intent",
        "Design responsive accompaniment that complements human input",
        "Implement call-and-response and imitation behaviors",
        "Maintain ensemble balance between generated and live sound",
    ),
    topics=(
        "Theramini gesture mapping and interpretation",
        "Pitch and volume tracking for musical response",
        "Call-and-response pattern design",
        "Accompaniment texture selection",
        "Ensemble balance and deference",
        "Musical turn-taking protocols",
    ),
    exercises=(
        _ex(
            "ex01", "Theramini Ensemble Cue Sheet",
            "Design a duet cue sheet that gives the Theramini and generated "
            "voices distinct ensemble roles, response windows, and balance rules.",
            "constraint",
            (
                "theramini_roles", "response_windows", "call_response",
                "deference_policy", "ensemble_balance",
            ),
            template={
                "theramini_roles": ["soloist", "gesture_source"],
                "response_windows": {"imitate_after_seconds": 2.0, "thin_after_seconds": 0.5},
                "call_response": "answer sustained human pitch with contrary motion",
                "deference_policy": "reduce accompaniment density while Theramini is active",
                "ensemble_balance": {"theramini_db_priority": 3.0},
            },
        ),
    ),
)

_EMSD_252 = _course(
    "EMSD-252", "Live Performance and Real-Time Decision Making", 3, 5, "specialization",
    ("EMSD-304",), ("tools/server_health.py", "tools/duet_composer.py"),
    description=(
        "Real-time musical decision-making under constraints: latency budgets, "
        "fallback strategies, live mixing, and performance flow."
    ),
    learning_objectives=(
        "Make musical decisions within strict latency budgets",
        "Implement graceful fallback when inputs are unavailable",
        "Maintain continuous audio output through system transitions",
        "Design performance flows that handle unexpected events",
    ),
    topics=(
        "Latency management and budgeting",
        "Fallback and graceful degradation strategies",
        "Live mixing automation",
        "Performance state machines",
        "Error recovery during playback",
    ),
)

_EMSD_253 = _course(
    "EMSD-253", "Sound Design for Narrative", 3, 5, "specialization",
    ("EMSD-201", "EMSD-302"),
    ("tools/senseweave/prosody_engine.py", "tools/senseweave/cadence_engine.py"),
    description=(
        "Designing sounds that convey mood and story: leitmotif, sonic branding, "
        "mood mapping, and synchronizing audio to narrative arc."
    ),
    learning_objectives=(
        "Design leitmotifs and sonic signatures for recurring themes",
        "Map synthesis parameters to emotional and narrative states",
        "Synchronize sound design choices to dramatic arc phases",
        "Create prosodic contours that convey intent without speech",
    ),
    topics=(
        "Leitmotif design and recurrence",
        "Sonic branding and identity",
        "Mood-to-parameter mapping",
        "Prosody and cadence in generated sound",
        "Narrative arc synchronization",
        "Emotional texture palettes",
    ),
    exercises=(
        _ex(
            "ex01", "Genre Strategy Translation",
            "Translate one genre strategy into concrete production choices for "
            "rhythm, harmony, synthesis, mix role, and scene-transition behavior.",
            "structural",
            (
                "genre_strategy", "reference_traits", "rhythm_choices",
                "synthesis_palette", "mix_role", "transition_type",
            ),
            template={
                "genre_strategy": "minimalist_process",
                "reference_traits": ["repetition", "gradual change", "clear pulse"],
                "rhythm_choices": {"meter_groove": "pulse", "density": "medium"},
                "synthesis_palette": ["subtractive_pluck", "additive_pad"],
                "mix_role": "ensemble",
                "transition_type": "seamless",
            },
        ),
    ),
)

_EMSD_254 = _course(
    "EMSD-254", "Environmental Sound Processing", 3, 4, "specialization",
    ("EMSD-202", "EMSD-120"), ("tools/senseweave/sample_lab.py", "tools/room_listener.py"),
    description=(
        "Capturing and transforming environmental audio: field recording analysis, "
        "noise classification, spectral transformation, and room acoustics."
    ),
    learning_objectives=(
        "Classify environmental sound sources for compositional use",
        "Transform field recordings through spectral processing",
        "Integrate room acoustic information into production decisions",
        "Design compositions that respond to environmental input",
    ),
    topics=(
        "Field recording analysis",
        "Environmental noise classification",
        "Spectral transformation of captured audio",
        "Room acoustics integration",
        "Microphone placement and source separation",
    ),
)

_EMSD_255 = _course(
    "EMSD-255", "Remixing and Transformation Techniques", 3, 6, "specialization",
    ("EMSD-202", "EMSD-401"),
    ("tools/senseweave/repertoire_memory.py", "tools/senseweave/sample_lab.py"),
    description=(
        "Deconstructing and reconstructing existing material: repertoire recall, "
        "spectral morphing, temporal manipulation, and recontextualization."
    ),
    learning_objectives=(
        "Recall and deconstruct material from repertoire memory",
        "Apply spectral morphing between source and target timbres",
        "Use temporal manipulation to reframe existing material",
        "Maintain artistic coherence through transformation chains",
    ),
    topics=(
        "Repertoire recall and material selection",
        "Material deconstruction techniques",
        "Spectral morphing and interpolation",
        "Temporal manipulation and re-sequencing",
        "Recontextualization strategies",
    ),
)

_EMSD_256 = _course(
    "EMSD-256", "Acoustic Ecology and Soundscape Composition", 3, 6, "specialization",
    ("EMSD-254",), ("tools/inner_life/world_model.py", "tools/senseweave/sample_lab.py"),
    description=(
        "Soundscape-aware composition: keynote sounds, sound marks, acoustic "
        "ecology principles, and environmental integration."
    ),
    learning_objectives=(
        "Analyze environmental soundscapes for compositional material",
        "Identify keynote sounds and sound marks in an environment",
        "Design compositions that complement the acoustic environment",
        "Integrate ecological awareness into production choices",
    ),
    topics=(
        "Soundscape analysis and taxonomy",
        "Keynote sounds and sound marks",
        "Acoustic ecology principles",
        "Site-responsive composition",
        "Environmental integration design",
    ),
)

_EMSD_257 = _course(
    "EMSD-257", "Cross-Modal Translation — Sound and Visuals", 3, 6, "specialization",
    ("EMSD-401",), ("tools/senseweave/dsp_scene_lab.py", "tools/glyphweave"),
    description=(
        "Translating between audio and visual domains: synesthesia mapping, "
        "audio-reactive graphics, and GlyphWeave integration."
    ),
    learning_objectives=(
        "Map audio features to visual parameters and vice versa",
        "Design audio-reactive visual elements for GlyphWeave",
        "Create coherent audiovisual experiences from unified data",
        "Translate between spectral, temporal, and spatial domains",
    ),
    topics=(
        "Synesthesia mapping strategies",
        "Audio-to-visual parameter translation",
        "Audio-reactive graphics pipelines",
        "GlyphWeave integration points",
        "Cross-modal coherence metrics",
    ),
    exercises=(
        _ex(
            "ex01", "SenseWeave Mapping Contract",
            "Map audio analysis features to GlyphWeave visual targets with "
            "stable names, ranges, and coherence checks.",
            "constraint",
            (
                "senseweave_mapping", "audio_features", "visual_targets",
                "range_policy", "coherence_checks",
            ),
            template={
                "senseweave_mapping": {"brightness": "color_luma", "density": "stroke_count"},
                "audio_features": ["brightness", "motion", "texture", "density"],
                "visual_targets": ["color_luma", "particle_speed", "edge_noise", "stroke_count"],
                "range_policy": {"input": "0.0-1.0", "output": "normalized"},
                "coherence_checks": ["monotonic_density", "bounded_motion"],
            },
        ),
    ),
)

_EMSD_258 = _course(
    "EMSD-258", "Music for Installation Art", 3, 6, "specialization",
    ("EMSD-303", "EMSD-L203"),
    ("tools/senseweave/procedural_arc.py", "tools/senseweave/capstone_engine.py"),
    description=(
        "Long-duration generative installations: site-specific composition, "
        "spatial audio, durational planning, and installation reliability."
    ),
    learning_objectives=(
        "Design compositions that sustain interest over hours of playback",
        "Configure spatial audio for physical installation spaces",
        "Plan generative variety that avoids repetition fatigue",
        "Ensure system reliability for unattended operation",
    ),
    topics=(
        "Site-specific composition approaches",
        "Spatial audio for installations",
        "Durational design and pacing",
        "Generative variety and anti-repetition",
        "Installation reliability and monitoring",
    ),
)

_EMSD_259 = _course(
    "EMSD-259", "Collaborative Machine Music", 3, 7, "specialization",
    ("EMSD-251", "EMSD-252"),
    ("tools/senseweave/theramini_duet.py", "tools/senseweave/procedural_arc.py"),
    description=(
        "Multi-agent musical collaboration: ensemble negotiation, role assignment, "
        "musical turn-taking, and collaborative improvisation."
    ),
    learning_objectives=(
        "Design negotiation protocols for multi-agent music making",
        "Implement dynamic role assignment in ensemble contexts",
        "Balance individual expression with ensemble coherence",
        "Create collaborative improvisation strategies",
    ),
    topics=(
        "Agent coordination and negotiation",
        "Dynamic role assignment protocols",
        "Musical turn-taking and listening",
        "Ensemble balance and coherence",
        "Collaborative improvisation design",
    ),
)

_EMSD_260 = _course(
    "EMSD-260", "Portfolio Development and Artistic Identity", 3, 8, "specialization",
    ("EMSD-499",),
    ("tools/senseweave/artistic_identity.py", "tools/senseweave/repertoire_memory.py"),
    description=(
        "Curating a body of work and developing artistic voice: portfolio analysis, "
        "style evolution tracking, and artistic statement formulation."
    ),
    learning_objectives=(
        "Curate a portfolio that demonstrates artistic range and development",
        "Analyze stylistic patterns across a body of work",
        "Formulate an artistic statement grounded in production history",
        "Track artistic identity evolution over time",
    ),
    topics=(
        "Portfolio curation and selection",
        "Style analysis across compositions",
        "Artistic statement formulation",
        "Repertoire review and reflection",
        "Identity evolution tracking",
    ),
)

# ---------------------------------------------------------------------------
# Foundations (14 courses)
# ---------------------------------------------------------------------------

_EMSD_L101 = _course(
    "EMSD-L101", "Musical Language and Description", 3, 1, "foundations",
    (), ("tools/senseweave/prosody_engine.py",),
    description=(
        "Formal vocabulary for describing musical events: terminology, "
        "description frameworks, and analytical writing for machine music criticism."
    ),
    learning_objectives=(
        "Use standard musical terminology to describe sonic events",
        "Generate structured analysis prose for compositions",
        "Apply description frameworks consistently across genres",
    ),
    topics=(
        "Musical terminology and vocabulary",
        "Description and analysis frameworks",
        "Technical vs. aesthetic description",
        "Genre-specific vocabulary",
        "Analytical writing conventions",
    ),
)

_EMSD_L110 = _course(
    "EMSD-L110", "History of Electronic Music", 3, 2, "foundations",
    (), ("docs/cypherclaw-emsd-roadmap.md",),
    description=(
        "Survey of electronic music from early experiments to AI composition: "
        "movements, practitioners, technologies, and contemporary influence."
    ),
    learning_objectives=(
        "Identify major periods and movements in electronic music history",
        "Contextualize CypherClaw's work within historical lineage",
        "Reference key practitioners and their contributions",
    ),
    topics=(
        "Musique concrete and early tape music",
        "Cologne school and electronic studios",
        "Analog synthesis and the Moog era",
        "Digital revolution and software instruments",
        "Laptop music and live coding",
        "AI-assisted and generative music",
    ),
)

_EMSD_L201 = _course(
    "EMSD-L201", "Acoustics and Psychoacoustics", 3, 2, "foundations",
    ("EMSD-101",), ("tools/senseweave/mix_engine.py",),
    description=(
        "Physical acoustics and perception of sound: frequency, loudness, "
        "masking, spatial hearing, and equal-loudness contours for production."
    ),
    learning_objectives=(
        "Apply equal-loudness contours to mixing decisions",
        "Identify masking conditions and apply corrective EQ",
        "Model spatial hearing for stereo and multichannel placement",
    ),
    topics=(
        "Fletcher-Munson curves and equal-loudness contours",
        "Critical bands and frequency resolution",
        "Simultaneous and temporal masking",
        "Spatial perception and localization",
        "Perceptual loudness models",
    ),
)

_EMSD_L202 = _course(
    "EMSD-L202", "Music Cognition for Agents", 3, 3, "foundations",
    ("EMSD-110",), ("tools/senseweave/ear_engine.py",),
    description=(
        "Modeling listener perception and cognition: expectation, surprise, "
        "tension, grouping, stream segregation, and musical memory."
    ),
    learning_objectives=(
        "Model listener expectation and surprise in compositional planning",
        "Apply grouping principles to arrangement decisions",
        "Design for auditory stream segregation",
    ),
    topics=(
        "Musical expectation and prediction",
        "Surprise and information content",
        "Tension and resolution models",
        "Auditory grouping principles",
        "Stream segregation",
        "Musical memory and recall",
    ),
)

_EMSD_L203 = _course(
    "EMSD-L203", "Sound Art and Installation History", 3, 4, "foundations",
    (), ("docs/cypherclaw-emsd-roadmap.md",),
    description=(
        "Historical context for sound art and installation: key works, "
        "practitioners, spatial composition, and site-specific precedent."
    ),
    learning_objectives=(
        "Reference key sound art works and practitioners",
        "Contextualize installation practice within art history",
        "Identify spatial composition techniques from historical examples",
    ),
    topics=(
        "Sound sculpture and sonic art history",
        "Installation art precedents",
        "Spatial composition techniques",
        "Site-specific art practice",
        "Gallery and museum exhibition contexts",
    ),
)

_EMSD_L204 = _course(
    "EMSD-L204", "Aesthetics and Artistic Intent", 3, 5, "foundations",
    ("EMSD-L203",), ("tools/senseweave/artistic_identity.py",),
    description=(
        "Aesthetic theory for machine creativity: intentionality, beauty, "
        "interest, artistic identity, and ethics of automated creative decisions."
    ),
    learning_objectives=(
        "Articulate aesthetic choices with reference to artistic intent",
        "Connect production decisions to a coherent artistic vision",
        "Evaluate beauty versus interest in compositional output",
    ),
    topics=(
        "Aesthetic theory and criticism",
        "Intentionality in machine art",
        "Beauty vs. interest in composition",
        "Artistic vision and identity",
        "Creative ethics for autonomous systems",
    ),
)

_EMSD_L301 = _course(
    "EMSD-L301", "Music, Space, and Architecture", 3, 3, "foundations",
    ("EMSD-L201",), ("tools/senseweave/mix_engine.py",),
    description=(
        "How physical space shapes musical perception: room acoustics, "
        "reverberation, architectural resonance, and site-specific mixing."
    ),
    learning_objectives=(
        "Analyze room acoustics for production context",
        "Apply reverberation models appropriate to physical space",
        "Design spatial audio for specific architectural environments",
    ),
    topics=(
        "Room acoustics and modal resonance",
        "Reverberation modeling and simulation",
        "Architectural resonance and standing waves",
        "Spatial audio design for rooms",
        "Site-specific mixing strategies",
    ),
)

_EMSD_L302 = _course(
    "EMSD-L302", "Audience Perception and Response", 3, 5, "foundations",
    ("EMSD-L202",),
    ("tools/senseweave/procedural_arc.py", "tools/senseweave/cadence_engine.py"),
    description=(
        "Predicting audience engagement: attention patterns, emotional arcs, "
        "habituation, and engagement metrics for installation audiences."
    ),
    learning_objectives=(
        "Model audience attention and engagement over time",
        "Design for habituation avoidance in long-duration work",
        "Predict emotional response curves for different arc shapes",
    ),
    topics=(
        "Attention span and engagement modeling",
        "Emotional arc design for installations",
        "Habituation and novelty management",
        "Surprise and anticipation balance",
        "Engagement metrics and evaluation",
    ),
)

_EMSD_L303 = _course(
    "EMSD-L303", "Project Management for Generative Systems", 3, 6, "foundations",
    (), ("tools/server_health.py", "tools/healer.py"),
    description=(
        "Planning and maintaining generative music systems: reliability, "
        "monitoring, logging, graceful degradation, and continuous operation."
    ),
    learning_objectives=(
        "Plan system reliability for unattended operation",
        "Implement monitoring and logging for generative systems",
        "Design graceful degradation for component failures",
    ),
    topics=(
        "System reliability engineering",
        "Monitoring and alerting strategies",
        "Logging for generative systems",
        "Graceful degradation design",
        "Maintenance scheduling",
    ),
)

_EMSD_L304 = _course(
    "EMSD-L304", "The Ethics of Machine Creativity", 3, 7, "foundations",
    ("EMSD-L204",), ("docs/cypherclaw-emsd-roadmap.md",),
    description=(
        "Ethical frameworks for AI-generated music: authorship, originality, "
        "attribution, cultural sensitivity, and creative responsibility."
    ),
    learning_objectives=(
        "Evaluate authorship and attribution for machine-generated works",
        "Apply originality standards to generative output",
        "Consider cultural sensitivity in style references and genre borrowing",
    ),
    topics=(
        "Authorship and attribution in AI art",
        "Originality standards for generative work",
        "Cultural sensitivity in music",
        "Creative responsibility and ethics",
        "Consent and training data provenance",
    ),
)

_EMSD_L401 = _course(
    "EMSD-L401", "Mathematics of Sound", 3, 2, "foundations",
    ("EMSD-101",), ("tools/senseweave/dsp_scene_lab.py",),
    description=(
        "Mathematical foundations for audio: Fourier analysis, wave equations, "
        "harmonic series, signal math, and tuning system calculations."
    ),
    learning_objectives=(
        "Apply Fourier analysis to decompose complex waveforms",
        "Calculate harmonic series relationships",
        "Model wave propagation and interference patterns",
        "Compute tuning system frequencies and ratios",
    ),
    topics=(
        "Fourier analysis and decomposition",
        "Wave equations and propagation",
        "Harmonic series and overtones",
        "Signal mathematics",
        "Tuning systems and ratio-based pitch",
    ),
)

_EMSD_L402 = _course(
    "EMSD-L402", "Digital Signal Processing Theory", 3, 4, "foundations",
    ("EMSD-L401",), ("tools/senseweave/dsp_scene_lab.py", "tools/senseweave/mix_engine.py"),
    description=(
        "DSP fundamentals for audio: Z-transform, filter design, convolution, "
        "windowing functions, and FFT-based spectral analysis."
    ),
    learning_objectives=(
        "Apply Z-transform analysis to digital filter design",
        "Design IIR and FIR filters for audio applications",
        "Implement convolution for audio effects processing",
        "Select windowing functions for spectral analysis accuracy",
    ),
    topics=(
        "Z-transform and transfer functions",
        "IIR and FIR filter design",
        "Convolution and correlation",
        "Windowing functions and spectral leakage",
        "FFT implementation strategies",
    ),
)

_EMSD_L403 = _course(
    "EMSD-L403", "Information Theory and Music", 3, 6, "foundations",
    ("EMSD-L402", "EMSD-L202"),
    ("tools/senseweave/ear_engine.py", "tools/senseweave/artistic_identity.py"),
    description=(
        "Information-theoretic analysis of music: entropy, redundancy, surprise, "
        "mutual information, and complexity measures for evaluation."
    ),
    learning_objectives=(
        "Compute entropy and redundancy measures for musical sequences",
        "Apply surprise metrics to evaluate compositional interest",
        "Use mutual information to analyze musical relationships",
    ),
    topics=(
        "Shannon entropy in music",
        "Redundancy and compression",
        "Surprise and information content",
        "Mutual information and dependency",
        "Complexity measures for composition",
    ),
)

_EMSD_L404 = _course(
    "EMSD-L404", "Machine Learning for Audio", 3, 7, "foundations",
    ("EMSD-120", "EMSD-L402"),
    ("tools/senseweave/sample_lab.py", "tools/senseweave/ear_engine.py"),
    description=(
        "Machine learning for audio: feature extraction, classification, "
        "neural audio synthesis, latent spaces, and transfer learning."
    ),
    learning_objectives=(
        "Extract meaningful features from audio signals for ML models",
        "Apply classification techniques to audio analysis tasks",
        "Explore latent spaces for audio generation and manipulation",
    ),
    topics=(
        "Audio feature extraction (MFCCs, spectral features)",
        "Classification techniques for audio",
        "Neural audio synthesis approaches",
        "Latent space exploration",
        "Transfer learning for audio models",
    ),
)

# ---------------------------------------------------------------------------
# Assembled catalog
# ---------------------------------------------------------------------------

COURSE_CATALOG: tuple[Course, ...] = (
    _EMSD_101, _EMSD_102, _EMSD_201, _EMSD_202,
    _EMSD_301, _EMSD_302, _EMSD_303, _EMSD_304,
    _EMSD_401, _EMSD_499,
    _EMSD_110, _EMSD_120, _EMSD_130,
    _EMSD_210, _EMSD_220,
    _EMSD_250, _EMSD_251, _EMSD_252, _EMSD_253, _EMSD_254,
    _EMSD_255, _EMSD_256, _EMSD_257, _EMSD_258, _EMSD_259, _EMSD_260,
    _EMSD_L101, _EMSD_L110, _EMSD_L201, _EMSD_L202, _EMSD_L203, _EMSD_L204,
    _EMSD_L301, _EMSD_L302, _EMSD_L303, _EMSD_L304,
    _EMSD_L401, _EMSD_L402, _EMSD_L403, _EMSD_L404,
)

CATALOG_CATEGORIES: tuple[str, ...] = (
    "core_concentrate",
    "musicianship",
    "concentrate_elective",
    "specialization",
    "foundations",
)

EXERCISE_VERIFIERS: tuple[str, ...] = (
    "structural",
    "constraint",
    "spectral",
    "temporal",
)


def all_courses() -> tuple[Course, ...]:
    return COURSE_CATALOG


def course_by_code(code: str) -> Course:
    for course in COURSE_CATALOG:
        if course.code == code:
            return course
    raise KeyError(code)


def curriculum_totals() -> dict[str, int]:
    return {
        "courses": len(COURSE_CATALOG),
        "credits": sum(course.credits for course in COURSE_CATALOG),
    }


def courses_by_category(
    category: str | None = None,
    courses: tuple[Course, ...] | None = None,
) -> dict[str, tuple[Course, ...]] | tuple[Course, ...]:
    """Group courses by category, or return one category when requested."""
    if courses is None:
        courses = COURSE_CATALOG

    grouped: dict[str, list[Course]] = {name: [] for name in CATALOG_CATEGORIES}
    for course in courses:
        grouped.setdefault(course.category, []).append(course)

    frozen = {
        name: tuple(items)
        for name, items in grouped.items()
        if items or category is None
    }
    if category is not None:
        return frozen.get(category, ())
    return frozen


def courses_for_semester(
    semester: int,
    courses: tuple[Course, ...] | None = None,
) -> tuple[Course, ...]:
    """Return courses offered in one semester, preserving catalog order."""
    if courses is None:
        courses = COURSE_CATALOG

    selected: list[Course] = []
    for course in courses:
        if course.semester == semester:
            selected.append(course)
    return tuple(selected)


def prerequisite_graph(
    courses: tuple[Course, ...] | None = None,
) -> dict[str, tuple[str, ...]]:
    """Return a course-code to prerequisite-code mapping."""
    if courses is None:
        courses = COURSE_CATALOG

    graph: dict[str, tuple[str, ...]] = {}
    for course in courses:
        graph[course.code] = course.prerequisites
    return graph


def exercise_index(
    courses: tuple[Course, ...] | None = None,
) -> dict[str, ExerciseSpec]:
    """Index exercises by stable ``COURSE/exercise`` key."""
    if courses is None:
        courses = COURSE_CATALOG

    index: dict[str, ExerciseSpec] = {}
    for course in courses:
        for exercise in course.exercises:
            index[f"{course.code}/{exercise.id}"] = exercise
    return index


def catalog_summary(
    courses: tuple[Course, ...] | None = None,
) -> dict[str, object]:
    """Return compact aggregate statistics for the curriculum catalog."""
    if courses is None:
        courses = COURSE_CATALOG

    category_counts: dict[str, int] = {}
    semesters: set[int] = set()
    exercise_count = 0
    credit_count = 0

    for course in courses:
        category_counts[course.category] = category_counts.get(course.category, 0) + 1
        semesters.add(course.semester)
        exercise_count += len(course.exercises)
        credit_count += course.credits

    return {
        "course_count": len(courses),
        "credit_count": credit_count,
        "exercise_count": exercise_count,
        "semester_count": len(semesters),
        "category_counts": dict(sorted(category_counts.items())),
    }


def validate_catalog(
    courses: tuple[Course, ...] | None = None,
) -> tuple[str, ...]:
    """Validate basic catalog consistency and return human-readable errors."""
    if courses is None:
        courses = COURSE_CATALOG

    errors: list[str] = []
    valid_codes = {course.code for course in courses}
    seen_codes: set[str] = set()

    for course in courses:
        if course.code in seen_codes:
            errors.append(f"duplicate course code: {course.code}")
        seen_codes.add(course.code)

        if course.category not in CATALOG_CATEGORIES:
            errors.append(f"{course.code} has invalid category: {course.category}")
        if course.credits <= 0:
            errors.append(f"{course.code} has nonpositive credits: {course.credits}")
        if course.semester <= 0:
            errors.append(f"{course.code} has invalid semester: {course.semester}")

        for prerequisite in course.prerequisites:
            if prerequisite not in valid_codes:
                errors.append(
                    f"{course.code} references missing prerequisite: {prerequisite}"
                )

        seen_exercise_ids: set[str] = set()
        for exercise in course.exercises:
            key = f"{course.code}/{exercise.id}"
            if exercise.id in seen_exercise_ids:
                errors.append(f"{course.code} has duplicate exercise id: {exercise.id}")
            seen_exercise_ids.add(exercise.id)

            if exercise.verifier not in EXERCISE_VERIFIERS:
                errors.append(f"{key} has invalid verifier: {exercise.verifier}")
            if not exercise.expected_features:
                errors.append(f"{key} has no expected features")
            if not exercise.title:
                errors.append(f"{key} has empty title")
            if not exercise.objective:
                errors.append(f"{key} has empty objective")

    return tuple(errors)


def scaffold_relpaths(course: Course) -> tuple[str, ...]:
    paths = [
        f"{course.code}/README.md",
        f"{course.code}/reference/01-overview.md",
        f"{course.code}/prompts/composition.md",
        f"{course.code}/prompts/analysis.md",
        f"{course.code}/exercises/README.md",
        f"{course.code}/COMPLETION.md",
    ]
    for ex in course.exercises:
        paths.append(f"{course.code}/exercises/{ex.id}/spec.json")
    return tuple(paths)
