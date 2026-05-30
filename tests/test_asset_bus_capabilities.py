"""Tests for the asset-bus capability matrix (T-010)."""

from __future__ import annotations

import pytest

from promptclaw.asset_bus import CAPABILITIES, capability_for


@pytest.mark.parametrize(
    "asset_type,expected",
    [
        ("image", "supported"),
        ("music", "supported"),
        ("sfx", "experimental"),
        ("voiceover", "deferred"),
    ],
)
def test_capability_matrix_value(asset_type: str, expected: str) -> None:
    assert CAPABILITIES[asset_type] == expected
    assert capability_for(asset_type) == expected


def test_capability_matrix_has_exactly_the_v01_asset_types() -> None:
    assert set(CAPABILITIES) == {"image", "music", "sfx", "voiceover"}


def test_capability_matrix_is_immutable() -> None:
    with pytest.raises(TypeError):
        CAPABILITIES["image"] = "deferred"  # type: ignore[index]


def test_capability_for_unknown_asset_type_is_none() -> None:
    assert capability_for("hologram") is None
