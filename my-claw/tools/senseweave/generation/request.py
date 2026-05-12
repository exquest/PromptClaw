"""Frozen ``GenerationRequest`` dataclass shared by composer, queue, and clients."""

from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass, field
from typing import Literal, get_args

import numpy as np


CLAP_CENTROID_DIM = 512
MIN_DURATION_SEC = 5.0
MAX_DURATION_SEC = 60.0

Backend = Literal["replicate", "modal", "local"]
Model = Literal["musicgen-medium", "stable-audio-open"]

_VALID_BACKENDS: frozenset[str] = frozenset(get_args(Backend))
_VALID_MODELS: frozenset[str] = frozenset(get_args(Model))


@dataclass(frozen=True)
class GenerationRequest:
    """Immutable description of a single audio-generation job."""

    prompt: str
    clap_centroid: np.ndarray = field(hash=False, compare=False)
    duration_sec: float
    seed: int
    bpm_target: float
    mode_name: str
    arc_phase: str
    backend: Backend = "replicate"
    model: Model = "musicgen-medium"

    def __post_init__(self) -> None:
        if not isinstance(self.clap_centroid, np.ndarray):
            raise TypeError(
                f"clap_centroid must be a numpy ndarray, got {type(self.clap_centroid).__name__}"
            )
        if self.clap_centroid.shape != (CLAP_CENTROID_DIM,):
            raise ValueError(
                f"clap_centroid must have shape ({CLAP_CENTROID_DIM},), "
                f"got {self.clap_centroid.shape}"
            )
        if self.clap_centroid.dtype != np.float32:
            raise TypeError(
                f"clap_centroid must have dtype float32, got {self.clap_centroid.dtype}"
            )
        if not MIN_DURATION_SEC <= float(self.duration_sec) <= MAX_DURATION_SEC:
            raise ValueError(
                f"duration_sec must be in [{MIN_DURATION_SEC}, {MAX_DURATION_SEC}], "
                f"got {self.duration_sec}"
            )
        if self.backend not in _VALID_BACKENDS:
            raise ValueError(
                f"backend must be one of {sorted(_VALID_BACKENDS)}, got {self.backend!r}"
            )
        if self.model not in _VALID_MODELS:
            raise ValueError(
                f"model must be one of {sorted(_VALID_MODELS)}, got {self.model!r}"
            )

    def hash(self) -> str:
        """Return the backend-independent content hash for generation caching."""
        digest = hashlib.sha256()

        def update_field(label: bytes, payload: bytes) -> None:
            digest.update(label)
            digest.update(struct.pack(">Q", len(payload)))
            digest.update(payload)

        digest.update(b"GenerationRequest:v1")
        update_field(b"prompt", self.prompt.encode("utf-8"))
        update_field(
            b"clap_centroid",
            self.clap_centroid.astype("<f4", copy=False).tobytes(order="C"),
        )
        update_field(b"duration_sec", struct.pack(">d", float(self.duration_sec)))
        update_field(b"seed", struct.pack(">q", int(self.seed)))
        update_field(b"model", self.model.encode("utf-8"))
        update_field(b"bpm_target", struct.pack(">d", float(self.bpm_target)))
        return digest.hexdigest()


__all__ = (
    "Backend",
    "CLAP_CENTROID_DIM",
    "GenerationRequest",
    "MAX_DURATION_SEC",
    "MIN_DURATION_SEC",
    "Model",
)
