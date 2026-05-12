"""Tests for tracker-runtime correlation helpers in self_listener.py."""
from __future__ import annotations

import json
import os
import sys
import subprocess
import struct
import wave

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))

import self_listener


class TestReadTrackerRuntimeState:
    def test_reads_recent_tracker_state(self, tmp_path, monkeypatch):
        path = tmp_path / "tracker_runtime_state.json"
        path.write_text(
            json.dumps(
                {
                    "timestamp": 100.0,
                    "scene_name": "Theme",
                    "row": 8,
                    "active_lanes": ["melody", "foundation"],
                    "scene_metadata": {
                        "payoff_focus": "primary",
                        "section_function": "arrival",
                    },
                }
            )
        )
        monkeypatch.setattr(self_listener, "TRACKER_RUNTIME_STATE", str(path))

        state = self_listener.read_tracker_runtime_state(now=105.0, window_seconds=10)
        assert state["scene_name"] == "Theme"
        assert state["row"] == 8
        assert state["scene_metadata"]["payoff_focus"] == "primary"

    def test_ignores_stale_tracker_state(self, tmp_path, monkeypatch):
        path = tmp_path / "tracker_runtime_state.json"
        path.write_text(json.dumps({"timestamp": 50.0, "scene_name": "Old"}))
        monkeypatch.setattr(self_listener, "TRACKER_RUNTIME_STATE", str(path))

        state = self_listener.read_tracker_runtime_state(now=100.0, window_seconds=10)
        assert state == {}


class TestGlyphAudioState:
    def test_builds_glyph_audio_state_from_composer_and_cadence_context(self):
        glyph = self_listener.build_glyph_audio_state(
            101.5,
            {
                "rms": 0.08,
                "peak": 0.2,
                "pitch_hz": 440.0,
                "pitch_confidence": 0.92,
                "spectral_centroid_hz": 1450.0,
                "onset_rate_hz": 3.2,
            },
            {"count": 0},
            composer_state={
                "arc_phase": "Conversation",
                "glyph_visual_bias": {"motion": 0.8, "density": 0.7},
                "sample_source": "theramini_in",
                "sample_transforms": ["slice_rearrange", "pitch_window"],
                "sample_density": 0.56,
                "dsp_blocks": ["cross_synthesis", "parallel_delay"],
                "dsp_source_focus": "theramini_in",
                "artistic_identity": "CypherClaw leans toward bloom forms.",
            },
            cadence_state={
                "spectral_centroid_hz": 1800.0,
                "onset_density_range": [2.0, 4.0],
            },
        )

        assert glyph["arc_phase"] == "Conversation"
        assert glyph["sample_source"] == "theramini_in"
        assert glyph["dsp_blocks"] == ["cross_synthesis", "parallel_delay"]
        assert glyph["visual_bias"] == {"motion": 0.8, "density": 0.7}
        assert glyph["brightness"] > 0.0
        assert glyph["motion"] > 0.0
        assert glyph["density"] > 0.0
        assert glyph["artistic_identity"]

    def test_glyph_audio_state_prefers_audio_features_over_target_metadata(self):
        glyph = self_listener.build_glyph_audio_state(
            88.0,
            {
                "rms": 0.05,
                "peak": 0.12,
                "pitch_hz": 220.0,
                "pitch_confidence": 0.7,
                "spectral_centroid_hz": 420.0,
                "onset_rate_hz": 0.8,
            },
            {"count": 0},
            composer_state={
                "target_spectral_centroid_hz": 3000.0,
                "glyph_visual_bias": {"brightness": 1.0},
            },
            cadence_state={"spectral_centroid_hz": 2800.0, "onset_density_range": [4.0, 6.0]},
        )

        assert glyph["spectral_centroid_hz"] == 420.0
        assert glyph["onset_rate_hz"] == 0.8
        assert glyph["brightness"] < 0.5

    def test_builds_quiet_glyph_state_when_capture_is_silent(self):
        glyph = self_listener.build_glyph_audio_state(
            55.0,
            {
                "rms": 0.0,
                "peak": 0.0,
                "pitch_hz": 0.0,
                "pitch_confidence": 0.0,
                "spectral_centroid_hz": 0.0,
                "onset_rate_hz": 0.0,
            },
            {"count": 0},
            composer_state={},
            cadence_state={},
        )

        assert glyph["motion"] == 0.0
        assert glyph["density"] == 0.0
        assert glyph["brightness"] >= 0.0


