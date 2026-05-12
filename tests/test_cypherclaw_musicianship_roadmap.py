"""Static regression tests for the musicianship roadmap sampler update."""
from pathlib import Path


ROADMAP_PATH = Path("docs/cypherclaw-musicianship-roadmap.md")


def test_roadmap_names_signature_quintet_and_sampler_role() -> None:
    content = ROADMAP_PATH.read_text(encoding="utf-8")
    lowered = content.lower()

    assert "current ensemble snapshot" in lowered
    assert "quintet" in lowered
    for voice in (
        "sw_bell_warm",
        "sw_bowed",
        "sw_breath",
        "sw_pad",
        "sw_sampler",
    ):
        assert voice in content

    for role_term in (
        "melody",
        "counter",
        "color",
        "foundation",
        "memory voice",
    ):
        assert role_term in lowered


def test_roadmap_records_landed_and_pending_quintet_status() -> None:
    content = ROADMAP_PATH.read_text(encoding="utf-8")
    lowered = content.lower()

    assert "landed now" in lowered
    assert "still pending" in lowered
    assert "quartet" in lowered

    for landed_ref in (
        "sample_capture_daemon.py",
        "sampler_buffers.py",
        "sampler_dispatch.py",
        "sampler_effects.scd",
        "sampler_silent_quintet_member",
    ):
        assert landed_ref in content

    for pending_ref in (
        "artist_identity.py",
        "tests/test_artist_identity.py",
        "SampleLibrary",
        "SampleSelector",
        "sw_sampler.scd",
    ):
        assert pending_ref in content
