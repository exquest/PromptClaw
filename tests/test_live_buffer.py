import json
import os
import sys


sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.live_buffer import LiveBuffer, SampleBankArchive

def test_live_buffer_refresh():
    """Verify buffer refresh exposes source name, capture path, freshness, RMS, spectral profile, and transform history."""
    buffer = LiveBuffer(source_name="room_mic", capture_path="/tmp/room_mic.wav")
    
    assert buffer.source_name == "room_mic"
    assert buffer.capture_path == "/tmp/room_mic.wav"
    assert buffer.freshness == 0.0
    assert buffer.rms == 0.0
    assert buffer.spectral_profile == {}
    assert buffer.transform_history == ()
    
    # Refresh
    buffer.refresh(
        freshness=12.5,
        rms=0.45,
        spectral_profile={"centroid": 1200.0, "rolloff": 3400.0},
        transform_history=("stretch", "pitch_window")
    )
    
    assert buffer.freshness == 12.5
    assert buffer.rms == 0.45
    assert buffer.spectral_profile == {"centroid": 1200.0, "rolloff": 3400.0}
    assert buffer.transform_history == ("stretch", "pitch_window")

def test_sample_bank_archive_path_selection(tmp_path):
    """Verify sample banks can retain selected clips on archive storage with metadata."""
    archive_dir = tmp_path / "sample_archive"
    archive = SampleBankArchive(archive_dir=archive_dir)
    
    # Create a dummy source file
    source_file = tmp_path / "source.wav"
    source_file.write_bytes(b"dummy wav content")
    
    metadata = {
        "source_name": "contact_mic",
        "rms": 0.8,
        "spectral_profile": {"centroid": 500.0},
        "tags": ["impulse", "body"]
    }
    
    archived_path = archive.retain_clip(
        source_path=source_file,
        source_name="contact_mic",
        metadata=metadata
    )
    
    assert archived_path is not None
    assert archived_path.exists()
    assert archived_path.parent == archive_dir / "contact_mic"
    assert archived_path.suffix == ".wav"
    
    # Verify metadata is stored
    meta_path = archived_path.with_suffix(".json")
    assert meta_path.exists()
    
    saved_meta = json.loads(meta_path.read_text())
    assert saved_meta["source_name"] == "contact_mic"
    assert saved_meta["rms"] == 0.8
    assert saved_meta["tags"] == ["impulse", "body"]
    assert "timestamp" in saved_meta

def test_sample_bank_archive_missing_file(tmp_path):
    """Verify archive fails gracefully when source file is missing."""
    archive = SampleBankArchive(archive_dir=tmp_path / "archive")
    
    archived_path = archive.retain_clip(
        source_path=tmp_path / "nonexistent.wav",
        source_name="room_mic",
        metadata={}
    )
    
    assert archived_path is None
