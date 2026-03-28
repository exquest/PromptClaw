"""Self-graduating enforcement mode promotion for the Coherence Engine."""

from __future__ import annotations

from dataclasses import dataclass

from .models import CoherenceConfig, EnforcementMode


@dataclass
class GraduationStats:
    """Tracks observation statistics used to evaluate mode promotions."""

    total_observations: int = 0
    true_positives: int = 0  # violation detected AND confirmed (retry fixed it)
    false_positives: int = 0  # violation detected BUT was wrong (user overrode)
    runs_in_current_mode: int = 0

    @property
    def confidence(self) -> float:
        if self.total_observations == 0:
            return 0.0
        return self.true_positives / self.total_observations

    @property
    def false_positive_rate(self) -> float:
        if self.total_observations == 0:
            return 1.0  # Unknown = assume bad
        return self.false_positives / self.total_observations


class GraduationManager:
    """Evaluates whether the enforcement mode should be promoted."""

    MIN_OBSERVATIONS_FOR_SOFT = 20
    MIN_RUNS_FOR_FULL = 10

    def __init__(self, config: CoherenceConfig) -> None:
        self.config = config
        self.current_mode: EnforcementMode = config.mode
        self.stats = GraduationStats()

    def record_observation(self, was_true_positive: bool) -> None:
        """Record whether a detected violation was a true or false positive."""
        self.stats.total_observations += 1
        if was_true_positive:
            self.stats.true_positives += 1
        else:
            self.stats.false_positives += 1

    def increment_run(self) -> None:
        """Increment the run counter for the current enforcement mode."""
        self.stats.runs_in_current_mode += 1

    def evaluate_promotion(self) -> EnforcementMode:
        """Evaluate and possibly promote the current enforcement mode.

        Promotion rules:
        - MONITOR -> SOFT: confidence > threshold AND total_observations >= MIN_OBSERVATIONS_FOR_SOFT
        - SOFT -> FULL: false_positive_rate < threshold AND runs_in_current_mode >= MIN_RUNS_FOR_FULL
        - FULL -> FULL: no auto-promotion beyond full
        - auto_graduate=False prevents all promotions

        Never auto-demotes. Returns the (possibly updated) mode.
        """
        if not self.config.auto_graduate:
            return self.current_mode

        if self.current_mode == EnforcementMode.MONITOR:
            if (
                self.stats.total_observations >= self.MIN_OBSERVATIONS_FOR_SOFT
                and self.stats.confidence > self.config.graduation_confidence_threshold
            ):
                self.current_mode = EnforcementMode.SOFT
                self.stats.runs_in_current_mode = 0

        elif self.current_mode == EnforcementMode.SOFT:
            if (
                self.stats.runs_in_current_mode >= self.MIN_RUNS_FOR_FULL
                and self.stats.false_positive_rate < self.config.graduation_false_positive_threshold
            ):
                self.current_mode = EnforcementMode.FULL
                self.stats.runs_in_current_mode = 0

        # FULL: no further promotion possible

        return self.current_mode
