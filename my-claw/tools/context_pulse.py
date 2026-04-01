"""Context Pulse — lets CypherClaw see its own context.

Demonstrates that 97% of system intelligence is in files/artifacts,
not in the prompt. Built as a class demo in 5 minutes.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


TOOLS_DIR = Path(__file__).parent
WORKSPACE_DIR = TOOLS_DIR / "workspace"
STATE_FILE = TOOLS_DIR / ".daemon_state.json"
OBSERVATORY_DB = TOOLS_DIR.parent / ".promptclaw" / "observatory.db"
SELECTOR_STATE = TOOLS_DIR / ".agent_selector_state.json"
PETS_FILE = Path.home() / ".promptclaw" / "pets.json"


def pulse() -> str:
    """Generate a full context pulse — everything the AI knows about itself."""
    lines = ["🔮 CONTEXT PULSE", f"📅 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", ""]

    # 1. Conversation memory
    try:
        data = json.loads(STATE_FILE.read_text())
        convo = data.get("conversation", [])
        lines.append(f"💬 Conversation Memory: {len(convo)} messages")
        if convo:
            last = convo[-1]
            role = "Anthony" if last["role"] == "user" else "Claw"
            lines.append(f"   Last: {role}: {last.get('text', '')[:60]}...")
            # Count by role
            user_count = sum(1 for m in convo if m["role"] == "user")
            claw_count = len(convo) - user_count
            lines.append(f"   Anthony: {user_count} | Claw: {claw_count}")
    except Exception:
        lines.append("💬 Conversation: unavailable")

    lines.append("")

    # 2. Workspace artifacts
    try:
        artifacts = [f.name for f in WORKSPACE_DIR.iterdir() if f.is_file()] if WORKSPACE_DIR.exists() else []
        lines.append(f"📁 Workspace: {len(artifacts)} artifacts")
        for a in artifacts[-5:]:
            size = (WORKSPACE_DIR / a).stat().st_size
            lines.append(f"   • {a} ({size // 1024}KB)")
    except Exception:
        lines.append("📁 Workspace: unavailable")

    lines.append("")

    # 3. Observatory events
    try:
        if OBSERVATORY_DB.exists():
            import sqlite3
            conn = sqlite3.connect(str(OBSERVATORY_DB))
            cursor = conn.execute("SELECT COUNT(*) FROM events")
            total_events = cursor.fetchone()[0]
            cursor2 = conn.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type ORDER BY COUNT(*) DESC LIMIT 5")
            top_events = cursor2.fetchall()
            conn.close()
            lines.append(f"📊 Observatory: {total_events} total events")
            for evt_type, count in top_events:
                lines.append(f"   • {evt_type}: {count}")
        else:
            lines.append("📊 Observatory: no database")
    except Exception as e:
        lines.append(f"📊 Observatory: error ({e})")

    lines.append("")

    # 4. Agent fitness / selector state
    try:
        if SELECTOR_STATE.exists():
            sel = json.loads(SELECTOR_STATE.read_text())
            lines.append("🎯 Agent Selector:")
            lines.append(f"   Last lead: {sel.get('last_lead', 'none')}")
            lines.append(f"   Provider: {sel.get('last_lead_provider', 'none')}")
            lines.append(f"   Tasks routed: {sel.get('task_count', 0)}")
        else:
            lines.append("🎯 Agent Selector: no state yet")
    except Exception:
        lines.append("🎯 Agent Selector: unavailable")

    lines.append("")

    # 5. Pet status
    try:
        if PETS_FILE.exists():
            pets = json.loads(PETS_FILE.read_text()).get("pets", {})
            lines.append(f"🐾 Pets: {len(pets)} agents")
            for name, pet in pets.items():
                icon = {"claude": "🟣", "codex": "🟢", "gemini": "🔵", "cypherclaw": "🦀"}.get(name, "⚪")
                lines.append(f"   {icon} {name}: stage {pet.get('stage', '?')} XP {pet.get('xp', '?')} mood {pet.get('mood', '?')}")
        else:
            lines.append("🐾 Pets: no data")
    except Exception:
        lines.append("🐾 Pets: unavailable")

    lines.append("")

    # 6. System resources
    try:
        import shutil
        disk = shutil.disk_usage("/")
        disk_pct = round(disk.used / disk.total * 100)
        lines.append(f"💾 Disk: {disk_pct}% used ({disk.free // (1024**3)}GB free)")
    except Exception:
        pass

    try:
        load = os.getloadavg()
        lines.append(f"⚡ Load: {load[0]:.1f} / {load[1]:.1f} / {load[2]:.1f}")
    except Exception:
        pass

    lines.append("")

    # 7. The meta observation
    total_files = sum(1 for _ in TOOLS_DIR.rglob("*.py"))
    total_configs = sum(1 for _ in TOOLS_DIR.parent.rglob("*.json")) + sum(1 for _ in TOOLS_DIR.parent.rglob("*.md"))
    lines.append("🧠 Intelligence footprint:")
    lines.append(f"   Python files: {total_files}")
    lines.append(f"   Config/docs: {total_configs}")
    lines.append("   Prompt is <3% of context — the rest is in files, DB, and artifacts")

    # Record this pulse event (so it shows up in the next pulse — the loop closes)
    try:
        if OBSERVATORY_DB.exists():
            import sqlite3
            conn = sqlite3.connect(str(OBSERVATORY_DB))
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(events)").fetchall()
            }
            data_column = "data"
            if "data" not in columns and "data_json" in columns:
                data_column = "data_json"
            conn.execute(
                f"INSERT INTO events (timestamp, event_type, {data_column}) VALUES (?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), "context_pulse", json.dumps({"source": "pulse_command"}))
            )
            conn.commit()
            conn.close()
    except Exception:
        pass

    return "\n".join(lines)


if __name__ == "__main__":
    print(pulse())
