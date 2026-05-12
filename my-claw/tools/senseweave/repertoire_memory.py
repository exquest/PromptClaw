"""Long-term song memory for CypherClaw repertoire hints."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

_LEGACY_HOOK_FIXES = {
    "answer the again": "keep the room open",
    "open the room open": "keep the room open",
    "carry the room wide": "keep the room open",
    "hold the room wide": "keep the room open",
    "carry the line wide": "keep the line open",
    "hold the line wide": "keep the line open",
}


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))


def _sanitize_hook_text(text: str) -> str:
    cleaned = " ".join(str(text).split()).strip()
    if not cleaned:
        return ""
    return _LEGACY_HOOK_FIXES.get(cleaned.lower(), cleaned)


def _feedback_scores_for_metrics(ear_metrics: dict[str, float]) -> dict[str, float]:
    try:
        from .ear_engine import feedback_scores

        return feedback_scores(ear_metrics)
    except (ImportError, ValueError, TypeError):
        return {}


class RepertoireMemory:
    def __init__(self, path: str = "/home/user/cypherclaw-data/state/repertoire_memory.json"):
        self.path = Path(path)

    def _load(self) -> dict[str, Any]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text())
                songs = list(data.get("songs", []))
                normalized: list[dict[str, Any]] = []
                changed = False
                for song in songs:
                    repaired = dict(song)
                    repaired_hook = _sanitize_hook_text(str(repaired.get("hook_text", "")))
                    if repaired_hook != repaired.get("hook_text", ""):
                        repaired["hook_text"] = repaired_hook
                        changed = True
                    normalized.append(repaired)
                if changed:
                    data["songs"] = normalized
                    self._save(data)
                return data
        except (OSError, json.JSONDecodeError):
            pass
        return {"songs": []}

    def _save(self, data: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            os.replace(str(tmp), str(self.path))
        except OSError:
            pass

    def store_song(
        self,
        *,
        title: str,
        family: str,
        progression_profile: str,
        cadence_state: str,
        key: str,
        hook_text: str,
        hook_class: str,
        practice_block: str,
        ear_metrics: dict[str, float],
        patch_name: str = "",
        form_class: str = "",
        composition_mode: str = "",
        ending_family: str = "",
        score_tree: object | None = None,
        audio_render_ref: str = "",
        source_samples: list[str] | None = None,
    ) -> None:
        data = self._load()
        songs = list(data.get("songs", []))
        score_tree_summary: dict[str, Any] = {}
        if score_tree is not None:
            piece_id = getattr(score_tree, "piece_id", "") or ""
            planned_duration_s = float(getattr(score_tree, "planned_duration_s", 0.0) or 0.0)
            motifs = getattr(score_tree, "motifs", []) or []
            motif_ids = [
                str(getattr(motif, "motif_id", ""))
                for motif in motifs
                if getattr(motif, "motif_id", "")
            ]
            sections = getattr(score_tree, "sections", []) or []
            section_functions = [
                str(getattr(section, "function", ""))
                for section in sections
                if getattr(section, "function", "")
            ]
            narrative_map = getattr(score_tree, "narrative_map", {}) or {}
            motif_contours = [
                list(getattr(motif, "contour", ()))
                for motif in motifs
                if getattr(motif, "contour", ())
            ]
            score_tree_summary = {
                "piece_id": piece_id,
                "form_class": form_class or getattr(getattr(score_tree, "commission", None), "form_class", ""),
                "composition_mode": composition_mode or getattr(getattr(score_tree, "commission", None), "composition_mode", ""),
                "ending_family": ending_family or getattr(score_tree, "ending_family", ""),
                "duration_s": planned_duration_s,
                "motif_ids": motif_ids,
                "motif_contours": motif_contours,
                "section_functions": section_functions,
                "narrative_beats": list(narrative_map.values()),
            }
        feedback_scores = _feedback_scores_for_metrics(dict(ear_metrics))
        songs.append(
            {
                "title": title,
                "family": family,
                "progression_profile": progression_profile,
                "cadence_state": cadence_state,
                "key": key,
                "hook_text": _sanitize_hook_text(hook_text),
                "hook_class": hook_class,
                "practice_block": practice_block,
                "patch_name": patch_name,
                "form_class": form_class,
                "composition_mode": composition_mode,
                "ending_family": ending_family,
                **({"score_tree_summary": score_tree_summary} if score_tree_summary else {}),
                "ear_metrics": dict(ear_metrics),
                "feedback_scores": feedback_scores,
                **({"audio_render_ref": audio_render_ref} if audio_render_ref else {}),
                **({"source_samples": list(source_samples)} if source_samples else {}),
                "stored_at": time.time(),
            }
        )
        data["songs"] = songs[-200:]
        self._save(data)

    def all_songs(self) -> list[dict[str, Any]]:
        songs = self._load().get("songs", [])
        return [dict(song) for song in songs]

    def recall_hint(self, *, family: str, cadence_state: str) -> dict[str, Any] | None:
        songs = self._load().get("songs", [])
        matches = [
            song for song in songs
            if song.get("family") == family and song.get("cadence_state") == cadence_state
        ]
        if not matches:
            return None
        matches.sort(
            key=lambda song: (
                float(song.get("ear_metrics", {}).get("hook_clarity", 0.0)),
                float(song.get("stored_at", 0.0)),
            ),
            reverse=True,
        )
        return matches[0]

    def influence_for_song(
        self,
        *,
        family: str,
        cadence_state: str,
        progression_profile: str,
        song_num: int,
    ) -> dict[str, Any] | None:
        hint = self.recall_hint(family=family, cadence_state=cadence_state)
        if hint is None:
            return None
        mode = "answer" if song_num % 2 == 0 else "recall"
        ear_metrics = dict(hint.get("ear_metrics", {}))
        feedback_scores = dict(hint.get("feedback_scores", {}) or _feedback_scores_for_metrics(ear_metrics))
        hook_clarity = float(ear_metrics.get("hook_clarity", 0.0) or 0.0)
        cadence_strength = float(ear_metrics.get("cadence_strength", 0.0) or 0.0)
        static_score = float(feedback_scores.get("static_score", 0.0) or 0.0)
        harsh_score = float(feedback_scores.get("harsh_score", 0.0) or 0.0)
        muddy_score = float(feedback_scores.get("muddy_score", 0.0) or 0.0)
        underdeveloped_score = float(feedback_scores.get("underdeveloped_score", 0.0) or 0.0)
        if cadence_strength >= 0.85:
            form_variant = "afterglow"
        elif hook_clarity >= 0.85:
            form_variant = "bridge"
        elif underdeveloped_score >= 0.55:
            form_variant = "bridge"
        elif song_num % 3 == 0:
            form_variant = "concise"
        else:
            form_variant = "base"
        density_bias = _clamp(
            ((hook_clarity + cadence_strength) - 1.25) * 0.3
            + static_score * 0.12
            - harsh_score * 0.06
            - muddy_score * 0.03,
            -0.2,
            0.2,
        )
        if form_variant == "afterglow":
            payoff_scene = "Afterglow"
        elif form_variant == "bridge":
            payoff_scene = "Bridge"
        elif cadence_strength >= 0.8:
            payoff_scene = "Resolution"
        elif mode == "answer":
            payoff_scene = "Recap"
        else:
            payoff_scene = "Theme"
        if harsh_score >= 0.6 and payoff_scene == "Theme":
            payoff_scene = "Release"
        correction_tags = [
            name
            for name, score in (
                ("static", static_score),
                ("harsh", harsh_score),
                ("muddy", muddy_score),
                ("underdeveloped", underdeveloped_score),
            )
            if score >= 0.55
        ]
        payoff_bias = _clamp(
            (hook_clarity * 0.12)
            + (cadence_strength * 0.08)
            + underdeveloped_score * 0.06
            + static_score * 0.03
            - harsh_score * 0.04,
            0.0,
            0.2,
        )
        return {
            "source_title": hint.get("title", ""),
            "hook_text": hint.get("hook_text", ""),
            "hook_class": hint.get("hook_class", hint.get("hook_class", "")),
            "progression_profile": hint.get("progression_profile", progression_profile),
            "mode": mode,
            "current_progression_profile": progression_profile,
            "form_variant": form_variant,
            "density_bias": round(density_bias, 3),
            "payoff_scene": payoff_scene,
            "payoff_bias": round(payoff_bias, 3),
            "feedback_scores": feedback_scores,
            "correction_tags": correction_tags,
        }

    def promoted_entries(self) -> list[dict[str, Any]]:
        songs = self._load().get("songs", [])
        promoted = [
            song for song in songs
            if float(song.get("ear_metrics", {}).get("hook_clarity", 0.0)) >= 0.8
            or float(song.get("ear_metrics", {}).get("cadence_strength", 0.0)) >= 0.85
        ]
        promoted.sort(
            key=lambda song: (
                float(song.get("ear_metrics", {}).get("hook_clarity", 0.0))
                + float(song.get("ear_metrics", {}).get("cadence_strength", 0.0))
            ),
            reverse=True,
        )
        return promoted

    def structural_recall(
        self,
        *,
        family: str,
        cadence_state: str,
        form_class: str = "",
        composition_mode: str = "",
    ) -> dict[str, Any] | None:
        songs = self._load().get("songs", [])
        matches = [
            song for song in songs
            if song.get("family") == family
            and song.get("cadence_state") == cadence_state
            and (not form_class or song.get("form_class") == form_class)
            and (not composition_mode or song.get("composition_mode") == composition_mode)
            and song.get("score_tree_summary")
        ]
        if not matches:
            return None
        matches.sort(key=lambda song: float(song.get("stored_at", 0.0)), reverse=True)
        return dict(matches[0].get("score_tree_summary", {}))

    def recall_motif_shape(
        self,
        *,
        family: str,
        cadence_state: str,
        motif_index: int = 0,
    ) -> tuple[int, ...] | None:
        """Return a stored motif contour for shape-based recall.

        The contour comes from the most recent matching score_tree_summary.
        Returns ``None`` when no contour is available.
        """
        summary = self.structural_recall(family=family, cadence_state=cadence_state)
        if summary is None:
            return None
        contours = summary.get("motif_contours", [])
        if motif_index < len(contours):
            raw = contours[motif_index]
            if isinstance(raw, (list, tuple)) and raw:
                return tuple(int(d) for d in raw)
        return None

    # ------------------------------------------------------------------
    # House repertoire promotion
    # ------------------------------------------------------------------

    def promote_to_house(
        self,
        *,
        archive_root: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        """Promote strong pieces into the house repertoire.

        Pieces qualify when ``hook_clarity >= 0.8`` or
        ``cadence_strength >= 0.85``.  Exact duplicate titles or
        hook texts are skipped when an alternative already exists in
        the house file.

        The house repertoire is stored under *archive_root* when
        provided, falling back to the parent of ``self.path``.

        Returns the list of newly promoted entries.
        """
        candidates = self.promoted_entries()
        if not candidates:
            return []

        house_path = _resolve_house_path(self.path, archive_root)
        existing = _load_house(house_path)

        existing_titles: set[str] = {
            e.get("title", "").lower() for e in existing
        }
        existing_hooks: set[str] = {
            e.get("hook_text", "").lower() for e in existing
        }

        newly_promoted: list[dict[str, Any]] = []
        for song in candidates:
            title_lower = song.get("title", "").lower()
            hook_lower = song.get("hook_text", "").lower()
            # Skip exact duplicate title when alternatives exist
            if title_lower in existing_titles and len(candidates) > 1:
                continue
            # Skip exact duplicate hook text when alternatives exist
            if hook_lower and hook_lower in existing_hooks and len(candidates) > 1:
                continue
            if title_lower in existing_titles:
                continue
            entry = {
                "title": song.get("title", ""),
                "family": song.get("family", ""),
                "key": song.get("key", ""),
                "hook_text": song.get("hook_text", ""),
                "hook_class": song.get("hook_class", ""),
                "form_class": song.get("form_class", ""),
                "ending_family": song.get("ending_family", ""),
                "ear_metrics": dict(song.get("ear_metrics", {})),
                "score_tree_summary": dict(song.get("score_tree_summary", {})),
                **({"audio_render_ref": song["audio_render_ref"]} if song.get("audio_render_ref") else {}),
                **({"source_samples": list(song["source_samples"])} if song.get("source_samples") else {}),
                "promoted_at": time.time(),
            }
            existing.append(entry)
            existing_titles.add(title_lower)
            existing_hooks.add(hook_lower)
            newly_promoted.append(entry)

        if newly_promoted:
            _save_house(house_path, existing)
        return newly_promoted

    def house_repertoire(
        self,
        *,
        archive_root: str | Path | None = None,
    ) -> list[dict[str, Any]]:
        """Return all entries in the house repertoire."""
        house_path = _resolve_house_path(self.path, archive_root)
        return _load_house(house_path)


def _resolve_house_path(
    repertoire_path: Path,
    archive_root: str | Path | None,
) -> Path:
    """Resolve the house repertoire JSON path.

    Uses *archive_root* when provided (the 10 TB volume), otherwise
    stores alongside the regular repertoire file.
    """
    if archive_root is not None:
        root = Path(archive_root)
    else:
        root = repertoire_path.parent
    return root / "house_repertoire.json"


def _load_house(path: Path) -> list[dict[str, Any]]:
    try:
        if path.exists():
            return list(json.loads(path.read_text()))
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    return []


def _save_house(path: Path, entries: list[dict[str, Any]]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(entries, indent=2))
        os.replace(str(tmp), str(path))
    except OSError:
        pass
