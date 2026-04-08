"""Integration tests for first-boot federation announcement wiring (FEDREAD-004).

Verifies:
- A federated clone triggers the announcement on startup.
- A standalone instance does not announce.
- A repeat boot does not re-announce.
"""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

sys.path.insert(0, "/home/user/cypherclaw/src")

from cypherclaw.first_boot import (
    FirstBootAnnouncer,
    bootstrap_identity,
    generate_artistic_name,
    mint_identity,
)


# ── Helpers ─────────────────────────────────────────────────────


def _write_identity(path, *, mode="federated", parent_id="parent-abc", **overrides):
    """Write a minimal identity file to *path*."""
    data = {
        "instance_id": overrides.get("instance_id", "test-instance-001"),
        "instance_name": overrides.get("instance_name", "test-home"),
        "mode": mode,
        "created_at": "2026-04-01T00:00:00+00:00",
        "release": overrides.get("release", "2.1.0"),
        "parent_id": parent_id,
        "clone_timestamp": "2026-04-01T00:00:00+00:00",
        "capabilities": overrides.get("capabilities", ["art", "music"]),
    }
    path.write_text(json.dumps(data))


def _make_announcer(tmp_path, *, mode="federated", parent_id="parent-abc",
                    pre_announced=False, **identity_kw):
    """Build a FirstBootAnnouncer wired to tmp_path with a mock announce_fn."""
    identity_path = tmp_path / "identity.json"
    announced_path = tmp_path / ".first_boot_announced"

    _write_identity(identity_path, mode=mode, parent_id=parent_id, **identity_kw)

    if pre_announced:
        announced_path.write_text(json.dumps({"announced_at": "2026-04-01T00:00:00+00:00"}))

    mock_fn = MagicMock()
    announcer = FirstBootAnnouncer(
        identity_path=identity_path,
        announced_path=announced_path,
        announce_fn=mock_fn,
    )
    return announcer, mock_fn


# ── Federated clone announces on first boot ─────────────────────


class TestFederatedCloneAnnounces:
    """A federated clone must announce exactly once on its very first boot."""

    def test_announces_on_first_boot(self, tmp_path):
        announcer, mock_fn = _make_announcer(tmp_path, mode="federated")

        payload = announcer.maybe_announce()

        assert payload is not None
        mock_fn.assert_called_once()
        assert payload["type"] == "first_boot_announcement"
        assert payload["mode"] == "federated"

    def test_announcement_contains_required_fields(self, tmp_path):
        announcer, _ = _make_announcer(
            tmp_path,
            mode="federated",
            instance_id="id-xyz",
            instance_name="my-home",
            release="2.1.0",
            parent_id="parent-abc",
            capabilities=["art", "music"],
        )

        payload = announcer.maybe_announce()

        assert payload is not None
        assert payload["instance_id"] == "id-xyz"
        assert payload["instance_name"] == "my-home"
        assert payload["release"] == "2.1.0"
        assert payload["lineage"]["parent_id"] == "parent-abc"
        assert payload["lineage"]["clone_timestamp"] is not None
        assert payload["capabilities"] == ["art", "music"]
        assert payload["publication_status"] == "local"
        assert "announced_at" in payload

    def test_announcement_excludes_private_data(self, tmp_path):
        """Payload must not leak raw private memory or secrets."""
        announcer, _ = _make_announcer(tmp_path, mode="federated")

        payload = announcer.maybe_announce()

        assert payload is not None
        payload_str = json.dumps(payload)
        for forbidden in ("private_memory", "secret", "token", "password", "api_key"):
            assert forbidden not in payload_str.lower(), (
                f"Payload should not contain '{forbidden}'"
            )

    def test_marker_file_created_after_announce(self, tmp_path):
        announcer, _ = _make_announcer(tmp_path, mode="federated")

        announcer.maybe_announce()

        assert announcer.announced_path.exists()
        marker = json.loads(announcer.announced_path.read_text())
        assert "announced_at" in marker


# ── Standalone instance does NOT announce ────────────────────────


