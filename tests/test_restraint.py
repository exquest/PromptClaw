from __future__ import annotations
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "my-claw", "tools"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cypherclaw.render.events import Event
from cypherclaw.render.rules.phrase_arch import PhraseArchRule

from senseweave.render.rules.silence_budget import SilenceBudgetRule
from test_silence_budget_rule import _scene, _step

def test_phrase_arch_restraint_neutral():
    event = Event(normalized_phrase_position=0.5, role="melody", metadata={"restraint": "0.0"})
    rule = PhraseArchRule(tempo_deviation_pct=4.0, amp_deviation_pct=4.0)
    rule.apply(event)
    assert event.metadata["phrase_arch_tempo_deviation_pct"] == "4.0"

def test_phrase_arch_restraint_near_flat():
    event = Event(normalized_phrase_position=0.5, role="melody", metadata={"restraint": "1.0"})
    rule = PhraseArchRule(tempo_deviation_pct=4.0, amp_deviation_pct=4.0)
    rule.apply(event)
    assert event.metadata["phrase_arch_tempo_deviation_pct"] == "0.0"
    
def test_silence_budget_restraint_neutral_vs_max():
    rule = SilenceBudgetRule(target_density=0.7, threshold=1.0)
    
    # dt=2.0 -> rest_budget = 1.4.
    steps = [
        _step(0, 2, phrase_id="p1", velocity=0.0),
        _step(2, 4, phrase_id="p2", velocity=0.8),
    ]
    steps[0].metadata["restraint"] = "0.0"
    scene_0 = _scene(steps)
    rendered_0 = rule.apply(scene_0, k=1.0, seeds=None, roles=None)
    out_0 = rendered_0.pattern.lanes[0].steps
    assert out_0[1].metadata.get("silence_budget_tacet") == "true"
    
    steps = [
        _step(0, 2, phrase_id="p1", velocity=0.0),
        _step(2, 4, phrase_id="p2", velocity=0.8),
    ]
    steps[0].metadata["restraint"] = "1.0"
    scene_1 = _scene(steps)
    rendered_1 = rule.apply(scene_1, k=1.0, seeds=None, roles=None)
    out_1 = rendered_1.pattern.lanes[0].steps
    assert out_1[1].metadata.get("silence_budget_tacet") is None
