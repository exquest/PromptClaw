"""Activation flag for the CypherClaw v2 tuning/morph pipeline.

Per the v2 PRD (§Feature 5 / CC-047), the entire tuning-and-morph stack is
gated behind the ``CYPHERCLAW_V2_TUNING_MORPH`` environment variable and
defaults OFF until the listening-session A/B approval lands. Callers should
check :func:`tuning_morph_enabled` before activating the new pitch pipeline,
falling back to legacy 12-TET behavior when the flag is unset.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


CYPHERCLAW_V2_TUNING_MORPH_ENV = "CYPHERCLAW_V2_TUNING_MORPH"
_TRUTHY_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})


def tuning_morph_enabled(env: Mapping[str, str] | None = None) -> bool:
    """Return True iff ``CYPHERCLAW_V2_TUNING_MORPH`` is set to a truthy value.

    Default OFF: an unset, empty, or non-truthy value resolves to False.
    Truthy values (case-insensitive, surrounding whitespace tolerated):
    ``1``, ``true``, ``yes``, ``on``, ``enabled``.
    """
    source = os.environ if env is None else env
    raw = source.get(CYPHERCLAW_V2_TUNING_MORPH_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUTHY_VALUES
