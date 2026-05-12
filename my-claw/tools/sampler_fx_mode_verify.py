"""Smoke-test entry point: drive every ArtistMode through the sampler FX bus.

Operators run this on cypherclaw (or any host with the sampler tools) to
verify end-to-end that each mode pushes the canonical CCS-026 preset onto the
shared ``sw_sampler_fx`` bus.
"""
from __future__ import annotations

import argparse
import json
import sys

from senseweave.sampler_dispatch import EffectsBus, FX_PRESETS_BY_MODE


MODE_SEQUENCE: tuple[str, ...] = tuple(FX_PRESETS_BY_MODE)


class _RecordingOSC:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[object]]] = []

    def send_message(self, address: str, args: list[object]) -> None:
        self.calls.append((address, list(args)))


def _latest_bus_pairs(osc: _RecordingOSC, fx_node_id: int) -> dict[str, float]:
    n_set = next(
        call for call in reversed(osc.calls)
        if call[0] == "/n_set" and call[1] and call[1][0] == fx_node_id
    )
    return {
        str(key): float(value)
        for key, value in zip(n_set[1][1::2], n_set[1][2::2])
    }


def capture_mode_snapshots(*, fx_node_id: int = 99) -> dict[str, dict[str, float]]:
    """Apply every canonical mode once and capture the bus state after each."""
    osc = _RecordingOSC()
    bus = EffectsBus(osc, fx_node_id=fx_node_id)
    snapshots: dict[str, dict[str, float]] = {}
    for mode in MODE_SEQUENCE:
        changed = bus.apply_mode(mode)
        if not changed:
            raise AssertionError(f"expected {mode} to emit a new /n_set")
        if bus.current_mode != mode:
            raise AssertionError(
                f"expected current_mode={mode!r}, got {bus.current_mode!r}"
            )
        snapshots[mode] = _latest_bus_pairs(osc, fx_node_id)
    return snapshots


def assert_mode_snapshots_match_presets(
    snapshots: dict[str, dict[str, float]],
) -> None:
    """Fail loudly when the captured bus state drifts from the canonical table."""
    if tuple(snapshots) != MODE_SEQUENCE:
        raise AssertionError(
            f"expected mode order {MODE_SEQUENCE!r}, got {tuple(snapshots)!r}"
        )
    for mode in MODE_SEQUENCE:
        expected = FX_PRESETS_BY_MODE[mode]
        actual = snapshots[mode]
        if actual != expected:
            raise AssertionError(
                f"{mode} preset mismatch: expected {expected!r}, got {actual!r}"
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fx-node-id",
        type=int,
        default=99,
        help="bus node id to target during the smoke run (default: %(default)s)",
    )
    args = parser.parse_args(argv)

    snapshots = capture_mode_snapshots(fx_node_id=args.fx_node_id)
    assert_mode_snapshots_match_presets(snapshots)
    for mode in MODE_SEQUENCE:
        print(f"{mode}={json.dumps(snapshots[mode], sort_keys=True)}")
    print("FX_MODE_PRESETS_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
