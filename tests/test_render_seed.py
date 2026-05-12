from __future__ import annotations

import json

from cypherclaw.render.seed import derive_seed


class TestDeriveSeed:
    def test_returns_int(self) -> None:
        result = derive_seed(42, (1, 2, 3))
        assert isinstance(result, int)

    def test_fits_in_32_bits(self) -> None:
        result = derive_seed(99, (10, 20))
        assert 0 <= result < 2**32

    def test_deterministic_same_inputs(self) -> None:
        a = derive_seed(42, (1, 2, 3))
        b = derive_seed(42, (1, 2, 3))
        assert a == b

    def test_different_root_seeds_differ(self) -> None:
        a = derive_seed(1, (10, 20))
        b = derive_seed(2, (10, 20))
        assert a != b

    def test_different_paths_differ(self) -> None:
        a = derive_seed(42, (1, 2))
        b = derive_seed(42, (1, 3))
        assert a != b

    def test_path_order_matters(self) -> None:
        a = derive_seed(42, (1, 2))
        b = derive_seed(42, (2, 1))
        assert a != b

    def test_empty_path(self) -> None:
        result = derive_seed(42, ())
        assert isinstance(result, int)
        assert 0 <= result < 2**32

    def test_empty_path_differs_from_nonempty(self) -> None:
        a = derive_seed(42, ())
        b = derive_seed(42, (0,))
        assert a != b

    def test_negative_root_seed(self) -> None:
        result = derive_seed(-1, (1,))
        assert 0 <= result < 2**32

    def test_negative_path_elements(self) -> None:
        result = derive_seed(42, (-5, -10))
        assert 0 <= result < 2**32

    def test_large_path(self) -> None:
        result = derive_seed(0, tuple(range(100)))
        assert 0 <= result < 2**32

    def test_known_value_stability(self) -> None:
        result = derive_seed(42, (1, 2, 3))
        assert result == derive_seed(42, (1, 2, 3))
        assert result != 0

    def test_seed_path_on_event(self) -> None:
        from cypherclaw.render.events import Event

        root = 12345
        path = (7, 3)
        sub = derive_seed(root, path)
        evt = Event(seed_path=path)
        reproduced = derive_seed(root, evt.seed_path)
        assert reproduced == sub


