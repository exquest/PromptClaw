from cypherclaw.render.events import Event
from cypherclaw.render.rules.call_response import (
    CallResponseRule,
    PerformedPart,
)


def _pearson(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0 or var_y == 0:
        return 0.0
    return cov / (var_x**0.5 * var_y**0.5)


def _make_follower(position: float = 0.0) -> Event:
    return Event(
        normalized_phrase_position=position,
        role="melody",
        contour_apex=0.5,
        amp_mult=1.0,
        tempo_mult=1.0,
        metadata={"call_response_role": "follower"},
    )


def test_complementarity_on_two_voice_fixture():
    """Follower contour inversely correlates with leader (r < -0.3)."""
    rule = CallResponseRule(complement_strength=0.8)
    n = 10

    leader_parts: list[PerformedPart] = []
    for i in range(n):
        pos = i / (n - 1)
        amp = pos / 0.7 if pos <= 0.7 else 1.0 - (pos - 0.7) / 0.3
        amp = max(0.0, min(1.0, amp))
        leader_parts.append(
            PerformedPart(
                contour_apex=amp,
                amp_curve=amp,
                is_building=pos <= 0.7,
                is_pausing=False,
            )
        )

    follower_events = [_make_follower(i / (n - 1)) for i in range(n)]

    for event, leader in zip(follower_events, leader_parts):
        rule.apply(event, leader)

    leader_amps = [lp.amp_curve for lp in leader_parts]
    follower_amps = [e.amp_mult for e in follower_events]
    follower_apexes = [e.contour_apex for e in follower_events]

    assert _pearson(leader_amps, follower_amps) < -0.3
    assert _pearson(leader_amps, follower_apexes) < -0.3


def test_leader_role_unchanged():
    rule = CallResponseRule()
    event = Event(
        role="melody",
        amp_mult=1.0,
        contour_apex=0.5,
        metadata={"call_response_role": "leader"},
    )
    rule.apply(event, PerformedPart(amp_curve=0.8, is_building=True))
    assert event.amp_mult == 1.0
    assert event.contour_apex == 0.5


def test_solo_role_unchanged():
    rule = CallResponseRule()
    event = Event(
        role="melody",
        amp_mult=1.0,
        contour_apex=0.5,
        metadata={"call_response_role": "solo"},
    )
    rule.apply(event, PerformedPart(amp_curve=0.8, is_building=True))
    assert event.amp_mult == 1.0


def test_tacet_role_unchanged():
    rule = CallResponseRule()
    event = Event(
        role="melody",
        amp_mult=1.0,
        contour_apex=0.5,
        metadata={"call_response_role": "tacet"},
    )
    rule.apply(event, PerformedPart(amp_curve=0.8, is_building=True))
    assert event.amp_mult == 1.0


def test_grid_locked_role_skipped():
    rule = CallResponseRule()
    event = Event(
        role="drums",
        amp_mult=1.0,
        metadata={"call_response_role": "follower"},
    )
    rule.apply(event, PerformedPart(amp_curve=0.8, is_building=True))
    assert event.amp_mult == 1.0


def test_no_leader_part_no_change():
    rule = CallResponseRule()
    event = _make_follower()
    rule.apply(event, None)
    assert event.amp_mult == 1.0
    assert event.contour_apex == 0.5


def test_leader_build_reduces_follower_amp():
    rule = CallResponseRule(complement_strength=0.8)
    event = _make_follower()
    rule.apply(event, PerformedPart(amp_curve=0.9, is_building=True))
    assert event.amp_mult < 1.0


def test_leader_pause_boosts_follower_amp():
    rule = CallResponseRule(complement_strength=0.8)
    event = _make_follower()
    rule.apply(event, PerformedPart(amp_curve=0.1, is_pausing=True))
    assert event.amp_mult > 1.0


def test_alternative_cr_role_keys():
    rule = CallResponseRule(complement_strength=0.5)
    for key in ("cr_role", "ensemble_role"):
        event = Event(
            role="melody",
            amp_mult=1.0,
            contour_apex=0.5,
            metadata={key: "follower"},
        )
        rule.apply(event, PerformedPart(amp_curve=0.8, is_building=True))
        assert event.amp_mult < 1.0


def test_no_metadata_no_change():
    rule = CallResponseRule()
    event = Event(role="melody", amp_mult=1.0, contour_apex=0.5)
    rule.apply(event, PerformedPart(amp_curve=0.8, is_building=True))
    assert event.amp_mult == 1.0
