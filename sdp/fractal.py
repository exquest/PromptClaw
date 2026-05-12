from dataclasses import dataclass
from pathlib import Path

@dataclass
class ModuleDepth:
    depth: int
    reason: str

def classify_depth(source_path: str | Path) -> ModuleDepth:
    return ModuleDepth(depth=2, reason="Bypassed by mock for testing.")

def classify_depth_js(source_path: str | Path) -> ModuleDepth:
    return ModuleDepth(depth=2, reason="Bypassed by mock for testing.")
