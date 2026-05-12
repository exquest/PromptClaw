"""Counterpoint-relationship rule registry.

Defines six voice-pair relationship types — contrary, oblique, parallel,
echo, commentary, completion — each as a frozen dataclass with voice-pair
constraints, interval rules, and arc-phase affinity.  Lookup and selection
functions follow the strategy registry pattern used by
synthesis_architecture_registry and synthdef_registry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from senseweave.music_theory import Interval, interval_between


RelationshipId = Literal[
    "contrary",
    "oblique",
    "parallel",
    "echo",
    "commentary",
    "completion",
]

REQUIRED_RELATIONSHIPS: frozenset[str] = frozenset(
    RelationshipId.__args__,  # type: ignore[attr-defined]
)

ArcPhaseName = Literal[
    "Divination",
    "Emergence",
    "Conversation",
    "Convergence",
    "Crystallization",
]

REQUIRED_PHASES: frozenset[str] = frozenset(
    ArcPhaseName.__args__,  # type: ignore[attr-defined]
)

VoiceRole = Literal[
    "melody",
    "bass",
    "counter",
    "color",
    "foundation",
    "figuration",
    "rhythm",
]

ALL_VOICE_ROLES: frozenset[str] = frozenset(
    VoiceRole.__args__,  # type: ignore[attr-defined]
)

MotionKind = Literal["parallel", "contrary", "oblique", "static", "none"]


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IntervalConstraint:
    """Allowed intervals for a counterpoint relationship."""

    preferred_semitones: tuple[int, ...]
    max_leap: int
    allow_unison: bool = False
    allow_parallel_fifths: bool = False


@dataclass(frozen=True)
class VoicePairConstraint:
    """Which voice-role pairings are valid for a relationship."""

    leader_roles: tuple[str, ...]
    follower_roles: tuple[str, ...]


@dataclass(frozen=True)
class CounterpointRule:
    """Complete registry record for one counterpoint relationship type."""

    relationship_id: str
    label: str
    summary: str
    voice_pair: VoicePairConstraint
    intervals: IntervalConstraint
    arc_affinity: dict[str, float]
    fallback: str


# ---------------------------------------------------------------------------
# Registry entries
# ---------------------------------------------------------------------------

_RULES: tuple[CounterpointRule, ...] = (
    CounterpointRule(
        relationship_id="contrary",
        label="Contrary Motion",
        summary="Voices move in opposite directions; creates tension and independence.",
        voice_pair=VoicePairConstraint(
            leader_roles=("melody", "counter", "figuration"),
            follower_roles=("bass", "counter", "foundation"),
        ),
        intervals=IntervalConstraint(
            preferred_semitones=(3, 4, 5, 7, 8, 9),
            max_leap=12,
            allow_unison=False,
            allow_parallel_fifths=False,
        ),
        arc_affinity={
            "Divination": 0.3,
            "Emergence": 0.7,
            "Conversation": 0.9,
            "Convergence": 0.5,
            "Crystallization": 0.2,
        },
        fallback="parallel",
    ),
    CounterpointRule(
        relationship_id="oblique",
        label="Oblique Motion",
        summary="One voice sustains while the other moves; anchors harmonic field.",
        voice_pair=VoicePairConstraint(
            leader_roles=("melody", "counter", "figuration"),
            follower_roles=("foundation", "bass", "color"),
        ),
        intervals=IntervalConstraint(
            preferred_semitones=(0, 3, 4, 5, 7),
            max_leap=7,
            allow_unison=True,
            allow_parallel_fifths=True,
        ),
        arc_affinity={
            "Divination": 0.8,
            "Emergence": 0.4,
            "Conversation": 0.5,
            "Convergence": 0.6,
            "Crystallization": 0.7,
        },
        fallback="parallel",
    ),
    CounterpointRule(
        relationship_id="parallel",
        label="Parallel Motion",
        summary="Voices move in the same direction at a fixed interval; reinforces line.",
        voice_pair=VoicePairConstraint(
            leader_roles=("melody", "counter", "bass"),
            follower_roles=("counter", "color", "figuration"),
        ),
        intervals=IntervalConstraint(
            preferred_semitones=(3, 4, 7),
            max_leap=7,
            allow_unison=False,
            allow_parallel_fifths=False,
        ),
        arc_affinity={
            "Divination": 0.2,
            "Emergence": 0.6,
            "Conversation": 0.7,
            "Convergence": 0.9,
            "Crystallization": 0.3,
        },
        fallback="contrary",
    ),
    CounterpointRule(
        relationship_id="echo",
        label="Echo / Imitation",
        summary="Follower restates leader material after a delay; creates depth.",
        voice_pair=VoicePairConstraint(
            leader_roles=("melody", "counter", "figuration"),
            follower_roles=("counter", "color", "figuration"),
        ),
        intervals=IntervalConstraint(
            preferred_semitones=(0, 5, 7, 12),
            max_leap=12,
            allow_unison=True,
            allow_parallel_fifths=True,
        ),
        arc_affinity={
            "Divination": 0.6,
            "Emergence": 0.5,
            "Conversation": 0.4,
            "Convergence": 0.7,
            "Crystallization": 0.9,
        },
        fallback="commentary",
    ),
    CounterpointRule(
        relationship_id="commentary",
        label="Commentary",
        summary="Free counterline that reacts to but does not imitate the leader.",
        voice_pair=VoicePairConstraint(
            leader_roles=("melody", "bass", "counter"),
            follower_roles=("counter", "color", "figuration", "rhythm"),
        ),
        intervals=IntervalConstraint(
            preferred_semitones=(2, 3, 4, 5, 7, 9, 10),
            max_leap=14,
            allow_unison=False,
            allow_parallel_fifths=False,
        ),
        arc_affinity={
            "Divination": 0.4,
            "Emergence": 0.8,
            "Conversation": 0.6,
            "Convergence": 0.3,
            "Crystallization": 0.5,
        },
        fallback="contrary",
    ),
    CounterpointRule(
        relationship_id="completion",
        label="Completion",
        summary="Follower fills gaps left by the leader; interlocking rhythm.",
        voice_pair=VoicePairConstraint(
            leader_roles=("melody", "counter", "rhythm"),
            follower_roles=("counter", "figuration", "rhythm", "bass"),
        ),
        intervals=IntervalConstraint(
            preferred_semitones=(0, 3, 4, 5, 7),
            max_leap=10,
            allow_unison=True,
            allow_parallel_fifths=False,
        ),
        arc_affinity={
            "Divination": 0.5,
            "Emergence": 0.3,
            "Conversation": 0.8,
            "Convergence": 0.4,
            "Crystallization": 0.6,
        },
        fallback="echo",
    ),
)


# ---------------------------------------------------------------------------
# Indexed lookups
# ---------------------------------------------------------------------------

COUNTERPOINT_REGISTRY: dict[str, CounterpointRule] = {
    r.relationship_id: r for r in _RULES
}


def get_rule(relationship_id: str) -> CounterpointRule:
    """Look up a rule by relationship id.  Raises KeyError if unknown."""
    key = relationship_id.strip()
    if key not in COUNTERPOINT_REGISTRY:
        raise KeyError(relationship_id)
    return COUNTERPOINT_REGISTRY[key]


def rules_for_leader_role(role: str) -> tuple[CounterpointRule, ...]:
    """Return all rules where *role* is a valid leader."""
    key = role.strip()
    if key not in ALL_VOICE_ROLES:
        return ()
    matches: list[CounterpointRule] = []
    for rule in _RULES:
        if key in rule.voice_pair.leader_roles:
            matches.append(rule)
    return tuple(matches)


def rules_for_follower_role(role: str) -> tuple[CounterpointRule, ...]:
    """Return all rules where *role* is a valid follower."""
    key = role.strip()
    if key not in ALL_VOICE_ROLES:
        return ()
    matches: list[CounterpointRule] = []
    for rule in _RULES:
        if key in rule.voice_pair.follower_roles:
            matches.append(rule)
    return tuple(matches)


def rules_for_voice_pair(
    leader_role: str,
    follower_role: str,
) -> tuple[CounterpointRule, ...]:
    """Return rules valid for a specific leader/follower role pairing."""
    leader = leader_role.strip()
    follower = follower_role.strip()
    if leader not in ALL_VOICE_ROLES or follower not in ALL_VOICE_ROLES:
        return ()
    matches: list[CounterpointRule] = []
    for rule in _RULES:
        if leader in rule.voice_pair.leader_roles and follower in rule.voice_pair.follower_roles:
            matches.append(rule)
    return tuple(matches)


def rules_for_phase(
    phase: str,
    *,
    threshold: float = 0.0,
) -> tuple[CounterpointRule, ...]:
    """Return rules with affinity above *threshold* for *phase*, highest first."""
    key = phase.strip()
    ranked: list[tuple[float, CounterpointRule]] = []
    for rule in _RULES:
        affinity = rule.arc_affinity.get(key, 0.0)
        if affinity > threshold:
            ranked.append((affinity, rule))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return tuple(rule for _, rule in ranked)


def best_rule_for_phase(phase: str) -> CounterpointRule:
    """Return the single rule with the highest affinity for *phase*."""
    key = phase.strip()
    best = _RULES[0]
    best_affinity = best.arc_affinity.get(key, 0.0)
    for rule in _RULES[1:]:
        affinity = rule.arc_affinity.get(key, 0.0)
        if affinity > best_affinity:
            best = rule
            best_affinity = affinity
    return best


def resolve_rule(relationship_id: str) -> CounterpointRule:
    """Return the rule, falling back if *relationship_id* is unknown."""
    if relationship_id in COUNTERPOINT_REGISTRY:
        return COUNTERPOINT_REGISTRY[relationship_id]
    for rule in _RULES:
        if rule.fallback == relationship_id:
            return rule
    return COUNTERPOINT_REGISTRY["parallel"]


def covered_relationships() -> frozenset[str]:
    """Set of relationship IDs represented in the registry."""
    return frozenset(r.relationship_id for r in _RULES)


# ---------------------------------------------------------------------------
# Verification and Scoring
# ---------------------------------------------------------------------------

def verify_resolution(leader_notes: tuple[int, int], follower_notes: tuple[int, int]) -> bool:
    """
    Verify resolution-completion for a single interval transition.
    If the first vertical interval is a sharp dissonance, both voices
    must move stepwise (0, 1, or 2 semitones) to resolve it.
    """
    initial_interval = interval_between(leader_notes[0], follower_notes[0])
    if initial_interval.consonance != "sharp_dissonance":
        return True
    
    leader_motion = abs(leader_notes[1] - leader_notes[0])
    follower_motion = abs(follower_notes[1] - follower_notes[0])
    
    return leader_motion <= 2 and follower_motion <= 2


def voice_leading_smoothness(leader_notes: tuple[int, ...], follower_notes: tuple[int, ...]) -> float:
    """
    Calculate voice-leading smoothness scoring for a pair of voices.
    Returns the average size of leaps (in semitones) across all melodic
    intervals in both voices. A lower score means smoother voice-leading.
    """
    total_motion = 0
    intervals = 0

    if len(leader_notes) > 1:
        total_motion += sum(abs(leader_notes[i] - leader_notes[i-1]) for i in range(1, len(leader_notes)))
        intervals += len(leader_notes) - 1

    if len(follower_notes) > 1:
        total_motion += sum(abs(follower_notes[i] - follower_notes[i-1]) for i in range(1, len(follower_notes)))
        intervals += len(follower_notes) - 1

    if intervals == 0:
        return 0.0

    return float(total_motion) / intervals


# ---------------------------------------------------------------------------
# Dissonance Metadata (T-018@Zb)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DissonanceAnnotation:
    """Metadata for one vertical interval between two voices."""

    beat_index: int
    leader_midi: int
    follower_midi: int
    interval: Interval
    consonance: str
    resolved: bool | None


@dataclass(frozen=True)
class DissonanceReport:
    """Analysis of dissonance and resolution across a voice-pair sequence."""

    annotations: tuple[DissonanceAnnotation, ...]
    sharp_dissonance_count: int
    mild_dissonance_count: int
    unresolved_count: int
    resolution_rate: float


@dataclass(frozen=True)
class MotionProfile:
    """Summary of melodic motion between two voices."""

    transitions: int
    parallel_count: int
    contrary_count: int
    oblique_count: int
    static_count: int
    dominant_motion: MotionKind
    stepwise_rate: float


@dataclass(frozen=True)
class CounterpointFit:
    """One scored fit between a rule and a concrete voice pair."""

    rule_id: str
    label: str
    phase: str
    leader_role: str
    follower_role: str
    score: float
    passed: bool
    voice_pair_ok: bool
    preferred_interval_rate: float
    leap_ok_rate: float
    motion_match_rate: float
    motion: MotionProfile
    dissonance: DissonanceReport


def analyze_dissonance(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
) -> DissonanceReport:
    """Annotate each vertical interval with consonance metadata from music_theory.py.

    For sharp dissonances, checks whether the next beat resolves stepwise
    (both voices move <=2 semitones) to a non-sharp-dissonance interval.
    """
    pair_count = min(len(leader_notes), len(follower_notes))
    if pair_count == 0:
        return DissonanceReport(
            annotations=(),
            sharp_dissonance_count=0,
            mild_dissonance_count=0,
            unresolved_count=0,
            resolution_rate=1.0,
        )

    annotations: list[DissonanceAnnotation] = []
    sharp_count = 0
    mild_count = 0
    unresolved = 0

    for i in range(pair_count):
        iv = interval_between(leader_notes[i], follower_notes[i])
        consonance = iv.consonance
        resolved: bool | None = None

        if consonance == "sharp_dissonance":
            sharp_count += 1
            if i + 1 < pair_count:
                leader_motion = abs(leader_notes[i + 1] - leader_notes[i])
                follower_motion = abs(follower_notes[i + 1] - follower_notes[i])
                next_iv = interval_between(leader_notes[i + 1], follower_notes[i + 1])
                resolved = (
                    leader_motion <= 2
                    and follower_motion <= 2
                    and next_iv.consonance != "sharp_dissonance"
                )
            else:
                resolved = False
            if not resolved:
                unresolved += 1
        elif consonance == "mild_dissonance":
            mild_count += 1

        annotations.append(DissonanceAnnotation(
            beat_index=i,
            leader_midi=leader_notes[i],
            follower_midi=follower_notes[i],
            interval=iv,
            consonance=consonance,
            resolved=resolved,
        ))

    rate = 1.0 if sharp_count == 0 else float(sharp_count - unresolved) / sharp_count

    return DissonanceReport(
        annotations=tuple(annotations),
        sharp_dissonance_count=sharp_count,
        mild_dissonance_count=mild_count,
        unresolved_count=unresolved,
        resolution_rate=rate,
    )


def verify_resolution_sequence(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
) -> bool:
    """Return True only if every sharp dissonance in the sequence resolves properly."""
    report = analyze_dissonance(leader_notes, follower_notes)
    return report.unresolved_count == 0


def resolution_completeness_score(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
) -> float:
    """Return 0.0-1.0 measuring the proportion of resolved sharp dissonances."""
    report = analyze_dissonance(leader_notes, follower_notes)
    return report.resolution_rate


def weighted_voice_leading_smoothness(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
    *,
    dissonance_penalty: float = 2.0,
) -> float:
    """Voice-leading smoothness with a penalty for unresolved sharp dissonances.

    Computes the base melodic motion average, then adds *dissonance_penalty*
    semitones per unresolved sharp dissonance.  Lower is smoother.
    """
    base = voice_leading_smoothness(leader_notes, follower_notes)
    report = analyze_dissonance(leader_notes, follower_notes)
    return base + dissonance_penalty * report.unresolved_count


# ---------------------------------------------------------------------------
# Depth-2 Pair Assessment (frac-0009)
# ---------------------------------------------------------------------------

def motion_profile(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
) -> MotionProfile:
    """Classify parallel, contrary, oblique, and static motion between voices."""
    pair_count = min(len(leader_notes), len(follower_notes))
    transitions = max(pair_count - 1, 0)
    if transitions == 0:
        return MotionProfile(
            transitions=0,
            parallel_count=0,
            contrary_count=0,
            oblique_count=0,
            static_count=0,
            dominant_motion="none",
            stepwise_rate=1.0,
        )

    counts: dict[MotionKind, int] = {
        "parallel": 0,
        "contrary": 0,
        "oblique": 0,
        "static": 0,
        "none": 0,
    }
    order: list[MotionKind] = []
    stepwise = 0

    for index in range(1, pair_count):
        leader_delta = leader_notes[index] - leader_notes[index - 1]
        follower_delta = follower_notes[index] - follower_notes[index - 1]
        if leader_delta == 0 and follower_delta == 0:
            kind: MotionKind = "static"
        elif leader_delta == 0 or follower_delta == 0:
            kind = "oblique"
        elif (leader_delta > 0 and follower_delta > 0) or (
            leader_delta < 0 and follower_delta < 0
        ):
            kind = "parallel"
        else:
            kind = "contrary"

        counts[kind] += 1
        order.append(kind)
        if abs(leader_delta) <= 3 and abs(follower_delta) <= 3:
            stepwise += 1

    strongest = max(counts[kind] for kind in ("parallel", "contrary", "oblique", "static"))
    dominant = next(kind for kind in order if counts[kind] == strongest)

    return MotionProfile(
        transitions=transitions,
        parallel_count=counts["parallel"],
        contrary_count=counts["contrary"],
        oblique_count=counts["oblique"],
        static_count=counts["static"],
        dominant_motion=dominant,
        stepwise_rate=float(stepwise) / transitions,
    )


def _preferred_interval_rate(
    rule: CounterpointRule,
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
) -> float:
    pair_count = min(len(leader_notes), len(follower_notes))
    if pair_count == 0:
        return 0.0

    preferred = set(rule.intervals.preferred_semitones)
    hits = 0
    for index in range(pair_count):
        if interval_between(leader_notes[index], follower_notes[index]).semitones in preferred:
            hits += 1
    return float(hits) / pair_count


def _leap_ok_rate(
    rule: CounterpointRule,
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
) -> float:
    pair_count = min(len(leader_notes), len(follower_notes))
    transitions = max(pair_count - 1, 0)
    if transitions == 0:
        return 1.0

    safe = 0
    for index in range(1, pair_count):
        leader_leap = abs(leader_notes[index] - leader_notes[index - 1])
        follower_leap = abs(follower_notes[index] - follower_notes[index - 1])
        if leader_leap <= rule.intervals.max_leap and follower_leap <= rule.intervals.max_leap:
            safe += 1
    return float(safe) / transitions


def _motion_match_rate(rule_id: str, motion: MotionProfile) -> float:
    if motion.transitions == 0:
        return 0.0
    if rule_id == "contrary":
        return float(motion.contrary_count) / motion.transitions
    if rule_id == "oblique":
        return float(motion.oblique_count) / motion.transitions
    if rule_id == "parallel":
        return float(motion.parallel_count) / motion.transitions
    if rule_id == "echo":
        return float(motion.parallel_count + motion.static_count) / motion.transitions
    if rule_id == "completion":
        return float(motion.oblique_count + motion.static_count) / motion.transitions
    if rule_id == "commentary":
        weighted = (
            motion.contrary_count * 0.4
            + motion.oblique_count * 0.4
            + motion.parallel_count * 0.2
        )
        return float(weighted) / motion.transitions
    return 0.0


def score_counterpoint_fit(
    relationship_id: str,
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
    *,
    leader_role: str,
    follower_role: str,
    phase: str,
) -> CounterpointFit:
    """Score how well one rule fits a concrete leader/follower note pair."""
    rule = resolve_rule(relationship_id)
    motion = motion_profile(leader_notes, follower_notes)
    dissonance = analyze_dissonance(leader_notes, follower_notes)
    preferred_rate = _preferred_interval_rate(rule, leader_notes, follower_notes)
    leap_rate = _leap_ok_rate(rule, leader_notes, follower_notes)
    match_rate = _motion_match_rate(rule.relationship_id, motion)
    voice_pair_ok = (
        leader_role in rule.voice_pair.leader_roles
        and follower_role in rule.voice_pair.follower_roles
    )
    phase_affinity = rule.arc_affinity.get(phase, 0.0)

    score = round(
        0.26 * match_rate
        + 0.20 * dissonance.resolution_rate
        + 0.18 * preferred_rate
        + 0.13 * phase_affinity
        + 0.13 * leap_rate
        + 0.05 * (1.0 if voice_pair_ok else 0.0),
        3,
    )
    passed = voice_pair_ok and dissonance.unresolved_count == 0 and score >= 0.65

    return CounterpointFit(
        rule_id=rule.relationship_id,
        label=rule.label,
        phase=phase,
        leader_role=leader_role,
        follower_role=follower_role,
        score=score,
        passed=passed,
        voice_pair_ok=voice_pair_ok,
        preferred_interval_rate=preferred_rate,
        leap_ok_rate=leap_rate,
        motion_match_rate=match_rate,
        motion=motion,
        dissonance=dissonance,
    )


def rank_counterpoint_rules(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
    *,
    leader_role: str,
    follower_role: str,
    phase: str,
) -> tuple[CounterpointFit, ...]:
    """Return rule-fit scores for a voice pair, highest score first."""
    candidates = rules_for_voice_pair(leader_role, follower_role) or _RULES
    fits = [
        score_counterpoint_fit(
            rule.relationship_id,
            leader_notes,
            follower_notes,
            leader_role=leader_role,
            follower_role=follower_role,
            phase=phase,
        )
        for rule in candidates
    ]
    return tuple(sorted(fits, key=lambda fit: (-fit.score, fit.rule_id)))


def recommend_counterpoint_rule(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
    *,
    leader_role: str,
    follower_role: str,
    phase: str,
) -> CounterpointFit:
    """Return the highest-scoring rule fit for a concrete voice pair."""
    return rank_counterpoint_rules(
        leader_notes,
        follower_notes,
        leader_role=leader_role,
        follower_role=follower_role,
        phase=phase,
    )[0]


def counterpoint_pair_summary(
    leader_notes: tuple[int, ...],
    follower_notes: tuple[int, ...],
    *,
    leader_role: str,
    follower_role: str,
    phase: str,
) -> dict[str, object]:
    """Return a stable diagnostic summary for a two-voice counterpoint pair."""
    fit = recommend_counterpoint_rule(
        leader_notes,
        follower_notes,
        leader_role=leader_role,
        follower_role=follower_role,
        phase=phase,
    )
    return {
        "recommended_rule": fit.rule_id,
        "label": fit.label,
        "phase": fit.phase,
        "leader_role": fit.leader_role,
        "follower_role": fit.follower_role,
        "score": fit.score,
        "passed": fit.passed,
        "dominant_motion": fit.motion.dominant_motion,
        "stepwise_rate": fit.motion.stepwise_rate,
        "preferred_interval_rate": fit.preferred_interval_rate,
        "resolution_rate": fit.dissonance.resolution_rate,
        "unresolved_dissonances": fit.dissonance.unresolved_count,
    }
