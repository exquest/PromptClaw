from __future__ import annotations

import hashlib
import struct


def derive_seed(root_seed: int, path: tuple[int, ...]) -> int:
    h = hashlib.sha256(struct.pack(">q", root_seed))
    for element in path:
        h.update(struct.pack(">q", element))
    return int.from_bytes(h.digest()[:4], "big")
