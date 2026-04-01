#!/usr/bin/env python3
"""Dashboard Generator for CypherClaw — Static HTML status dashboard."""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Import existing tools if possible, otherwise mock
try:
    from server_health import check_health
except ImportError:
    # Minimal mock if run outside tools/
    def check_health():
        return {"healthy": True, "checks": {}, "warnings": []}

try:
    from tamagotchi import PetManager, STAGE_NAMES
except ImportError:
    PetManager = None

# Paths
TOOLS_DIR = Path(__file__).parent
PROJECT_ROOT = TOOLS_DIR.parent
OBSERVATORY_DB = PROJECT_ROOT / ".promptclaw" / "observatory.db"
if not OBSERVATORY_DB.exists():
    # Fallback to home dir version or other common paths
    OBSERVATORY_DB = Path.home() / ".promptclaw" / "observatory.db"
SDP_STATE_DB = Path("/run/cypherclaw-tmp/workdir/cypherclaw-work/.sdp/state.db") # On server
# If running locally, check if we have a local copy or mock
if not SDP_STATE_DB.exists():
    SDP_STATE_DB = PROJECT_ROOT / ".sdp" / "state.db"

OUTPUT_PATH = Path("/var/www/html/index.html")
if os.access("/var/www/html", os.W_OK) is False:
    # Fallback for local testing or if no permission
    OUTPUT_PATH = PROJECT_ROOT / "dashboard.html"


HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="60">
    <title>CypherClaw | Dashboard</title>
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
        body {{
            background-color: var(--bg-color);
            color: var(--text-color);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            margin: 0;
            padding: 20px;
        }}
        .header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 10px;
            margin-bottom: 20px;
        }}
        .header h1 {{ margin: 0; font-size: 24px; color: var(--accent-color); }}
        .header .timestamp {{ font-size: 14px; color: #8b949e; }}
        
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 20px;
        }}
        
        .card {{
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 6px;
            padding: 15px;
        }}
        .card h2 {{
            margin-top: 0;
            font-size: 18px;
            border-bottom: 1px solid var(--border-color);
            padding-bottom: 8px;
            margin-bottom: 12px;
            display: flex;
            justify-content: space-between;
        }}
        
        .stat-row {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 8px;
            font-size: 14px;
        }}
        .stat-label {{ color: #8b949e; }}
        .stat-value {{ font-weight: 500; }}
        
        .status-pill {{
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 12px;
            font-weight: bold;
        }}
        .status-active {{ background-color: #238636; color: white; }}
        .status-inactive {{ background-color: #6e7681; color: white; }}
        .status-error {{ background-color: #da3633; color: white; }}
        
        .progress-container {{
            width: 100%;
            background-color: #30363d;
            border-radius: 4px;
            height: 12px;
            margin: 10px 0;
        }}
        .progress-bar {{
            height: 100%;
            background-color: var(--success-color);
            border-radius: 4px;
            transition: width 0.3s ease;
        }}
        
        .pet-grid {{
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 10px;
        }}
        .pet-card {{
            background-color: #0d1117;
            padding: 10px;
            border-radius: 4px;
            font-size: 12px;
        }}
        .pet-name {{ font-weight: bold; color: var(--accent-color); margin-bottom: 4px; }}
        
        .event-list {{
            font-size: 12px;
            list-style: none;
            padding: 0;
            margin: 0;
        }}
        .event-item {{
            padding: 6px 0;
            border-bottom: 1px solid var(--border-color);
        }}
        .event-time {{ color: #8b949e; margin-right: 8px; }}
        .event-type {{ font-weight: bold; color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>\U0001f980 CypherClaw Status</h1>
        <div class="timestamp">Last updated: {timestamp}</div>
    </div>
    
    <div class="grid">
        <!-- Server Vitals -->
        <div class="card">
            <h2>\u26a1 Server Vitals</h2>
            <div class="stat-row">
                <span class="stat-label">CPU Load</span>
                <span class="stat-value">{vitals_load}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Memory</span>
                <span class="stat-value">{vitals_memory}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Disk Usage</span>
                <span class="stat-value">{vitals_disk}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Temperature</span>
                <span class="stat-value">{vitals_temp}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Uptime</span>
                <span class="stat-value">{vitals_uptime}</span>
            </div>
        </div>
        
        <!-- Service Status -->
        <div class="card">
            <h2>\u2699\ufe0f Services</h2>
            {services_html}
        </div>
        
        <!-- Pipeline Progress -->
        <div class="card">
            <h2>\U0001f680 Pipeline Progress</h2>
            <div class="stat-row">
                <span class="stat-label">Total Tasks</span>
                <span class="stat-value">{pipeline_total}</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Complete</span>
                <span class="stat-value">{pipeline_complete}</span>
            </div>
            <div class="progress-container">
                <div class="progress-bar" style="width: {pipeline_percent}%"></div>
            </div>
            <div class="stat-row">
                <span class="stat-label">Status</span>
                <span class="stat-value">{pipeline_status}</span>
            </div>
        </div>
        
        <!-- Pet Status -->
        <div class="card">
            <h2>\U0001f43e Pet Status</h2>
            <div class="pet-grid">
                {pets_html}
            </div>
        </div>
        
        <!-- Recent Events -->
        <div class="card" style="grid-column: span 2;">
            <h2>\U0001f441\ufe0f Recent Events</h2>
            <ul class="event-list">
                {events_html}
            </ul>
        </div>
    </div>
</body>
</html>
"""


def get_pipeline_data():
    """Get task stats from sdp-cli state.db."""
    try:
        conn = sqlite3.connect(f"file:{SDP_STATE_DB}?mode=ro", uri=True)
        cursor = conn.cursor()
        cursor.execute("SELECT status, count(*) FROM tasks GROUP BY status")
        rows = cursor.fetchall()
        conn.close()
        
        stats = dict(rows)
        complete = stats.get("complete", 0)
        running = stats.get("running", 0)
        pending = stats.get("pending", 0) + stats.get("split", 0)
        total = complete + running + pending
        
        percent = round((complete / total * 100), 1) if total > 0 else 0
        status_text = "\u25b6\ufe0f Running" if running > 0 else "\u23f8\ufe0f Paused"
        
        return {
            "total": total,
            "complete": complete,
            "percent": percent,
            "status": status_text
        }
    except Exception as e:
        return {"total": "?", "complete": "?", "percent": 0, "status": f"Error: {e}"}


def get_event_data():
    """Get last 10 events from Observatory."""
    try:
        conn = sqlite3.connect(f"file:{OBSERVATORY_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events ORDER BY timestamp DESC LIMIT 10")
        rows = cursor.fetchall()
        conn.close()
        
        events = []
        for r in rows:
            ts = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")).strftime("%H:%M:%S")
            data = json.loads(r["data"])
            msg = data.get("text") or data.get("action_taken") or str(data)[:60]
            events.append({
                "time": ts,
                "type": r["event_type"],
                "message": msg
            })
        return events
    except Exception:
        return []


def generate():
    """Generate the HTML dashboard."""
    # 1. Health data
    health = check_health()
    checks = health["checks"]
    
    # 2. Services HTML
    services = ["daemon", "postgresql", "redis-server", "nginx", "docker", "sdp-cli", "ollama"]
    services_html = ""
    for svc in services:
        status = checks.get(svc, "unknown")
        pill_class = "status-active" if status == "active" or status == "running" else "status-inactive"
        if status == "failed" or status == "error":
            pill_class = "status-error"
        
        services_html += f"""
        <div class="stat-row">
            <span class="stat-label">{svc}</span>
            <span class="status-pill {pill_class}">{status}</span>
        </div>
        """
        
    # 3. Pipeline data
    pipe = get_pipeline_data()
    
    # 4. Pets HTML
    pets_html = ""
    if PetManager:
        manager = PetManager()
        for agent in ["claude", "codex", "gemini", "cypherclaw"]:
            pet = manager.get(agent)
            pets_html += f"""
            <div class="pet-card">
                <div class="pet-name">{agent.upper()} ({STAGE_NAMES[pet.stage]})</div>
                <div class="stat-row">
                    <span class="stat-label">Mood</span>
                    <span>{pet.mood}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Hunger</span>
                    <span>{pet.hunger}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Energy</span>
                    <span>{pet.energy}%</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">XP</span>
                    <span>{pet.xp}</span>
                </div>
            </div>
            """
            
    # 5. Events HTML
    events = get_event_data()
    events_html = ""
    for e in events:
        events_html += f"""
        <li class="event-item">
            <span class="event-time">[{e['time']}]</span>
            <span class="event-type">{e['type'].upper()}:</span>
            <span>{e['message']}</span>
        </li>
        """
        
    # Final render
    html = HTML_TEMPLATE.format(
        timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        vitals_load=checks.get("load", "?"),
        vitals_memory=checks.get("memory", "?"),
        vitals_disk=checks.get("disk_usage", "?"),
        vitals_temp=checks.get("temperature", "N/A"),
        vitals_uptime=checks.get("uptime", "?"),
        services_html=services_html,
        pipeline_total=pipe["total"],
        pipeline_complete=pipe["complete"],
        pipeline_percent=pipe["percent"],
        pipeline_status=pipe["status"],
        pets_html=pets_html,
        events_html=events_html
    )
    
    OUTPUT_PATH.write_text(html)
    print(f"Dashboard generated at {OUTPUT_PATH}")


if __name__ == "__main__":
    generate()
