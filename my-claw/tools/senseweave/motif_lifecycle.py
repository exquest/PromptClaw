"""Leitmotif lifecycle management for CypherClaw composition.

Motifs move through seven states across a piece and across repertoire:
  statement -> variation -> contrast -> recall -> answer -> liquidation -> residue

Each transition applies a deterministic transformation to contour, rhythm,
and degree material so the motif evolves without exact self-copying.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from .score_tree import MOTIF_LIFECYCLE_STATES, MotifNode, motif_lifecycle_band


# -- valid transitions --------------------------------------------------------

_TRANSITIONS: dict[str, tuple[str, ...]] = {
    "statement": ("variation", "contrast", "answer"),
    "variation": ("contrast", "recall", "answer", "liquidation"),
    "contrast": ("recall", "answer", "liquidation"),
    "recall": ("variation", "answer", "liquidation"),
    "answer": ("liquidation", "residue"),
    "liquidation": ("residue",),
    "residue": (),
}


def valid_next_states(current: str) -> tuple[str, ...]:
    """Return states reachable from *current*."""
    return _TRANSITIONS.get(current, ())


# -- transformations ----------------------------------------------------------


def _clamp_degree(d: int) -> int:
    return max(1, min(8, d))


def transform_variation(motif: MotifNode) -> MotifNode:
    """Vary contour by shifting inner degrees +/-1 and shuffling rhythm."""
    contour = list(motif.contour)
    for i in range(1, len(contour) - 1):
        contour[i] = _clamp_degree(contour[i] + (1 if i % 2 == 0 else -1))
    rhythm = list(motif.rhythm)
    if len(rhythm) >= 2:
        rhythm[0], rhythm[-1] = rhythm[-1], rhythm[0]
    return replace(
        motif,
        motif_id=_derive_id(motif.motif_id, "variation"),
        contour=tuple(contour),
        rhythm=tuple(rhythm),
        lifecycle_state="variation",
    )


def transform_contrast(motif: MotifNode) -> MotifNode:
    """Invert contour and reverse rhythm for contrast material."""
    max_deg = max(motif.contour) if motif.contour else 8
    inverted = tuple(_clamp_degree(max_deg + 1 - d) for d in motif.contour)
    return replace(
        motif,
        motif_id=_derive_id(motif.motif_id, "contrast"),
        contour=inverted,
        rhythm=tuple(reversed(motif.rhythm)),
        anchor_degrees=motif.answer_degrees or motif.anchor_degrees,
        answer_degrees=motif.anchor_degrees,
        lifecycle_state="contrast",
    )


def transform_recall(motif: MotifNode, *, shape: Sequence[int] | None = None) -> MotifNode:
    """Recall the motif shape from repertoire without exact self-copying.

    If *shape* is given it is used as a starting contour; otherwise the
    original contour is used.  Either way a slight perturbation is applied
    so the recall is never identical to the statement.
    """
    base = list(shape) if shape else list(motif.contour)
    # perturb: shift each degree toward center by 1
    center = sum(base) / len(base) if base else 4
    recalled = []
    for d in base:
        if d > center:
            recalled.append(_clamp_degree(d - 1))
        elif d < center:
            recalled.append(_clamp_degree(d + 1))
        else:
            recalled.append(d)
    return replace(
        motif,
        motif_id=_derive_id(motif.motif_id, "recall"),
        contour=tuple(recalled),
        lifecycle_state="recall",
    )


def transform_answer(motif: MotifNode) -> MotifNode:
    """Produce the answer form: swap anchor/answer degrees, resolve last to 1."""
    answer_contour = list(motif.contour)
    if answer_contour:
        answer_contour[-1] = 1 if answer_contour[-1] >= 4 else 3
    return replace(
        motif,
        motif_id=_derive_id(motif.motif_id, "answer"),
        contour=tuple(answer_contour),
        anchor_degrees=motif.answer_degrees or motif.anchor_degrees,
        answer_degrees=motif.anchor_degrees,
        lifecycle_state="answer",
    )


def transform_liquidation(motif: MotifNode) -> MotifNode:
    """Fragment the motif: keep only the first half of contour/rhythm."""
    half = max(1, len(motif.contour) // 2)
    return replace(
        motif,
        motif_id=_derive_id(motif.motif_id, "liquidation"),
        contour=motif.contour[:half],
        rhythm=motif.rhythm[:half],
        lifecycle_state="liquidation",
    )


def transform_residue(motif: MotifNode) -> MotifNode:
    """Reduce to the opening interval -- the melodic residue."""
    return replace(
        motif,
        motif_id=_derive_id(motif.motif_id, "residue"),
        contour=motif.contour[:2] if len(motif.contour) >= 2 else motif.contour[:1],
        rhythm=motif.rhythm[:1],
        lifecycle_state="residue",
    )


_TRANSFORM_FN: dict[str, Callable[[MotifNode], MotifNode]] = {
    "variation": transform_variation,
    "contrast": transform_contrast,
    "recall": transform_recall,
    "answer": transform_answer,
    "liquidation": transform_liquidation,
    "residue": transform_residue,
}


def advance(motif: MotifNode, target_state: str) -> MotifNode:
    """Advance *motif* to *target_state*, applying the matching transformation.

    Raises ``ValueError`` if the transition is not permitted.
    """
    if target_state not in MOTIF_LIFECYCLE_STATES:
        raise ValueError(f"unknown lifecycle state: {target_state!r}")
    allowed = valid_next_states(motif.lifecycle_state)
    if target_state not in allowed:
        raise ValueError(
            f"cannot transition from {motif.lifecycle_state!r} to {target_state!r}; "
            f"valid targets: {allowed}"
        )
    fn = _TRANSFORM_FN[target_state]
    return fn(motif)


# -- lifecycle diagnostics ----------------------------------------------------


@dataclass(frozen=True)
class MotifLifecycleStep:
    """Resolved diagnostics for one motif snapshot in a lifecycle path."""

    motif_id: str
    state: str
    state_index: int
    state_band: str
    contour: tuple[int, ...]
    rhythm: tuple[float, ...]
    contour_span: int
    rhythm_total: float
    material_units: int


@dataclass(frozen=True)
class MotifLifecycleReport:
    """Operator-readable summary for a motif lifecycle path."""

    origin_motif_id: str
    current_motif_id: str
    current_state: str
    terminal_state: str
    terminal: bool
    history: tuple[str, ...]
    next_states: tuple[str, ...]
    step_count: int
    state_counts: dict[str, int]
    contour_span_delta: int
    rhythm_total_delta: float
    material_ratio: float
    steps: tuple[MotifLifecycleStep, ...]


def lifecycle_state_index(state: str) -> int:
    """Return the canonical zero-based lifecycle index, or -1 if unknown."""
    for index, candidate in enumerate(MOTIF_LIFECYCLE_STATES):
        if candidate == state:
            return index
    return -1


def build_lifecycle_step(motif: MotifNode) -> MotifLifecycleStep:
    """Build material diagnostics for one motif lifecycle snapshot."""
    contour = tuple(motif.contour)
    rhythm = tuple(motif.rhythm)
    contour_span = max(contour) - min(contour) if contour else 0
    rhythm_total = float(sum(rhythm))
    return MotifLifecycleStep(
        motif_id=motif.motif_id,
        state=motif.lifecycle_state,
        state_index=lifecycle_state_index(motif.lifecycle_state),
        state_band=motif_lifecycle_band(motif.lifecycle_state),
        contour=contour,
        rhythm=rhythm,
        contour_span=contour_span,
        rhythm_total=rhythm_total,
        material_units=max(len(contour), len(rhythm)),
    )


def canonical_lifecycle_path(motif: MotifNode) -> tuple[MotifNode, ...]:
    """Advance *motif* through the remaining canonical lifecycle states."""
    state_index = lifecycle_state_index(motif.lifecycle_state)
    if state_index < 0:
        raise ValueError(f"unknown lifecycle state: {motif.lifecycle_state!r}")

    path = [motif]
    current = motif
    for target_state in MOTIF_LIFECYCLE_STATES[state_index + 1:]:
        current = advance(current, target_state)
        path.append(current)
    return tuple(path)


def build_lifecycle_report(motifs: Sequence[MotifNode]) -> MotifLifecycleReport:
    """Summarize a concrete motif lifecycle path."""
    if not motifs:
        raise ValueError("motif lifecycle report requires at least one motif")

    steps = tuple(build_lifecycle_step(motif) for motif in motifs)
    origin = steps[0]
    current = steps[-1]

    state_counts: dict[str, int] = {state: 0 for state in MOTIF_LIFECYCLE_STATES}
    for step in steps:
        if step.state in state_counts:
            state_counts[step.state] += 1

    next_states = valid_next_states(current.state)
    material_ratio = (
        current.material_units / origin.material_units
        if origin.material_units
        else 0.0
    )
    return MotifLifecycleReport(
        origin_motif_id=origin.motif_id,
        current_motif_id=current.motif_id,
        current_state=current.state,
        terminal_state=MOTIF_LIFECYCLE_STATES[-1],
        terminal=not bool(next_states),
        history=tuple(step.state for step in steps),
        next_states=next_states,
        step_count=len(steps),
        state_counts=state_counts,
        contour_span_delta=current.contour_span - origin.contour_span,
        rhythm_total_delta=current.rhythm_total - origin.rhythm_total,
        material_ratio=material_ratio,
        steps=steps,
    )


def summarize_lifecycle_report(report: MotifLifecycleReport) -> dict[str, Any]:
    """Return a JSON-safe lifecycle report summary."""
    steps: list[dict[str, Any]] = []
    for step in report.steps:
        steps.append(
            {
                "motif_id": step.motif_id,
                "state": step.state,
                "state_index": step.state_index,
                "state_band": step.state_band,
                "contour": list(step.contour),
                "rhythm": list(step.rhythm),
                "contour_span": step.contour_span,
                "rhythm_total": step.rhythm_total,
                "material_units": step.material_units,
            }
        )

    return {
        "origin_motif_id": report.origin_motif_id,
        "current_motif_id": report.current_motif_id,
        "current_state": report.current_state,
        "terminal_state": report.terminal_state,
        "terminal": report.terminal,
        "history": list(report.history),
        "next_states": list(report.next_states),
        "step_count": report.step_count,
        "state_counts": dict(report.state_counts),
        "contour_span_delta": report.contour_span_delta,
        "rhythm_total_delta": report.rhythm_total_delta,
        "material_ratio": report.material_ratio,
        "steps": steps,
    }


# -- leitmotif registry ------------------------------------------------------


@dataclass
class LeitmotifEntry:
    """Tracks a motif's identity and lifecycle across a piece or repertoire."""

    origin_motif: MotifNode
    current: MotifNode
    history: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.history:
            self.history = [self.origin_motif.lifecycle_state]


