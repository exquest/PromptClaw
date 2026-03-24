from __future__ import annotations

import json
import os
import re
import string
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path

def read_text(path: Path, default: str = "") -> str:
    if not path.exists():
        return default
    return path.read_text(encoding="utf-8")

def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content, encoding="utf-8")

def append_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)

def write_json(path: Path, data: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(make_json_safe(data), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))

def make_json_safe(data: Any) -> Any:
    if is_dataclass(data):
        return {key: make_json_safe(value) for key, value in asdict(data).items()}
    if isinstance(data, dict):
        return {str(key): make_json_safe(value) for key, value in data.items()}
    if isinstance(data, (list, tuple, set)):
        return [make_json_safe(item) for item in data]
    if isinstance(data, Path):
        return str(data)
    return data

def slugify(value: str, max_length: int = 48) -> str:
    allowed = string.ascii_letters + string.digits + "-_"
    cleaned = re.sub(r"\s+", "-", value.strip().lower())
    cleaned = "".join(ch for ch in cleaned if ch in allowed)
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-_")
    return cleaned[:max_length] or "run"

def render_string_template(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{" + key + "}", str(value))
    return rendered

def extract_json_object(text: str) -> str | None:
    # First: fenced JSON block
    fenced = re.search(r"```json\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fenced:
        return fenced.group(1)
    # Second: first balanced-looking object
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return None

def truncate(text: str, limit: int = 1200) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."

def parse_verdict(text: str) -> str | None:
    match = re.search(r"VERDICT\s*:\s*(PASS_WITH_NOTES|PASS|FAIL)", text, re.IGNORECASE)
    if not match:
        return None
    return match.group(1).upper()

def truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)

def executable_exists(program: str) -> bool:
    from shutil import which
    return which(program) is not None
