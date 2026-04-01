"""Bridge between CypherClaw and LifeImprover/LDP.

Provides access to LifeImprover's daily briefings, pipeline status,
energy patterns, and LDP introspection cycles.
"""

import json
import os
import subprocess
import urllib.request
import urllib.error
from dataclasses import dataclass, field
from pathlib import Path


LI_PROJECT = Path.home() / "Documents" / "programming" / "LifeImprover"
LI_BASE_URL = os.environ.get("LIFEIMPROVER_URL", "http://127.0.0.1:8000")
LI_API_URL = f"{LI_BASE_URL}/api/v1"


@dataclass
class BriefingResult:
    success: bool
    content: str
    error: str = ""


@dataclass
class PipelineStatus:
    leads: list[dict] = field(default_factory=list)
    total: int = 0
    by_stage: dict[str, int] = field(default_factory=dict)


class LifeImproverBridge:
    """Interface to LifeImprover's API and CLI."""

    def __init__(self):
        self.project_path = LI_PROJECT
        self.base_url = LI_BASE_URL
        self.api_url = LI_API_URL

    # --- Health ---
    def is_available(self) -> bool:
        """Check if LifeImprover is running."""
        try:
            req = urllib.request.Request(f"{self.base_url}/health/", headers={"User-Agent": "CypherClaw/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    # --- CLI Commands ---
    def _run_ldp(self, *args, timeout: int = 60) -> str:
        """Run an LDP CLI command and return output."""
        cmd = ["python", "manage.py", "ldp"] + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                cwd=str(self.project_path),
            )
            output = result.stdout.strip()
            if result.returncode != 0 and result.stderr:
                output += f"\n[stderr] {result.stderr.strip()}"
            return output or "(no output)"
        except subprocess.TimeoutExpired:
            return f"[ldp command timed out after {timeout}s]"
        except Exception as e:
            return f"[ldp error: {e}]"

    def _run_manage(self, *args, timeout: int = 60) -> str:
        """Run a Django manage.py command."""
        cmd = ["python", "manage.py"] + list(args)
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
                cwd=str(self.project_path),
            )
            return result.stdout.strip() or result.stderr.strip() or "(no output)"
        except subprocess.TimeoutExpired:
            return f"[command timed out after {timeout}s]"
        except Exception as e:
            return f"[error: {e}]"

    # --- API Calls ---
    def _api_get(self, endpoint: str) -> dict | list | None:
        """GET from LifeImprover API."""
        try:
            url = f"{self.api_url}/{endpoint.lstrip('/')}"
            req = urllib.request.Request(url, headers={"User-Agent": "CypherClaw/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read())
        except Exception:
            return None

    # --- Daily Briefing ---
    def get_daily_briefing(self) -> BriefingResult:
        """Get today's daily briefing."""
        output = self._run_ldp("today", timeout=30)
        if output.startswith("["):
            return BriefingResult(success=False, content="", error=output)
        return BriefingResult(success=True, content=output)

    # --- Weekly Review ---
    def get_weekly_review(self) -> BriefingResult:
        """Generate weekly review."""
        output = self._run_ldp("week", "--review", timeout=60)
        if output.startswith("["):
            return BriefingResult(success=False, content="", error=output)
        return BriefingResult(success=True, content=output)

    # --- Pipeline ---
    def get_pipeline_status(self) -> PipelineStatus:
        """Get current pipeline/leads status."""
        data = self._api_get("leads/")
        if data is None:
            # Fallback to CLI
            output = self._run_ldp("pipeline", "list", timeout=15)
            return PipelineStatus(leads=[], total=0, by_stage={"raw": output})

        leads = data if isinstance(data, list) else data.get("results", [])
        by_stage: dict[str, int] = {}
        for lead in leads:
            stage = lead.get("stage", lead.get("status", "unknown"))
            by_stage[stage] = by_stage.get(stage, 0) + 1

        return PipelineStatus(leads=leads, total=len(leads), by_stage=by_stage)

    # --- Energy Patterns ---
    def get_energy_patterns(self) -> dict:
        """Get recent energy ratings."""
        data = self._api_get("energy-ratings/")
        if data is None:
            return {"available": False}
        ratings = data if isinstance(data, list) else data.get("results", [])
        return {"available": True, "ratings": ratings[:14], "count": len(ratings)}

    # --- Initiatives ---
    def get_active_initiatives(self) -> list[dict]:
        """Get active initiatives/leads."""
        data = self._api_get("leads/?status=active")
        if data is None:
            return []
        return data if isinstance(data, list) else data.get("results", [])

    # --- Strategy Memos ---
    def get_latest_strategy_memo(self) -> str:
        """Get the most recent strategy memo."""
        data = self._api_get("strategy-memos/?ordering=-created_at&limit=1")
        if data and isinstance(data, list) and data:
            return data[0].get("content", "")
        if data and isinstance(data, dict) and data.get("results"):
            return data["results"][0].get("content", "")
        return ""

    # --- Introspection ---
    def run_review(self, review_type: str = "daily") -> str:
        """Run an LDP introspection review (daily, weekly, monthly, quarterly)."""
        return self._run_ldp("review", review_type, timeout=120)

    # --- SDP Integration ---
    def run_sdp(self, prd_path: str, initiative_id: str = "") -> str:
        """Run sdp-cli analysis via LifeImprover."""
        args = ["sdp", "run", "--prd", prd_path]
        if initiative_id:
            args.extend(["--initiative-id", initiative_id])
        return self._run_ldp(*args, timeout=300)

    # --- Income ---
    def log_income(self, stream: str, amount: float, date: str = "") -> str:
        """Log an income event."""
        args = ["income", "log", "--stream", stream, "--amount", str(amount)]
        if date:
            args.extend(["--date", date])
        return self._run_ldp(*args, timeout=15)

    # --- Content ---
    def get_content_calendar(self, period: str = "week") -> str:
        """Get content calendar."""
        return self._run_ldp("content", "calendar", f"--{period}", timeout=15)

    # --- Summary for Telegram ---
    def telegram_summary(self) -> str:
        """Generate a compact summary suitable for Telegram."""
        available = self.is_available()
        if not available:
            return "🔴 LifeImprover is offline\nStart it with: cd ~/Documents/programming/LifeImprover && python manage.py runserver"

        lines = ["🏠 LifeImprover Status\n"]

        # Daily briefing
        briefing = self.get_daily_briefing()
        if briefing.success:
            lines.append(f"📋 Today:\n{briefing.content[:500]}")
        else:
            lines.append(f"📋 Briefing unavailable: {briefing.error[:100]}")

        # Pipeline
        pipeline = self.get_pipeline_status()
        if pipeline.total > 0:
            stages = ", ".join(f"{k}: {v}" for k, v in pipeline.by_stage.items())
            lines.append(f"\n🎯 Pipeline: {pipeline.total} leads ({stages})")

        return "\n".join(lines)
