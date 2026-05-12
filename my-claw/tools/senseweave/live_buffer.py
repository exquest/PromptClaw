"""Live buffer and sample bank archive abstractions for SenseWeave."""
import json
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

@dataclass
class LiveBuffer:
    """State representation of a continuous environmental audio buffer."""
    source_name: str
    capture_path: str
    freshness: float = 0.0
    rms: float = 0.0
    spectral_profile: dict[str, float] = field(default_factory=dict)
    transform_history: tuple[str, ...] = ()

    def refresh(
        self,
        freshness: float,
        rms: float,
        spectral_profile: dict[str, float],
        transform_history: tuple[str, ...],
    ) -> None:
        """Update the buffer state with recent sensory data."""
        self.freshness = freshness
        self.rms = rms
        self.spectral_profile = dict(spectral_profile)
        self.transform_history = tuple(transform_history)


class SampleBankArchive:
    """Manages the long-term retention of selected clips."""
    
    def __init__(self, archive_dir: Path | str):
        self.archive_dir = Path(archive_dir)
        self.archive_dir.mkdir(parents=True, exist_ok=True)

    def retain_clip(self, source_path: Path | str, source_name: str, metadata: dict[str, Any]) -> Path | None:
        """
        Copy a clip to the archive storage along with its metadata.
        
        Args:
            source_path: Path to the audio file to retain.
            source_name: The name of the SenseWeave source (e.g., 'room_mic').
            metadata: Associated metadata to persist alongside the file.
            
        Returns:
            The Path to the archived audio file, or None if the source file was missing.
        """
        source = Path(source_path)
        if not source.exists():
            return None

        # Create source-specific subdirectory
        source_dir = self.archive_dir / source_name
        source_dir.mkdir(parents=True, exist_ok=True)

        # Generate a unique name based on timestamp
        timestamp = int(time.time() * 1000)
        unique_id = f"{source_name}_{timestamp}"
        
        dest_audio = source_dir / f"{unique_id}{source.suffix}"
        dest_meta = source_dir / f"{unique_id}.json"

        # Copy audio file
        shutil.copy2(source, dest_audio)

        # Save metadata
        meta_to_save = dict(metadata)
        if "timestamp" not in meta_to_save:
            meta_to_save["timestamp"] = timestamp
            
        dest_meta.write_text(json.dumps(meta_to_save, indent=2))

        return dest_audio
