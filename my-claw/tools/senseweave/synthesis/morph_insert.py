"""Global evolving-timbre morph insert (CypherClaw v2 §11 macro morph).

A single persistent DSP node (`sw_morph_insert`) placed immediately before the
master node. It reads the summed main bus (dry voices + reverb-space returns),
crossfades the whole ensemble between a warm and a bright tone color, and writes
the result back in place. A free-running slow LFO inside the synth sweeps the
morph so the entire mix's timbre breathes over minutes.

The node id sits above the voice range (1000+) and below the master node
(99999), distinct from the reverb-space ids (99001/99002), so ``addBefore`` the
master resolves cleanly — the same idiom as :mod:`reverb_spaces`.

LIVE-SAFE: ``mix`` defaults to 0.0, an exact passthrough, so seeding the node is
audibly transparent. Intensity is brought up afterwards with
``/n_set <node> mix <x>`` while listening.
"""

# Above voices (1000+, see VoiceManager) and below the master node (99999),
# distinct from the reverb spaces (99001/99002).
MORPH_INSERT_NODE_ID = 99010
MASTER_NODE_ID = 99999

# scsynth /s_new addAction: 3 == addBefore the target node.
ADD_BEFORE = 3

DEFAULT_PARAMS = {
    "mix": 0.0,         # wet amount; 0.0 == transparent bypass (safe seed)
    "rate": 0.018,      # morph LFO frequency in Hz (~55 s period)
    "depth": 1.0,       # fraction of the [0,1] morph range the sweep covers
    "bias": 0.0,        # center offset added to the swept morph position
    "fc": 900.0,        # low/high crossover frequency (Hz) for the tilt
    "warm_hi": 0.5,     # high-band gain on the warm side (softens highs)
    "bright_lo": 0.8,   # low-band gain on the bright side (trims lows)
    "bright_hi": 1.18,  # high-band gain on the bright side (lifts sparse highs)
}


def morph_insert_s_new_args(
    node_id: int = MORPH_INSERT_NODE_ID,
    *,
    target_node: int = MASTER_NODE_ID,
    **overrides: float,
) -> list:
    """Build the ``/s_new`` args that seed the morph insert before the master.

    addAction 3 (addBefore) places the insert immediately before ``target_node``
    so it processes the summed bus after every voice and reverb space has
    written, and just before the master reads it.
    """
    params = dict(DEFAULT_PARAMS)
    params.update(overrides)
    args = ["sw_morph_insert", node_id, ADD_BEFORE, target_node]
    for key, value in params.items():
        args += [key, float(value)]
    return args


def seed_morph_insert(
    client,
    *,
    node_id: int = MORPH_INSERT_NODE_ID,
    target_node: int = MASTER_NODE_ID,
    **overrides: float,
) -> None:
    """Spawn the persistent morph-insert synth before the master.

    Call this AFTER the master node exists so ``addBefore(target_node)``
    resolves. Seeds with ``mix=0.0`` (transparent) unless overridden.
    """
    client.send_message(
        "/s_new",
        morph_insert_s_new_args(node_id, target_node=target_node, **overrides),
    )