class RenderSeedEndToEndTests:
    """End-to-end render-seed lifecycle across the public surface."""

    __test__ = True

    def test_full_seed_derivation_lifecycle_is_json_safe_and_event_round_trip_safe(
        self,
    ) -> None:
        from cypherclaw.render.events import Event

        root_seed = 20260502
        alt_root_seed = root_seed ^ 0xA5A5A5A5
        family: tuple[tuple[int, ...], ...] = (
            (1,),
            (1, 0),
            (1, 0, 7),
            (1, 0, 11),
            (1, 1, 7),
            (2, 3, 5),
        )

        primary_seeds = [derive_seed(root_seed, path) for path in family]
        replayed_seeds = [derive_seed(root_seed, path) for path in family]
        alt_seeds = [derive_seed(alt_root_seed, path) for path in family]

        for seed in primary_seeds:
            assert isinstance(seed, int)
            assert 0 <= seed < 2**32

        assert primary_seeds == replayed_seeds
        assert len(set(primary_seeds)) == len(primary_seeds)
        for primary, alt in zip(primary_seeds, alt_seeds):
            assert primary != alt

        events = [
            Event(event_id=f"evt-{index}", seed_path=path)
            for index, path in enumerate(family)
        ]
        for path, event, expected_seed in zip(family, events, primary_seeds):
            assert isinstance(event.seed_path, tuple)
            assert event.seed_path == path
            assert derive_seed(root_seed, event.seed_path) == expected_seed

        diagnostic = {
            "root_seed": root_seed,
            "alt_root_seed": alt_root_seed,
            "family": [
                {
                    "event_id": event.event_id,
                    "path": list(path),
                    "seed": seed,
                    "alt_seed": alt_seed,
                    "event_seed_path": list(event.seed_path),
                }
                for path, event, seed, alt_seed in zip(
                    family, events, primary_seeds, alt_seeds
                )
            ],
        }
        round_tripped = json.loads(json.dumps(diagnostic, sort_keys=True))

        assert round_tripped["root_seed"] == root_seed
        assert round_tripped["alt_root_seed"] == alt_root_seed
        assert len(round_tripped["family"]) == len(family)
        for entry, path, seed, alt_seed in zip(
            round_tripped["family"], family, primary_seeds, alt_seeds
        ):
            assert entry["path"] == list(path)
            assert entry["event_seed_path"] == list(path)
            assert entry["seed"] == seed
            assert entry["alt_seed"] == alt_seed
            assert derive_seed(root_seed, tuple(entry["event_seed_path"])) == seed

    def test_family_seeds_remain_within_32_bit_range_for_full_walk(self) -> None:
        root_seed = 0xCAFEBABE
        family: tuple[tuple[int, ...], ...] = (
            (0,),
            (1, 2),
            (3, 5, 8, 13),
            (21, 34, 55, 89, 144),
        )
        seeds: list[int] = []
        for path in family:
            sub_seed = derive_seed(root_seed, path)
            assert isinstance(sub_seed, int)
            assert 0 <= sub_seed < 2**32
            seeds.append(sub_seed)
        assert len(seeds) == len(family)

    def test_family_redrives_deterministically_across_repeats(self) -> None:
        root_seed = 0xDEADBEEF
        family: tuple[tuple[int, ...], ...] = (
            (1, 0),
            (1, 1),
            (2, 0),
            (2, 1, 9),
        )
        baseline = [derive_seed(root_seed, path) for path in family]
        for _ in range(4):
            replay = [derive_seed(root_seed, path) for path in family]
            assert replay == baseline

    def test_family_distinct_paths_yield_distinct_seeds(self) -> None:
        root_seed = 17
        family: tuple[tuple[int, ...], ...] = (
            (1,),
            (2,),
            (1, 0),
            (1, 0, 0),
            (0, 1, 0),
        )
        seeds: list[int] = []
        for path in family:
            sub_seed = derive_seed(root_seed, path)
            assert sub_seed not in seeds
            seeds.append(sub_seed)
        assert len(set(seeds)) == len(family)

    def test_family_root_seed_sensitivity_holds_at_every_position(self) -> None:
        family: tuple[tuple[int, ...], ...] = (
            (4,),
            (4, 2),
            (4, 2, 0),
            (4, 2, 0, 7),
        )
        primary_root = 100
        for delta in (1, 7, 0xA5A5, -3, 0xFFFFFFFF):
            alt_root = primary_root ^ delta if delta >= 0 else primary_root + delta
            for path in family:
                primary = derive_seed(primary_root, path)
                alt = derive_seed(alt_root, path)
                assert primary != alt

    def test_family_event_seed_path_is_normalized_to_int_tuple(self) -> None:
        from cypherclaw.render.events import Event

        family: tuple[tuple[int, ...], ...] = (
            (1, 2, 3),
            (10, 20),
            (0,),
        )
        for index, path in enumerate(family):
            event = Event(event_id=f"evt-{index}", seed_path=path)
            assert isinstance(event.seed_path, tuple)
            assert event.seed_path == path
            for component in event.seed_path:
                assert isinstance(component, int)

    def test_family_event_round_trip_reproduces_original_seed(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = 314159
        family: tuple[tuple[int, ...], ...] = (
            (1,),
            (1, 4),
            (1, 4, 1),
            (1, 4, 1, 5),
            (9, 2, 6),
        )
        for path in family:
            expected = derive_seed(root_seed, path)
            event = Event(seed_path=path)
            replayed = derive_seed(root_seed, event.seed_path)
            assert replayed == expected

    def test_family_path_order_sensitivity_via_event_round_trip(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = 99
        ordered_pairs: tuple[tuple[tuple[int, ...], tuple[int, ...]], ...] = (
            ((1, 2), (2, 1)),
            ((3, 5, 8), (8, 5, 3)),
            ((4, 0, 0, 1), (1, 0, 0, 4)),
        )
        for forward, reverse in ordered_pairs:
            forward_event = Event(seed_path=forward)
            reverse_event = Event(seed_path=reverse)
            forward_seed = derive_seed(root_seed, forward_event.seed_path)
            reverse_seed = derive_seed(root_seed, reverse_event.seed_path)
            assert forward_seed != reverse_seed

    def test_family_diagnostic_round_trips_per_position_seeds(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = 2026
        family: tuple[tuple[int, ...], ...] = (
            (1,),
            (1, 2),
            (1, 2, 3),
            (4, 5, 6, 7),
        )
        diagnostic_entries: list[dict[str, object]] = []
        for index, path in enumerate(family):
            seed = derive_seed(root_seed, path)
            event = Event(event_id=f"evt-{index}", seed_path=path)
            diagnostic_entries.append(
                {
                    "event_id": event.event_id,
                    "path": list(event.seed_path),
                    "seed": seed,
                }
            )
        encoded = json.dumps(
            {"root_seed": root_seed, "family": diagnostic_entries},
            sort_keys=True,
        )
        decoded = json.loads(encoded)
        assert decoded["root_seed"] == root_seed
        assert len(decoded["family"]) == len(family)
        for decoded_entry, original in zip(decoded["family"], diagnostic_entries):
            assert decoded_entry == original
            assert (
                derive_seed(root_seed, tuple(decoded_entry["path"]))
                == decoded_entry["seed"]
            )

    def test_family_empty_path_lifecycle_round_trips(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = 7
        empty_path: tuple[int, ...] = ()
        baseline_seed = derive_seed(root_seed, empty_path)
        event = Event(event_id="evt-empty", seed_path=empty_path)
        encoded = json.dumps({"path": list(event.seed_path), "seed": baseline_seed})
        decoded = json.loads(encoded)
        for path_entry in (
            tuple(decoded["path"]),
            event.seed_path,
            empty_path,
        ):
            assert derive_seed(root_seed, path_entry) == baseline_seed

    def test_family_negative_components_lifecycle_remain_in_range(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = -42
        family: tuple[tuple[int, ...], ...] = (
            (-1,),
            (-1, -2),
            (-1, -2, -3),
            (5, -7, 11, -13),
        )
        for path in family:
            seed = derive_seed(root_seed, path)
            assert 0 <= seed < 2**32
            event = Event(seed_path=path)
            assert event.seed_path == path
            assert derive_seed(root_seed, event.seed_path) == seed

    def test_family_large_path_lifecycle_round_trips(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = 0
        widths = (1, 8, 32, 128)
        for width in widths:
            path = tuple(range(width))
            expected = derive_seed(root_seed, path)
            assert 0 <= expected < 2**32
            event = Event(seed_path=path)
            assert len(event.seed_path) == width
            assert derive_seed(root_seed, event.seed_path) == expected

    def test_family_event_id_uniqueness_does_not_affect_derived_seed(self) -> None:
        from cypherclaw.render.events import Event

        root_seed = 65535
        path = (3, 1, 4, 1, 5, 9)
        baseline = derive_seed(root_seed, path)
        for index in range(8):
            event = Event(event_id=f"evt-{index}", seed_path=path)
            assert event.event_id == f"evt-{index}"
            assert derive_seed(root_seed, event.seed_path) == baseline
