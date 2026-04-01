#!/usr/bin/env python3
"""Dashboard Generator for CypherClaw."""

from __future__ import annotations

import html
import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, cast

try:
    from server_health import check_health as _imported_check_health
except ImportError:
    def _fallback_check_health() -> dict[str, object]:
        return {"healthy": True, "checks": {}, "warnings": []}

    check_health: Callable[[], dict[str, object]] = _fallback_check_health
else:
    check_health = cast(Callable[[], dict[str, object]], _imported_check_health)

try:
    from tamagotchi import PetManager as _ImportedPetManager, STAGE_NAMES as _IMPORTED_STAGE_NAMES
except ImportError:
    PetManager: type[Any] | None = None
    STAGE_NAMES: dict[int, str] = {}
else:
    PetManager = _ImportedPetManager
    STAGE_NAMES = dict(_IMPORTED_STAGE_NAMES)


TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TOOLS_DIR.parent
OBSERVATORY_DB = PROJECT_ROOT / ".promptclaw" / "observatory.db"
if not OBSERVATORY_DB.exists():
    OBSERVATORY_DB = Path.home() / ".promptclaw" / "observatory.db"
SDP_STATE_DB = Path("/run/cypherclaw-tmp/workdir/cypherclaw-work/.sdp/state.db")
if not SDP_STATE_DB.exists():
    SDP_STATE_DB = PROJECT_ROOT / ".sdp" / "state.db"
OUTPUT_PATH = Path("/var/www/html/index.html")
if not os.access("/var/www/html", os.W_OK):
    OUTPUT_PATH = PROJECT_ROOT / "dashboard.html"
DEFAULT_PETS_FILE = PROJECT_ROOT / ".promptclaw" / "pets.json"

CLASS_EMOJI = {
    "Scholar": "📚",
    "Engineer": "🔧",
    "Explorer": "🧭",
    "Artist": "🎨",
    "Guardian": "🛡️",
    "Diplomat": "🤝",
}

_FALLBACK_STAGE_NAMES = {
    1: "Baby",
    2: "Teen",
    3: "Adult",
    4: "Elite",
    5: "Master",
}


def _stage_for_xp(xp: int) -> int:
    if xp >= 1000:
        return 5
    if xp >= 500:
        return 4
    if xp >= 200:
        return 3
    if xp >= 50:
        return 2
    return 1


def _stage_name(stage: int) -> str:
    return STAGE_NAMES.get(stage) or _FALLBACK_STAGE_NAMES.get(stage, f"Stage {stage}")


def _bar_html(value: float, *, max_val: float = 100, color: str = "#58a6ff") -> str:
    pct = 0.0 if max_val <= 0 else max(0.0, min(float(value) / float(max_val) * 100.0, 100.0))
    pct_label = f"{pct:.1f}".rstrip("0").rstrip(".")
    return (
        '<div class="progress-container">'
        f'<div class="progress-bar" style="width:{pct_label}%; background:{html.escape(color)};"></div>'
        "</div>"
    )


def _service_pill_class(status: str) -> str:
    normalized = status.lower()
    if normalized in {"active", "running"}:
        return "status-active"
    if normalized in {"failed", "error"}:
        return "status-error"
    return "status-inactive"


def _format_timestamp(raw: str) -> str:
    if not raw:
        return "??:??"
    if len(raw) == 5 and ":" in raw:
        return raw
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return html.escape(raw)
    return dt.strftime("%H:%M")


def _format_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("type", "event"))
    data = event.get("data", {})

    if event_type == "heartbeat" and isinstance(data, dict):
        uptime = html.escape(str(data.get("uptime", "?")))
        io_pct = html.escape(str(data.get("io_pct", "?")))
        load = html.escape(str(data.get("load_1m", "?")))
        return f"Heartbeat {uptime} | IO {io_pct}% | Load {load}"
    if event_type == "health_check" and isinstance(data, dict):
        healthy = bool(data.get("healthy"))
        warnings = html.escape(str(data.get("warnings", 0)))
        status = "Healthy" if healthy else "UNHEALTHY"
        return f"{status} | warnings: {warnings}"
    if event_type == "task_result" and isinstance(data, dict):
        agent = html.escape(str(data.get("agent", "?")))
        success = "success" if data.get("success") else "failure"
        return f"{agent} {success}"

    if isinstance(data, dict):
        rendered = json.dumps(data, sort_keys=True)
    else:
        rendered = str(data)
    return html.escape(rendered)


