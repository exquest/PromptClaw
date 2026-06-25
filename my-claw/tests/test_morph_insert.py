"""Tests for the global evolving-timbre morph insert (CypherClaw v2 macro morph)."""
import sys

sys.path.insert(0, "/home/user/cypherclaw/tools")

from senseweave.synthesis import morph_insert as mi


class FakeOSCClient:
    def __init__(self):
        self.messages = []

    def send_message(self, address, args):
        self.messages.append((address, list(args)))

    def messages_for(self, address):
        return [(a, args) for a, args in self.messages if a == address]


class TestSNewArgs:
    def test_targets_master_with_add_before(self):
        args = mi.morph_insert_s_new_args()
        assert args[0] == "sw_morph_insert"
        assert args[1] == mi.MORPH_INSERT_NODE_ID
        # addAction 3 == addBefore, target == master node.
        assert args[2] == 3
        assert args[3] == mi.MASTER_NODE_ID

    def test_default_mix_is_transparent_bypass(self):
        # Seeding must be audibly transparent on the live master chain.
        params = _params_from_args(mi.morph_insert_s_new_args())
        assert params["mix"] == 0.0

    def test_node_id_between_voices_and_master_distinct_from_spaces(self):
        # Above voice range (1000+), below master (99999), and not colliding
        # with the reverb-space ids 99001/99002.
        assert 1000 < mi.MORPH_INSERT_NODE_ID < mi.MASTER_NODE_ID
        assert mi.MORPH_INSERT_NODE_ID not in (99001, 99002)

    def test_overrides_apply_and_are_floats(self):
        params = _params_from_args(mi.morph_insert_s_new_args(mix=0.3, rate=0.05))
        assert params["mix"] == 0.3
        assert params["rate"] == 0.05
        # Every control value is coerced to float for scsynth.
        assert all(isinstance(v, float) for v in params.values())

    def test_custom_node_and_target(self):
        args = mi.morph_insert_s_new_args(99011, target_node=88888)
        assert args[1] == 99011
        assert args[3] == 88888


class TestSeed:
    def test_seed_sends_exactly_one_s_new(self):
        client = FakeOSCClient()
        mi.seed_morph_insert(client)
        s_new = client.messages_for("/s_new")
        assert len(s_new) == 1
        _, args = s_new[0]
        assert args[0] == "sw_morph_insert"
        assert args[2] == 3
        assert args[3] == mi.MASTER_NODE_ID

    def test_seed_passes_overrides(self):
        client = FakeOSCClient()
        mi.seed_morph_insert(client, mix=0.25)
        _, args = client.messages_for("/s_new")[0]
        assert _params_from_args(args)["mix"] == 0.25


def _params_from_args(args):
    # args = [name, node_id, addAction, target, k, v, k, v, ...]
    tail = args[4:]
    return {tail[i]: tail[i + 1] for i in range(0, len(tail), 2)}