class TestCaptureBackendSelection:
    def setup_method(self) -> None:
        self_listener.reset_capture_backend_cache()

    def test_prefers_pipewire_monitor_target_when_available(self, monkeypatch):
        monkeypatch.setattr(self_listener, "resolve_pipewire_monitor_target", lambda status=None: "71")

        assert self_listener.select_capture_backend("SuperCollider:out_1") == "pipewire"

    def test_prefers_real_jack_when_capture_port_exists(self, monkeypatch):
        monkeypatch.setattr(self_listener, "resolve_pipewire_monitor_target", lambda status=None: None)

        def fake_run(cmd, capture_output=True, text=True, timeout=None, check=False, env=None):
            if cmd == ["jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="SuperCollider:out_1\n")
            if cmd == ["pw-jack", "jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="")
            raise AssertionError(cmd)

        monkeypatch.setattr(self_listener.subprocess, "run", fake_run)

        assert self_listener.select_capture_backend("SuperCollider:out_1") == "jack"

    def test_falls_back_to_pipewire_jack_when_real_jack_port_is_absent(self, monkeypatch):
        monkeypatch.setattr(self_listener, "resolve_pipewire_monitor_target", lambda status=None: None)

        def fake_run(cmd, capture_output=True, text=True, timeout=None, check=False, env=None):
            if cmd == ["jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 1, stdout="")
            if cmd == ["pw-jack", "jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="SuperCollider:out_1\n")
            raise AssertionError(cmd)

        monkeypatch.setattr(self_listener.subprocess, "run", fake_run)

        assert self_listener.select_capture_backend("SuperCollider:out_1") == "pw-jack"

    def test_rechecks_real_jack_after_pw_jack_cache_reset(self, monkeypatch):
        monkeypatch.setattr(self_listener, "resolve_pipewire_monitor_target", lambda status=None: None)
        state = {"direct_jack": False}
        calls: list[tuple[tuple[str, ...], float | None]] = []

        def fake_run(cmd, capture_output=True, text=True, timeout=None, check=False, env=None):
            calls.append((tuple(cmd), timeout))
            if cmd == ["jack_lsp"]:
                if not state["direct_jack"]:
                    raise subprocess.TimeoutExpired(cmd, timeout or 0)
                return subprocess.CompletedProcess(cmd, 0, stdout="SuperCollider:out_1\n")
            if cmd == ["pw-jack", "jack_lsp"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="SuperCollider:out_1\n")
            raise AssertionError(cmd)

        monkeypatch.setattr(self_listener.subprocess, "run", fake_run)

        assert self_listener.select_capture_backend("SuperCollider:out_1", now=100.0) == "pw-jack"
        first_call_count = len(calls)
        assert self_listener.select_capture_backend("SuperCollider:out_1", now=110.0) == "pw-jack"
        assert len(calls) == first_call_count

        self_listener.reset_capture_backend_cache()
        state["direct_jack"] = True

        assert self_listener.select_capture_backend("SuperCollider:out_1", now=111.0) == "jack"
        assert any(
            cmd == ("jack_lsp",) and timeout == self_listener.DIRECT_JACK_PROBE_TIMEOUT_SECONDS
            for cmd, timeout in calls
        )

    def test_build_capture_command_sets_no_autostart_env(self, monkeypatch):
        monkeypatch.setattr(self_listener, "select_capture_backend", lambda _port: "jack")

        cmd, env, backend = self_listener.build_capture_command("SuperCollider:out_1")

        assert backend == "jack"
        assert cmd[:4] == ["jack_rec", "-f", self_listener.CLIP, "-d"]
        assert env["JACK_NO_START_SERVER"] == "1"

    def test_build_capture_command_uses_pipewire_target(self, monkeypatch):
        monkeypatch.setattr(self_listener, "select_capture_backend", lambda _port: "pipewire")
        monkeypatch.setattr(self_listener, "resolve_pipewire_monitor_target", lambda status=None: "71")

        cmd, env, backend = self_listener.build_capture_command("SuperCollider:out_1")

        assert backend == "pipewire"
        assert cmd[:5] == ["timeout", "2", "pw-record", "--target", "71"]
        assert cmd[-1] == self_listener.CLIP
        assert "JACK_NO_START_SERVER" not in env

    def test_resolve_pipewire_monitor_target_prefers_default_sink(self):
        status = """
Audio
 ├─ Sinks:
 │  *   71. Perform-VE Analog Surround 7.1      [vol: 1.50]
 │      93. JACK Sink                           [vol: 1.00]
 │  
 ├─ Sources:
"""

        assert self_listener.resolve_pipewire_monitor_target(status) == "71"

    def test_run_capture_once_discards_child_output(self, monkeypatch, tmp_path):
        stale_clip = tmp_path / "self_listen.wav"
        stale_clip.write_text("stale")
        monkeypatch.setattr(self_listener, "CLIP", str(stale_clip))
        captured: dict[str, object] = {}

        def fake_run(cmd, timeout=None, stdout=None, stderr=None, check=False, env=None):
            captured["cmd"] = cmd
            captured["timeout"] = timeout
            captured["stdout"] = stdout
            captured["stderr"] = stderr
            return subprocess.CompletedProcess(cmd, 0)

        monkeypatch.setattr(self_listener.subprocess, "run", fake_run)

        ok = self_listener.run_capture_once(["jack_rec", "dummy"], {"JACK_NO_START_SERVER": "1"})

        assert ok is True
        assert not stale_clip.exists()
        assert captured["stdout"] is subprocess.DEVNULL
        assert captured["stderr"] is subprocess.DEVNULL


class TestFallbackCapture:
    def _write_wav(self, path, *, sample_rate=16000, frames=1600, amplitude=4000):
        with wave.open(str(path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            data = [int(amplitude if (index % 2 == 0) else -amplitude) for index in range(frames)]
            wav_file.writeframes(struct.pack(f"<{len(data)}h", *data))

    def test_load_fallback_capture_uses_recent_room_capture(self, tmp_path, monkeypatch):
        room_capture = tmp_path / "room_capture.wav"
        self._write_wav(room_capture)
        monkeypatch.setattr(self_listener, "ROOM_CAPTURE", str(room_capture))
        monkeypatch.setattr(self_listener, "ROOM_CAPTURE_MAX_AGE_SECONDS", 30.0)

        analysis, backend = self_listener.load_fallback_capture(now=room_capture.stat().st_mtime + 5.0)

        assert backend == "room_capture"
        assert analysis is not None
        assert analysis["sample_rate"] == 16000
        assert analysis["peak"] > 0.0

    def test_load_fallback_capture_ignores_stale_room_capture(self, tmp_path, monkeypatch):
        room_capture = tmp_path / "room_capture.wav"
        self._write_wav(room_capture)
        monkeypatch.setattr(self_listener, "ROOM_CAPTURE", str(room_capture))
        monkeypatch.setattr(self_listener, "ROOM_CAPTURE_MAX_AGE_SECONDS", 5.0)

        analysis, backend = self_listener.load_fallback_capture(now=room_capture.stat().st_mtime + 30.0)

        assert analysis is None
        assert backend is None
