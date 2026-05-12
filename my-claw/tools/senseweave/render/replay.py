"""Deterministic render replay from score events, seeds, and delta tracks."""
from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import fields
from pathlib import Path
from typing import Any

from cypherclaw.render.events import Event

from .pass_ import PerformedPart

DeltaTrack = str | Path | Sequence[Mapping[str, Any]] | Mapping[str, Any]

_EVENT_FIELDS = {field.name for field in fields(Event) if field.init}
_SCORE_FIELDS = Event.SCORE_LEVEL_FIELDS
_PERFORMANCE_FIELDS = _EVENT_FIELDS.difference(_SCORE_FIELDS)


def replay(
    score: Sequence[Event | Mapping[str, Any]] | Mapping[str, Any] | PerformedPart,
    seeds: Mapping[str, int] | None,
    delta_track: DeltaTrack,
) -> PerformedPart:
    """Replay a performed part from immutable score events and recorded deltas.

    The delta track may be a JSON path, a sequence of event-delta mappings, or a
    sidecar-like mapping with ``delta_track``/``events`` entries. Deltas are
    matched by ``event_id`` when present, otherwise by zero-based sequence index.
    Only performance-level fields are overlaid; score-level fields remain owned
    by *score*.
    """

    events = _score_events(score)
    deltas = _load_delta_track(delta_track)
    by_id, by_index = _index_deltas(deltas)

    replayed: list[Event] = []
    for index, event in enumerate(events):
        event_delta = _delta_for_event(event, index, by_id, by_index)
        replayed_event = _copy_event(event)
        if event_delta is not None:
            _apply_delta(replayed_event, event_delta)
        replayed_event.mark_rendered()
        replayed.append(replayed_event)

    return PerformedPart(
        score=replayed,
        applied_rules=_applied_rules(replayed),
        quantities={},
        metadata={str(key): str(value) for key, value in dict(seeds or {}).items()},
    )


def _score_events(
    score: Sequence[Event | Mapping[str, Any]] | Mapping[str, Any] | PerformedPart,
) -> list[Event]:
    raw_score = score.score if isinstance(score, PerformedPart) else score
    if isinstance(raw_score, Mapping):
        events = raw_score.get("events")
        if not isinstance(events, Sequence) or isinstance(events, (str, bytes)):
            raise TypeError("score mapping must include an events sequence")
        raw_score = events
    if not isinstance(raw_score, Sequence) or isinstance(raw_score, (str, bytes)):
        raise TypeError("score must be a sequence of Event objects or event mappings")
    return [_coerce_event(event) for event in raw_score]


def _coerce_event(event: Event | Mapping[str, Any]) -> Event:
    if isinstance(event, Event):
        return event
    if isinstance(event, Mapping):
        return Event.from_json_dict(dict(event))
    raise TypeError("score events must be Event objects or mappings")


def _copy_event(event: Event) -> Event:
    return Event.from_json_dict(event.to_json_dict())


def _load_delta_track(delta_track: DeltaTrack) -> list[Mapping[str, Any]]:
    if isinstance(delta_track, (str, Path)):
        loaded = json.loads(Path(delta_track).read_text(encoding="utf-8"))
        return _load_delta_track(loaded)
    if isinstance(delta_track, Mapping):
        for key in ("delta_track", "deltas", "events"):
            value = delta_track.get(key)
            if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
                return _load_delta_track(value)
        return [delta_track]
    if isinstance(delta_track, Sequence) and not isinstance(delta_track, (str, bytes)):
        entries: list[Mapping[str, Any]] = []
        for entry in delta_track:
            if not isinstance(entry, Mapping):
                raise TypeError("delta track entries must be mappings")
            entries.append(entry)
        return entries
    raise TypeError("delta_track must be a path, mapping, or sequence of mappings")


def _index_deltas(
    deltas: Sequence[Mapping[str, Any]],
) -> tuple[dict[str, Mapping[str, Any]], dict[int, Mapping[str, Any]]]:
    by_id: dict[str, Mapping[str, Any]] = {}
    by_index: dict[int, Mapping[str, Any]] = {}
    for index, delta in enumerate(deltas):
        event_id = delta.get("event_id")
        if event_id not in (None, ""):
            by_id[str(event_id)] = delta
        delta_index = delta.get("index", index)
        if isinstance(delta_index, int):
            by_index[delta_index] = delta
    return by_id, by_index


def _delta_for_event(
    event: Event,
    index: int,
    by_id: Mapping[str, Mapping[str, Any]],
    by_index: Mapping[int, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if event.event_id and event.event_id in by_id:
        return by_id[event.event_id]
    return by_index.get(index)


def _apply_delta(event: Event, delta: Mapping[str, Any]) -> None:
    for key, value in delta.items():
        if key not in _PERFORMANCE_FIELDS:
            continue
        if key == "metadata":
            if isinstance(value, Mapping):
                event.metadata.update({str(k): str(v) for k, v in value.items()})
            continue
        if key == "seed_path":
            setattr(event, key, tuple(int(seed) for seed in _as_sequence(value)))
            continue
        if key == "rule_stack":
            setattr(event, key, [str(rule) for rule in _as_sequence(value)])
            continue
        setattr(event, key, value)


def _as_sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, str):
        loaded = json.loads(value)
        if isinstance(loaded, Sequence) and not isinstance(loaded, (str, bytes)):
            return loaded
        return [loaded]
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return value
    return [value]


def _applied_rules(events: Sequence[Event]) -> tuple[str, ...]:
    rules: list[str] = []
    seen: set[str] = set()
    for event in events:
        for rule in event.rule_stack:
            if rule not in seen:
                seen.add(rule)
                rules.append(rule)
    return tuple(rules)