def _connect_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def collect_pipeline(path: Path) -> dict[str, int]:
    empty = {"total": 0, "complete": 0, "pending": 0, "running": 0, "blocked": 0, "skipped": 0, "split": 0}
    if not path.exists():
        return empty
    try:
        conn = _connect_readonly(path)
        cursor = conn.cursor()
        cursor.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")
        rows = cursor.fetchall()
        conn.close()
    except sqlite3.Error:
        return empty

    stats = {str(status): int(count) for status, count in rows}
    result = dict(empty)
    for key in result:
        result[key] = int(stats.get(key, 0))
    result["total"] = sum(int(count) for count in stats.values())
    return result


def get_pipeline_data() -> dict[str, Any]:
    pipeline = collect_pipeline(SDP_STATE_DB)
    pending_total = pipeline["pending"] + pipeline["split"]
    total_for_progress = pipeline["complete"] + pipeline["running"] + pending_total
    percent = round((pipeline["complete"] / total_for_progress * 100), 1) if total_for_progress else 0
    status_text = "▶️ Running" if pipeline["running"] > 0 else "⏸️ Paused"
    return {"total": total_for_progress, "complete": pipeline["complete"], "percent": percent, "status": status_text}


def collect_events(path: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        conn = _connect_readonly(path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT event_type, timestamp, data FROM events ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
    except sqlite3.Error:
        return []

    events: list[dict[str, Any]] = []
    for row in rows:
        raw_data = row["data"]
        if isinstance(raw_data, str):
            try:
                data = json.loads(raw_data)
            except json.JSONDecodeError:
                data = raw_data
        else:
            data = raw_data
        events.append({"type": str(row["event_type"]), "timestamp": str(row["timestamp"]), "data": data})
    return events


def get_event_data() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for event in collect_events(OBSERVATORY_DB, limit=10):
        data = event.get("data", {})
        message = ""
        if isinstance(data, dict):
            message = str(data.get("text") or data.get("action_taken") or _format_event(event))
        else:
            message = str(data)
        items.append(
            {
                "time": _format_timestamp(str(event.get("timestamp", ""))) + ":00" if len(_format_timestamp(str(event.get("timestamp", "")))) == 5 else _format_timestamp(str(event.get("timestamp", ""))),
                "type": str(event.get("type", "")),
                "message": message,
            }
        )
    return items


def collect_pet_classes() -> dict[str, tuple[str, int]]:
    return {}


def collect_pets(pets_file: Path, *, class_overrides: dict[str, tuple[str, int]]) -> list[dict[str, Any]]:
    if not pets_file.exists():
        return []
    try:
        payload = json.loads(pets_file.read_text())
    except (OSError, json.JSONDecodeError):
        return []

    pets = payload.get("pets", {})
    if not isinstance(pets, dict):
        return []

    rendered: list[dict[str, Any]] = []
    for agent, raw_pet in pets.items():
        if not isinstance(raw_pet, dict):
            continue
        xp = int(raw_pet.get("xp", 0))
        stage = int(raw_pet.get("stage", _stage_for_xp(xp)))
        completed = int(raw_pet.get("tasks_completed", 0))
        failed = int(raw_pet.get("tasks_failed", 0))
        total = completed + failed
        success_rate = int(completed / total * 100) if total else None
        class_name: str | None = None
        class_level: int | None = None
        if agent in class_overrides:
            class_name, class_level = class_overrides[agent]
        rendered.append(
            {
                "agent": str(agent),
                "stage": stage,
                "stage_name": _stage_name(stage),
                "xp": xp,
                "mood": int(raw_pet.get("mood", 0)),
                "energy": int(raw_pet.get("energy", 0)),
                "hunger": int(raw_pet.get("hunger", 0)),
                "state": str(raw_pet.get("state", "idle")),
                "tasks_completed": completed,
                "tasks_failed": failed,
                "success_rate": success_rate,
                "class_name": class_name,
                "class_level": class_level,
            }
        )
    return rendered


def _runtime_pets() -> list[dict[str, Any]]:
    if PetManager is None:
        return []
    manager = PetManager()
    pets: list[dict[str, Any]] = []
    for agent in ("claude", "codex", "gemini", "cypherclaw"):
        pet = manager.get(agent)
        stage = int(getattr(pet, "stage", 1))
        pets.append(
            {
                "agent": agent,
                "stage": stage,
                "stage_name": _stage_name(stage),
                "xp": int(getattr(pet, "xp", 0)),
                "mood": int(getattr(pet, "mood", 0)),
                "energy": int(getattr(pet, "energy", 0)),
                "hunger": int(getattr(pet, "hunger", 0)),
                "state": str(getattr(pet, "state", "idle")),
                "tasks_completed": int(getattr(pet, "tasks_completed", 0)),
                "tasks_failed": int(getattr(pet, "tasks_failed", 0)),
                "success_rate": None,
                "class_name": None,
                "class_level": None,
            }
        )
    return pets


def _format_vitals(vitals: dict[str, Any]) -> dict[str, str]:
    load = vitals.get("load", (0, 0, 0))
    if isinstance(load, tuple):
        load_text = " / ".join(str(item) for item in load)
    else:
        load_text = str(load)
    temp = vitals.get("temp_c")
    temp_text = "N/A" if temp is None else f"{temp}C"
    mem_value = vitals.get("mem_pct", 0)
    disk_value = vitals.get("disk_pct", 0)
    if isinstance(mem_value, (int, float)):
        memory_text = f"{mem_value}% used"
    else:
        memory_text = str(mem_value)
    if isinstance(disk_value, (int, float)):
        disk_text = f"{disk_value}%"
    else:
        disk_text = str(disk_value)
    return {
        "uptime": html.escape(str(vitals.get("uptime", "?"))),
        "load": html.escape(load_text),
        "memory": html.escape(memory_text),
        "disk": html.escape(disk_text),
        "temp": html.escape(temp_text),
    }


def generate_html(
    *,
    vitals: dict[str, Any],
    services: list[dict[str, str]],
    pipeline: dict[str, Any],
    pets: list[dict[str, Any]],
    events: list[dict[str, Any]],
    quality: dict[str, Any],
    now: datetime | None = None,
) -> str:
    current_time = now or datetime.now(timezone.utc)
    vitals_text = _format_vitals(vitals)
    total = int(pipeline.get("total", 0))
    complete = int(pipeline.get("complete", 0))
    percent = round((complete / total * 100), 1) if total else 0.0

    services_html = "".join(
        '<div class="stat-row">'
        f'<span class="stat-label">{html.escape(service["name"])}</span>'
        f'<span class="status-pill {_service_pill_class(service["status"])}">{html.escape(service["status"])}</span>'
        "</div>"
        for service in services
    )

    pet_blocks: list[str] = []
    for pet in pets:
        class_name = str(pet.get("class_name") or "Unclassed")
        class_level = pet.get("class_level")
        level_text = f"Lv.{class_level}" if class_level is not None else "-"
        pet_blocks.append(
            '<div class="pet-card">'
            f'<div class="pet-name">{html.escape(str(pet["agent"]).upper())} ({html.escape(str(pet["stage_name"]))})</div>'
            f'<div class="stat-row"><span class="stat-label">XP</span><span>{html.escape(str(pet["xp"]))}</span></div>'
            f'<div class="stat-row"><span class="stat-label">Mood</span><span>{html.escape(str(pet["mood"]))}%</span></div>'
            f'<div class="stat-row"><span class="stat-label">Energy</span><span>{html.escape(str(pet["energy"]))}%</span></div>'
            f'<div class="stat-row"><span class="stat-label">Hunger</span><span>{html.escape(str(pet["hunger"]))}%</span></div>'
            f'<div class="stat-row"><span class="stat-label">Class</span><span>{html.escape(class_name)}</span></div>'
            f'<div class="stat-row"><span class="stat-label">Level</span><span>{html.escape(level_text)}</span></div>'
            "</div>"
        )
    pets_html = "".join(pet_blocks)

    events_html = "".join(
        '<li class="event-item">'
        f'<span class="event-time">[{_format_timestamp(str(event.get("timestamp", "")))}]</span> '
        f'<span class="event-type">{html.escape(str(event.get("type", "")).upper())}:</span> '
        f'<span>{_format_event(event)}</span>'
        "</li>"
        for event in events
    )

    quality_rows = "".join(
        '<div class="stat-row">'
        f'<span class="stat-label">{html.escape(str(key).replace("_", " ").title())}</span>'
        f'<span class="stat-value">{html.escape(str(value))}</span>'
        "</div>"
        for key, value in quality.items()
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="refresh" content="60">
  <title>CypherClaw Dashboard</title>
  <style>
    :root {{
      --bg-color: #0d1117;
      --card-bg: #161b22;
      --text-color: #c9d1d9;
      --accent-color: #58a6ff;
      --success-color: #3fb950;
      --warning-color: #d29922;
      --error-color: #f85149;
      --border-color: #30363d;
    }}
    body {{ background-color: var(--bg-color); color: var(--text-color); font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; margin: 0; padding: 20px; }}
    .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 10px; margin-bottom: 20px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
    .card {{ background-color: var(--card-bg); border: 1px solid var(--border-color); border-radius: 6px; padding: 15px; }}
    .card h2 {{ margin-top: 0; }}
    .stat-row {{ display: flex; justify-content: space-between; margin-bottom: 8px; font-size: 14px; gap: 12px; }}
    .stat-label {{ color: #8b949e; }}
    .status-pill {{ padding: 2px 8px; border-radius: 10px; font-size: 12px; font-weight: bold; }}
    .status-active {{ background-color: #238636; color: white; }}
    .status-inactive {{ background-color: #6e7681; color: white; }}
    .status-error {{ background-color: #da3633; color: white; }}
    .progress-container {{ width: 100%; background-color: #30363d; border-radius: 4px; height: 12px; margin: 10px 0; }}
    .progress-bar {{ height: 100%; border-radius: 4px; }}
    .pet-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
    .pet-card {{ background-color: #0d1117; padding: 10px; border-radius: 4px; font-size: 12px; }}
    .pet-name {{ font-weight: bold; color: var(--accent-color); margin-bottom: 4px; }}
    .event-list {{ font-size: 12px; list-style: none; padding: 0; margin: 0; }}
    .event-item {{ padding: 6px 0; border-bottom: 1px solid var(--border-color); }}
    .event-time {{ color: #8b949e; margin-right: 8px; }}
    .event-type {{ font-weight: bold; color: #f2f2f2; }}
  </style>
</head>
<body>
  <div class="header">
    <h1>🦀 CypherClaw Status</h1>
    <div class="timestamp">Last updated: {current_time.strftime("%Y-%m-%d %H:%M:%S %Z")}</div>
  </div>
  <div class="grid">
    <div class="card">
      <h2>⚡ Server Vitals</h2>
      <div class="stat-row"><span class="stat-label">Uptime</span><span>{vitals_text["uptime"]}</span></div>
      <div class="stat-row"><span class="stat-label">CPU Load</span><span>{vitals_text["load"]}</span></div>
      <div class="stat-row"><span class="stat-label">Memory</span><span>{vitals_text["memory"]}</span></div>
      <div class="stat-row"><span class="stat-label">Disk Usage</span><span>{vitals_text["disk"]}</span></div>
      <div class="stat-row"><span class="stat-label">Temperature</span><span>{vitals_text["temp"]}</span></div>
    </div>
    <div class="card">
      <h2>⚙️ Services</h2>
      {services_html}
    </div>
    <div class="card">
      <h2>🚀 Pipeline Progress</h2>
      <div class="stat-row"><span class="stat-label">Progress</span><span>{complete}/{total}</span></div>
      <div class="stat-row"><span class="stat-label">Complete</span><span>{percent:.1f}%</span></div>
      {_bar_html(complete, max_val=total or 1, color="#3fb950")}
      <div class="stat-row"><span class="stat-label">Running</span><span>{html.escape(str(pipeline.get("running", 0)))}</span></div>
      <div class="stat-row"><span class="stat-label">Pending</span><span>{html.escape(str(pipeline.get("pending", 0)))}</span></div>
      <div class="stat-row"><span class="stat-label">Blocked</span><span>{html.escape(str(pipeline.get("blocked", 0)))}</span></div>
      <div class="stat-row"><span class="stat-label">Skipped</span><span>{html.escape(str(pipeline.get("skipped", 0)))}</span></div>
    </div>
    <div class="card">
      <h2>🐾 Pet Status</h2>
      <div class="pet-grid">{pets_html}</div>
    </div>
    <div class="card">
      <h2>✅ Quality</h2>
      {quality_rows or '<div class="stat-row"><span class="stat-label">Status</span><span>No quality data</span></div>'}
    </div>
    <div class="card" style="grid-column: span 2;">
      <h2>👁️ Recent Events</h2>
      <ul class="event-list">{events_html}</ul>
    </div>
  </div>
</body>
</html>
"""


def _services_from_health(health: dict[str, Any]) -> list[dict[str, str]]:
    checks = health.get("checks", {})
    if not isinstance(checks, dict):
        return []
    labels = [
        ("daemon", "Daemon"),
        ("postgresql", "PostgreSQL"),
        ("redis-server", "Redis"),
        ("nginx", "Nginx"),
        ("docker", "Docker"),
        ("sdp-cli", "SDP CLI"),
        ("ollama", "Ollama"),
    ]
    return [{"name": label, "status": str(checks.get(key, "unknown"))} for key, label in labels]


def _vitals_from_health(health: dict[str, Any]) -> dict[str, Any]:
    checks = health.get("checks", {})
    if not isinstance(checks, dict):
        return {}
    return {
        "uptime": checks.get("uptime", "?"),
        "load": checks.get("load", (0, 0, 0)),
        "mem_pct": checks.get("memory", "0"),
        "disk_pct": checks.get("disk_usage", "0"),
        "temp_c": checks.get("temperature"),
    }


def generate_dashboard(
    *,
    output: Path = OUTPUT_PATH,
    sdp_db: Path = SDP_STATE_DB,
    obs_db: Path = OBSERVATORY_DB,
    pets_file: Path = DEFAULT_PETS_FILE,
    now: datetime | None = None,
) -> Path:
    health = check_health()
    services = _services_from_health(health)
    pipeline = collect_pipeline(sdp_db)
    pets = collect_pets(pets_file, class_overrides=collect_pet_classes())
    events = collect_events(obs_db, limit=10)
    html_text = generate_html(
        vitals=_vitals_from_health(health),
        services=services,
        pipeline=pipeline,
        pets=pets,
        events=events,
        quality={},
        now=now,
    )
    output.write_text(html_text)
    return output


def generate() -> None:
    health = check_health()
    services = _services_from_health(health)
    pipeline = collect_pipeline(SDP_STATE_DB)
    pipeline["pending"] = int(pipeline.get("pending", 0)) + int(pipeline.get("split", 0))
    pipeline["total"] = pipeline["complete"] + pipeline["running"] + pipeline["pending"] + pipeline["blocked"] + pipeline["skipped"]
    events = collect_events(OBSERVATORY_DB, limit=10)
    pets = _runtime_pets()
    html_text = generate_html(
        vitals=_vitals_from_health(health),
        services=services,
        pipeline=pipeline,
        pets=pets,
        events=events,
        quality={},
    )
    OUTPUT_PATH.write_text(html_text)
    print(f"Dashboard generated at {OUTPUT_PATH}")


if __name__ == "__main__":
    generate()
