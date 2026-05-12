"""Runtime checks for archive_daemon path selection."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
TOOLS_DIR = ROOT / "my-claw" / "tools"


def test_archive_daemon_uses_env_archive_root_for_outputs(tmp_path: Path, monkeypatch) -> None:
    archive_root = tmp_path / "archive-storage"
    porch_dir = tmp_path / "camera" / "porch_eye_captures"
    side_dir = tmp_path / "camera" / "side_eye_captures"
    monkeypatch.setenv("CYPHERCLAW_ARCHIVE_RECORDINGS_DIR", str(archive_root / "archive"))
    monkeypatch.setenv("CYPHERCLAW_PORCH_CAPTURE_DIR", str(porch_dir))
    monkeypatch.setenv("CYPHERCLAW_SIDE_CAPTURE_DIR", str(side_dir))
    monkeypatch.syspath_prepend(str(TOOLS_DIR))

    spec = importlib.util.spec_from_file_location("archive_daemon_test", TOOLS_DIR / "archive_daemon.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules.pop("archive_daemon_test", None)
    spec.loader.exec_module(module)

    assert module.ARCHIVE_ROOT == archive_root / "archive"
    assert module.PORCH_CAPTURE_DIR == porch_dir
    assert module.SIDE_CAPTURE_DIR == side_dir
    assert module.MUSIC_DIR.exists()
    assert module.CAMERA_DIR.exists()