class TestStandaloneDoesNotAnnounce:
    """A standalone instance must never automatically announce."""

    def test_standalone_skips_announcement(self, tmp_path):
        announcer, mock_fn = _make_announcer(tmp_path, mode="standalone")

        payload = announcer.maybe_announce()

        assert payload is None
        mock_fn.assert_not_called()

    def test_standalone_does_not_create_marker(self, tmp_path):
        announcer, _ = _make_announcer(tmp_path, mode="standalone")

        announcer.maybe_announce()

        assert not announcer.announced_path.exists()

    def test_standalone_with_parent_still_skips(self, tmp_path):
        """Even cloned standalones (with a parent_id) must not announce."""
        announcer, mock_fn = _make_announcer(
            tmp_path, mode="standalone", parent_id="parent-123",
        )

        payload = announcer.maybe_announce()

        assert payload is None
        mock_fn.assert_not_called()


# ── Repeat boot does NOT re-announce ─────────────────────────────


class TestRepeatBootDoesNotReAnnounce:
    """Once announced, subsequent boots must not send another announcement."""

    def test_second_boot_skips(self, tmp_path):
        announcer, mock_fn = _make_announcer(tmp_path, mode="federated")

        first = announcer.maybe_announce()
        assert first is not None
        mock_fn.assert_called_once()

        # Simulate reboot: create a fresh announcer pointing at the same paths.
        mock_fn2 = MagicMock()
        announcer2 = FirstBootAnnouncer(
            identity_path=announcer.identity_path,
            announced_path=announcer.announced_path,
            announce_fn=mock_fn2,
        )
        second = announcer2.maybe_announce()

        assert second is None
        mock_fn2.assert_not_called()

    def test_pre_announced_instance_skips(self, tmp_path):
        """An already-announced instance must not re-announce."""
        announcer, mock_fn = _make_announcer(
            tmp_path, mode="federated", pre_announced=True,
        )

        payload = announcer.maybe_announce()

        assert payload is None
        mock_fn.assert_not_called()

    def test_marker_survives_across_announcer_instances(self, tmp_path):
        """The marker file persists independently of the announcer object."""
        announcer, _ = _make_announcer(tmp_path, mode="federated")
        announcer.maybe_announce()

        # Verify the marker was written
        assert announcer.announced_path.exists()

        # Third reboot — still no announcement
        mock_fn3 = MagicMock()
        announcer3 = FirstBootAnnouncer(
            identity_path=announcer.identity_path,
            announced_path=announcer.announced_path,
            announce_fn=mock_fn3,
        )
        assert announcer3.maybe_announce() is None
        mock_fn3.assert_not_called()


# ── Edge cases ───────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases: missing identity, corrupt files, no announce_fn."""

    def test_missing_identity_file(self, tmp_path):
        mock_fn = MagicMock()
        announcer = FirstBootAnnouncer(
            identity_path=tmp_path / "does_not_exist.json",
            announced_path=tmp_path / ".announced",
            announce_fn=mock_fn,
        )

        payload = announcer.maybe_announce()

        assert payload is None
        mock_fn.assert_not_called()

    def test_corrupt_identity_file(self, tmp_path):
        identity_path = tmp_path / "identity.json"
        identity_path.write_text("{bad json")
        mock_fn = MagicMock()
        announcer = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=tmp_path / ".announced",
            announce_fn=mock_fn,
        )

        payload = announcer.maybe_announce()

        assert payload is None
        mock_fn.assert_not_called()

    def test_no_announce_fn_still_marks(self, tmp_path):
        """If no announce_fn is provided, announcement is still marked."""
        identity_path = tmp_path / "identity.json"
        _write_identity(identity_path, mode="federated")
        announced_path = tmp_path / ".announced"

        announcer = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=announced_path,
            announce_fn=None,
        )

        payload = announcer.maybe_announce()

        assert payload is not None
        assert announced_path.exists()


# ── mint_identity helper ─────────────────────────────────────────


