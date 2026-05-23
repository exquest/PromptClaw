"""Tests for the CYPHERCLAW_V2_TUNING_MORPH activation flag (T-040 / CC-047)."""

from __future__ import annotations

import os

from cypherclaw.tuning import CYPHERCLAW_V2_TUNING_MORPH_ENV, tuning_morph_enabled
from cypherclaw.tuning import flags as tuning_flags


def test_env_name_matches_prd() -> None:
    assert CYPHERCLAW_V2_TUNING_MORPH_ENV == "CYPHERCLAW_V2_TUNING_MORPH"
    assert tuning_flags.CYPHERCLAW_V2_TUNING_MORPH_ENV == "CYPHERCLAW_V2_TUNING_MORPH"


def test_default_off_when_env_unset() -> None:
    # CC-047: "default behavior matches OFF state."
    assert tuning_morph_enabled(env={}) is False


def test_default_off_in_real_environment_without_variable(monkeypatch) -> None:
    monkeypatch.delenv(CYPHERCLAW_V2_TUNING_MORPH_ENV, raising=False)
    assert tuning_morph_enabled() is False


def test_falsy_values_resolve_off() -> None:
    for falsy in ("", "0", "false", "no", "off", "disabled", "  ", "FALSE", "  off "):
        assert (
            tuning_morph_enabled(env={CYPHERCLAW_V2_TUNING_MORPH_ENV: falsy}) is False
        ), falsy


def test_truthy_values_resolve_on() -> None:
    for truthy in ("1", "true", "yes", "on", "enabled", " TRUE ", "On", "ENABLED"):
        assert (
            tuning_morph_enabled(env={CYPHERCLAW_V2_TUNING_MORPH_ENV: truthy}) is True
        ), truthy


def test_reads_real_environment_by_default(monkeypatch) -> None:
    monkeypatch.setenv(CYPHERCLAW_V2_TUNING_MORPH_ENV, "1")
    assert tuning_morph_enabled() is True
    monkeypatch.setenv(CYPHERCLAW_V2_TUNING_MORPH_ENV, "0")
    assert tuning_morph_enabled() is False
    monkeypatch.delenv(CYPHERCLAW_V2_TUNING_MORPH_ENV, raising=False)
    assert tuning_morph_enabled() is False


def test_env_mapping_overrides_os_environ(monkeypatch) -> None:
    monkeypatch.setenv(CYPHERCLAW_V2_TUNING_MORPH_ENV, "1")
    # Passing an explicit env mapping must bypass os.environ entirely.
    assert tuning_morph_enabled(env={}) is False
    assert (
        tuning_morph_enabled(env={CYPHERCLAW_V2_TUNING_MORPH_ENV: "0"}) is False
    )


def test_unrelated_env_vars_do_not_enable_flag() -> None:
    # Guard against accidental coupling with sibling v2 flags.
    env = {
        "CYPHERCLAW_V2_FATIGUE": "1",
        "CYPHERCLAW_V2_INSTRUMENT_MORPH": "1",
        "CYPHERCLAW_V2_COUPLING": "1",
    }
    assert tuning_morph_enabled(env=env) is False


def test_module_does_not_capture_os_environ_at_import() -> None:
    # Ensure the function reads os.environ at call time, not at import time.
    saved = os.environ.pop(CYPHERCLAW_V2_TUNING_MORPH_ENV, None)
    try:
        assert tuning_morph_enabled() is False
        os.environ[CYPHERCLAW_V2_TUNING_MORPH_ENV] = "yes"
        assert tuning_morph_enabled() is True
    finally:
        if saved is None:
            os.environ.pop(CYPHERCLAW_V2_TUNING_MORPH_ENV, None)
        else:
            os.environ[CYPHERCLAW_V2_TUNING_MORPH_ENV] = saved