class MotifLifecycleManager:
    """Manages leitmotif entries for one piece or across repertoire."""

    def __init__(self) -> None:
        self._entries: dict[str, LeitmotifEntry] = {}

    def register(self, motif: MotifNode) -> LeitmotifEntry:
        entry = LeitmotifEntry(origin_motif=motif, current=motif)
        self._entries[motif.motif_id] = entry
        return entry

    def get(self, motif_id: str) -> LeitmotifEntry | None:
        return self._entries.get(motif_id)

    def advance(self, motif_id: str, target_state: str) -> MotifNode:
        """Advance the motif identified by *motif_id* to *target_state*."""
        entry = self._entries.get(motif_id)
        if entry is None:
            raise KeyError(f"motif {motif_id!r} not registered")
        new_motif = advance(entry.current, target_state)
        entry.current = new_motif
        entry.history.append(target_state)
        self._entries[new_motif.motif_id] = entry
        return new_motif

    @property
    def entries(self) -> dict[str, LeitmotifEntry]:
        return dict(self._entries)

    def recall_from_repertoire(
        self,
        motif_id: str,
        *,
        repertoire_shape: Sequence[int],
    ) -> MotifNode:
        """Recall *motif_id* using a shape from repertoire (never an exact copy)."""
        entry = self._entries.get(motif_id)
        if entry is None:
            raise KeyError(f"motif {motif_id!r} not registered")
        allowed = valid_next_states(entry.current.lifecycle_state)
        if "recall" not in allowed:
            raise ValueError(
                f"cannot recall from state {entry.current.lifecycle_state!r}"
            )
        new_motif = transform_recall(entry.current, shape=repertoire_shape)
        entry.current = new_motif
        entry.history.append("recall")
        self._entries[new_motif.motif_id] = entry
        return new_motif


# -- helpers ------------------------------------------------------------------


def _derive_id(base_id: str, suffix: str) -> str:
    payload = f"{base_id}|{suffix}"
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]


def recall_shape_from_summary(
    score_tree_summary: Mapping[str, Any],
    *,
    motif_index: int = 0,
) -> tuple[int, ...] | None:
    """Extract a motif contour from a stored repertoire score_tree_summary.

    Returns ``None`` when no contour data is available.
    """
    motifs = score_tree_summary.get("motif_contours", ())
    if motif_index < len(motifs):
        raw = motifs[motif_index]
        if isinstance(raw, (list, tuple)) and raw:
            return tuple(int(d) for d in raw)
    return None