class TestMintIdentity:
    """Tests for the mint_identity convenience function."""

    def test_mints_unique_id(self, tmp_path):
        id1 = mint_identity(identity_path=tmp_path / "id1.json")
        id2 = mint_identity(identity_path=tmp_path / "id2.json")
        assert id1.instance_id != id2.instance_id

    def test_persists_to_disk(self, tmp_path):
        path = tmp_path / "identity.json"
        identity = mint_identity(mode="federated", release="2.1.0", identity_path=path)

        assert path.exists()
        data = json.loads(path.read_text())
        assert data["instance_id"] == identity.instance_id
        assert data["mode"] == "federated"

    def test_clone_records_lineage(self, tmp_path):
        path = tmp_path / "identity.json"
        identity = mint_identity(
            mode="federated",
            parent_id="parent-xyz",
            identity_path=path,
        )

        assert identity.parent_id == "parent-xyz"
        assert identity.clone_timestamp is not None

    def test_standalone_no_clone_timestamp(self, tmp_path):
        path = tmp_path / "identity.json"
        identity = mint_identity(mode="standalone", identity_path=path)

        assert identity.parent_id is None
        assert identity.clone_timestamp is None


# ── Full integration: mint → boot → announce → reboot ────────────


class TestFullIntegration:
    """End-to-end: mint an identity, boot, announce, reboot, verify no repeat."""

    def test_federated_clone_lifecycle(self, tmp_path):
        identity_path = tmp_path / "identity.json"
        announced_path = tmp_path / ".first_boot_announced"

        # Step 1: Mint a federated clone identity
        identity = mint_identity(
            mode="federated",
            parent_id="origin-home",
            release="2.1.0",
            identity_path=identity_path,
        )
        assert identity.mode == "federated"
        assert identity.parent_id == "origin-home"

        # Step 2: First boot — should announce
        mock_fn = MagicMock()
        announcer = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=announced_path,
            announce_fn=mock_fn,
        )
        payload = announcer.maybe_announce()

        assert payload is not None
        assert payload["instance_id"] == identity.instance_id
        assert payload["lineage"]["parent_id"] == "origin-home"
        mock_fn.assert_called_once_with(payload)

        # Step 3: Second boot — must NOT re-announce
        mock_fn2 = MagicMock()
        announcer2 = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=announced_path,
            announce_fn=mock_fn2,
        )
        assert announcer2.maybe_announce() is None
        mock_fn2.assert_not_called()

    def test_standalone_clone_lifecycle(self, tmp_path):
        identity_path = tmp_path / "identity.json"
        announced_path = tmp_path / ".first_boot_announced"

        # Mint a standalone clone
        mint_identity(
            mode="standalone",
            parent_id="origin-home",
            identity_path=identity_path,
        )

        # Boot — should NOT announce
        mock_fn = MagicMock()
        announcer = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=announced_path,
            announce_fn=mock_fn,
        )
        assert announcer.maybe_announce() is None
        mock_fn.assert_not_called()
        assert not announced_path.exists()


# ── Artistic name generation ───────────────────────────────────


class TestGenerateArtisticName:
    """Tests for the artistic instance name generator."""

    def test_returns_adjective_dash_noun(self):
        name = generate_artistic_name()
        parts = name.split("-")
        assert len(parts) == 2, f"Expected 'adjective-noun', got {name!r}"

    def test_deterministic_with_seed(self):
        import random

        rng = random.Random(42)
        name1 = generate_artistic_name(rng=rng)
        rng2 = random.Random(42)
        name2 = generate_artistic_name(rng=rng2)
        assert name1 == name2

    def test_different_seeds_produce_different_names(self):
        import random

        name1 = generate_artistic_name(rng=random.Random(1))
        name2 = generate_artistic_name(rng=random.Random(999))
        assert name1 != name2

    def test_name_uses_lowercase_alpha(self):
        import random

        for seed in range(50):
            name = generate_artistic_name(rng=random.Random(seed))
            assert name == name.lower()
            assert all(c.isalpha() or c == "-" for c in name)

    def test_mint_identity_uses_artistic_name(self, tmp_path):
        """mint_identity without explicit name should use an artistic name."""
        path = tmp_path / "identity.json"
        identity = mint_identity(identity_path=path)
        parts = identity.instance_name.split("-")
        assert len(parts) == 2
        assert all(part.isalpha() for part in parts)


# ── bootstrap_identity ─────────────────────────────────────────


