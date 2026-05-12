"""Tests for artistic identity derivation from repertoire-like memory."""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools", "senseweave"))

from senseweave.artistic_identity import derive_artistic_identity


def test_identity_derives_signature_families_and_images() -> None:
    identity = derive_artistic_identity(
        [
            {"family": "bloom", "patch_name": "house_garden", "title": "Quiet Rooms", "hook_text": "keep the room open"},
            {"family": "bloom", "patch_name": "house_garden", "title": "Near Thresholds", "hook_text": "keep the room open"},
            {"family": "ember", "patch_name": "house_chamber", "title": "Moving Lines", "hook_text": "let the line ring"},
        ]
    )

    assert identity.signature_families[0] == "bloom"
    assert identity.signature_patches[0] == "house_garden"
    assert identity.signature_images[0] == "room"
    assert identity.statement
