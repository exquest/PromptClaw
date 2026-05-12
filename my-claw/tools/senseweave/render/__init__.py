"""Structured expression rendering helpers for SenseWeave."""
from __future__ import annotations

from .ablation import (
    AblationCase,
    AblationResult,
    AblationSuite,
    ablate,
    build_ablation_cases,
    filter_active_rules,
    rule_identifiers,
    run_ablation_suite,
    summarize_ablation_suite,
)
from .audio_sidecar import (
    audio_delta_track_path,
    audio_metadata_sidecar_path,
    read_audio_metadata_sidecar,
    write_audio_metadata_sidecar,
)
from .audio_novelty import (
    AudioNoveltyAnalysis,
    NoveltyAlignment,
    NoveltyPeakMatch,
    ProxyAudioRender,
    align_novelty_peaks,
    check_audio_symbolic_novelty_alignment,
    extract_audio_novelty,
    render_proxy_audio,
    symbolic_novelty_peak_times,
)
from .export import ExportResult, export_audio
from .debugger import (
    AblationRun,
    LocalizationReport,
    ProblemRegion,
    RuleImpact,
    localize_rule_impacts,
    run_debugger,
)
from .diff import NoteDelta, PhraseDelta, ScoreDelta, diff_scores
from .pass_ import RULE_ORDER, PerformedPart, RenderPass, RenderRule
from .replay import replay
from .rules import (
    AgogicAccentRule,
    DurationContrastRule,
    METRIC_ACCENT_4_4,
    MetricAccentRule,
    apply_agogic_accent,
    apply_duration_contrast,
    apply_metric_accent,
    metric_accent_table,
)

__all__ = [
    "AblationCase",
    "AblationResult",
    "AblationRun",
    "AblationSuite",
    "AudioNoveltyAnalysis",
    "AgogicAccentRule",
    "DurationContrastRule",
    "ExportResult",
    "LocalizationReport",
    "METRIC_ACCENT_4_4",
    "MetricAccentRule",
    "NoveltyAlignment",
    "NoveltyPeakMatch",
    "NoteDelta",
    "RULE_ORDER",
    "PerformedPart",
    "PhraseDelta",
    "ProblemRegion",
    "ProxyAudioRender",
    "RenderPass",
    "RenderRule",
    "RuleImpact",
    "ScoreDelta",
    "ablate",
    "align_novelty_peaks",
    "audio_delta_track_path",
    "audio_metadata_sidecar_path",
    "apply_agogic_accent",
    "apply_duration_contrast",
    "apply_metric_accent",
    "build_ablation_cases",
    "check_audio_symbolic_novelty_alignment",
    "diff_scores",
    "export_audio",
    "extract_audio_novelty",
    "filter_active_rules",
    "localize_rule_impacts",
    "metric_accent_table",
    "read_audio_metadata_sidecar",
    "replay",
    "render_proxy_audio",
    "rule_identifiers",
    "run_debugger",
    "run_ablation_suite",
    "summarize_ablation_suite",
    "symbolic_novelty_peak_times",
    "write_audio_metadata_sidecar",
]