class TestBootstrapIdentity:
    """Tests for the load-or-create bootstrap_identity function."""

    def test_creates_new_on_first_boot(self, tmp_path):
        path = tmp_path / "identity.json"
        identity = bootstrap_identity(identity_path=path)

        assert path.exists()
        assert identity.instance_id
        assert identity.instance_name
        assert identity.mode == "standalone"

    def test_loads_existing_on_subsequent_boot(self, tmp_path):
        path = tmp_path / "identity.json"
        first = bootstrap_identity(identity_path=path)
        second = bootstrap_identity(identity_path=path)

        assert first.instance_id == second.instance_id
        assert first.instance_name == second.instance_name
        assert first.created_at == second.created_at

    def test_does_not_overwrite_existing(self, tmp_path):
        path = tmp_path / "identity.json"
        _write_identity(path, mode="federated", instance_id="keep-me",
                        instance_name="precious-artifact")

        identity = bootstrap_identity(identity_path=path)

        assert identity.instance_id == "keep-me"
        assert identity.instance_name == "precious-artifact"
        assert identity.mode == "federated"

    def test_recovers_from_corrupt_file(self, tmp_path):
        path = tmp_path / "identity.json"
        path.write_text("{corrupt json!!")

        identity = bootstrap_identity(identity_path=path)

        assert identity.instance_id  # fresh identity minted
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["instance_id"] == identity.instance_id

    def test_creates_parent_directory(self, tmp_path):
        path = tmp_path / "nested" / "deep" / "identity.json"
        identity = bootstrap_identity(identity_path=path)

        assert path.exists()
        assert identity.instance_id

    def test_preserves_mode_and_release(self, tmp_path):
        path = tmp_path / "identity.json"
        identity = bootstrap_identity(
            mode="federated",
            release="3.0.0",
            parent_id="parent-abc",
            identity_path=path,
        )

        assert identity.mode == "federated"
        assert identity.release == "3.0.0"
        assert identity.parent_id == "parent-abc"
        assert identity.clone_timestamp is not None


# ── Startup flow integration: bootstrap → announce ───────────────


class TestStartupIdentityPersistence:
    """Simulate the daemon startup flow: bootstrap_identity then FirstBootAnnouncer.

    Verifies the identity is auto-created on first boot and persists across
    subsequent boots without regeneration, matching the real poll_loop() wiring.
    """

    def test_first_boot_creates_identity_then_announces(self, tmp_path):
        """First startup mints identity; announcer finds it and announces."""
        identity_path = tmp_path / "identity.json"
        announced_path = tmp_path / ".first_boot_announced"

        # Simulate startup: bootstrap creates identity
        identity = bootstrap_identity(
            mode="federated",
            release="3.0.0",
            parent_id="origin-home",
            identity_path=identity_path,
        )

        assert identity_path.exists()
        assert identity.instance_id
        assert identity.instance_name

        # Announcer finds the identity and announces
        mock_fn = MagicMock()
        announcer = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=announced_path,
            announce_fn=mock_fn,
        )
        payload = announcer.maybe_announce()

        assert payload is not None
        assert payload["instance_id"] == identity.instance_id
        mock_fn.assert_called_once()

    def test_identity_persists_across_reboots(self, tmp_path):
        """Subsequent boots load the same identity without regenerating."""
        identity_path = tmp_path / "identity.json"

        first = bootstrap_identity(identity_path=identity_path)
        second = bootstrap_identity(identity_path=identity_path)
        third = bootstrap_identity(identity_path=identity_path)

        assert first.instance_id == second.instance_id == third.instance_id
        assert first.instance_name == second.instance_name == third.instance_name
        assert first.created_at == second.created_at == third.created_at

    def test_standalone_startup_creates_identity_no_announce(self, tmp_path):
        """Standalone boot creates identity but does not announce."""
        identity_path = tmp_path / "identity.json"
        announced_path = tmp_path / ".first_boot_announced"

        identity = bootstrap_identity(mode="standalone", identity_path=identity_path)

        assert identity_path.exists()
        assert identity.mode == "standalone"

        mock_fn = MagicMock()
        announcer = FirstBootAnnouncer(
            identity_path=identity_path,
            announced_path=announced_path,
            announce_fn=mock_fn,
        )
        assert announcer.maybe_announce() is None
        mock_fn.assert_not_called()
