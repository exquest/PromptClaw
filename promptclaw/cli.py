from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from .asset_bus import SchemaError, validate_request
from .bootstrap import bootstrap_project, init_project
from .config import load_config
from .diagnostics import diagnose, format_diagnosis
from .doctor import run_doctor
from .orchestrator import PromptClawOrchestrator
from .pal_agent import (
    DEFAULT_ACTION_TASK,
    DEFAULT_PHASE2_READINESS_TASK,
    DEFAULT_RESTART_VALIDATION_TASK,
    DEFAULT_SHUTDOWN_AUDIT_TASK,
    DEFAULT_SLOW_INFERENCE_DIAGNOSIS_TASK,
    DEFAULT_TRIAGE_TASK,
    load_pal_action_results,
    run_pal_ops_actions,
    run_pal_ops_triage,
    run_pal_phase2_readiness_report,
    run_pal_restart_validation,
    run_pal_shutdown_audit,
    run_pal_slow_inference_diagnosis,
)
from .pal_client import PALRouterClient
from .pal_deploy import (
    apply_pal_deployment_changes,
    build_pal_deploy_plan,
    compute_pal_cost_burn,
    default_pal_deploy_apply_backup_id,
    format_pal_cost_burn,
    format_pal_deploy_apply_result,
    format_pal_deploy_plan,
    format_pal_deploy_rollback_result,
    load_pal_deployment_backup,
    load_pal_deployment_manifest,
    load_pal_remote_inventory_snapshot,
    rollback_pal_deployment_backup,
)
from .pal_knowledge import query_pal_knowledge_index, write_pal_knowledge_index
from .pal_smoke import (
    format_baseline_summary,
    load_smoke_reports,
    run_pal_smoke,
    summarize_smoke_reports,
    write_smoke_report,
)
from .paths import ProjectPaths
from .state_store import StateStore
from .ui import banner, status_line
from .utils import read_text
from .wizard import run_startup_wizard


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="promptclaw", description="PromptClaw multi-agent orchestrator")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a new PromptClaw project")
    init_parser.add_argument("path", type=Path)
    init_parser.add_argument("--name", default="New PromptClaw")
    init_parser.add_argument("--no-wizard", action="store_true", help="Skip the interactive startup wizard")

    wizard_parser = subparsers.add_parser("wizard", help="Run the playful startup wizard")
    wizard_parser.add_argument("project_root", type=Path)

    doctor_parser = subparsers.add_parser("doctor", help="Validate a PromptClaw project")
    doctor_parser.add_argument("project_root", type=Path)

    bootstrap_parser = subparsers.add_parser("bootstrap", help="Run the bootstrap task from starter prompts")
    bootstrap_parser.add_argument("project_root", type=Path)

    run_parser = subparsers.add_parser("run", help="Run a task")
    run_parser.add_argument("project_root", type=Path)
    group = run_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--task-file", type=Path)
    group.add_argument("--task")

    resume_parser = subparsers.add_parser("resume", help="Resume an ambiguous run")
    resume_parser.add_argument("project_root", type=Path)
    resume_parser.add_argument("--run-id", required=True)
    resume_parser.add_argument("--answer", required=True)

    status_parser = subparsers.add_parser("status", help="Show project status")
    status_parser.add_argument("project_root", type=Path)
    status_parser.add_argument("--run-id")

    show_config_parser = subparsers.add_parser("show-config", help="Print resolved config")
    show_config_parser.add_argument("project_root", type=Path)

    pal_parser = subparsers.add_parser("pal", help="PAL router commands")
    pal_sub = pal_parser.add_subparsers(dest="pal_command", required=True)

    pal_health_parser = pal_sub.add_parser("health", help="Check the configured PAL router")
    pal_health_parser.add_argument("project_root", type=Path)

    pal_query_parser = pal_sub.add_parser("query", help="Send a prompt to the configured PAL router")
    pal_query_parser.add_argument("project_root", type=Path)
    pal_query_parser.add_argument("--prompt", required=True)
    pal_query_parser.add_argument("--system")
    pal_query_parser.add_argument("--model")
    pal_query_parser.add_argument("--temperature", type=float, default=0.7)
    pal_query_parser.add_argument("--text", action="store_true", help="Print only the response text")

    pal_smoke_parser = pal_sub.add_parser("smoke", help="Run the PAL restart smoke suite")
    pal_smoke_parser.add_argument("project_root", type=Path)
    pal_smoke_parser.add_argument("--output", type=Path)
    pal_smoke_parser.add_argument("--json", action="store_true", help="Print the full smoke report JSON")

    pal_baseline_parser = pal_sub.add_parser("baseline", help="Summarize saved PAL smoke reports")
    pal_baseline_parser.add_argument("project_root", type=Path)
    pal_baseline_parser.add_argument("--json", action="store_true", help="Print baseline summary JSON")

    pal_diagnose_parser = pal_sub.add_parser("diagnose", help="Run read-only PAL diagnosis workflows")
    pal_diagnose_sub = pal_diagnose_parser.add_subparsers(dest="pal_diagnose_command", required=True)
    pal_diagnose_slow_parser = pal_diagnose_sub.add_parser(
        "slow-inference",
        help="Diagnose PAL slow inference without mutating infrastructure",
    )
    pal_diagnose_slow_parser.add_argument("project_root", type=Path)
    pal_diagnose_slow_parser.add_argument(
        "--task",
        default=DEFAULT_SLOW_INFERENCE_DIAGNOSIS_TASK,
        help="Operator task for the slow-inference diagnosis",
    )
    pal_diagnose_slow_parser.add_argument("--json", action="store_true", help="Print diagnosis result JSON")

    pal_validate_parser = pal_sub.add_parser("validate", help="Run read-only PAL validation workflows")
    pal_validate_sub = pal_validate_parser.add_subparsers(dest="pal_validate_command", required=True)
    pal_validate_restart_parser = pal_validate_sub.add_parser(
        "restart",
        help="Validate PAL health after restart or instance boot",
    )
    pal_validate_restart_parser.add_argument("project_root", type=Path)
    pal_validate_restart_parser.add_argument(
        "--task",
        default=DEFAULT_RESTART_VALIDATION_TASK,
        help="Operator task for restart validation",
    )
    pal_validate_restart_parser.add_argument("--json", action="store_true", help="Print validation result JSON")

    pal_audit_parser = pal_sub.add_parser("audit", help="Run read-only PAL audit workflows")
    pal_audit_sub = pal_audit_parser.add_subparsers(dest="pal_audit_command", required=True)
    pal_audit_shutdown_parser = pal_audit_sub.add_parser(
        "shutdown",
        help="Audit PAL auto-shutdown config, override state, cron, and logs",
    )
    pal_audit_shutdown_parser.add_argument("project_root", type=Path)
    pal_audit_shutdown_parser.add_argument(
        "--task",
        default=DEFAULT_SHUTDOWN_AUDIT_TASK,
        help="Operator task for shutdown audit",
    )
    pal_audit_shutdown_parser.add_argument("--json", action="store_true", help="Print audit result JSON")

    pal_report_parser = pal_sub.add_parser("report", help="Run read-only PAL report workflows")
    pal_report_sub = pal_report_parser.add_subparsers(dest="pal_report_command", required=True)
    pal_report_phase2_parser = pal_report_sub.add_parser(
        "phase2-readiness",
        help="Score Phase 2 prerequisites without exposing execution actions",
    )
    pal_report_phase2_parser.add_argument("project_root", type=Path)
    pal_report_phase2_parser.add_argument(
        "--task",
        default=DEFAULT_PHASE2_READINESS_TASK,
        help="Operator task for Phase 2 readiness reporting",
    )
    pal_report_phase2_parser.add_argument("--json", action="store_true", help="Print report result JSON")

    pal_deploy_parser = pal_sub.add_parser("deploy", help="PAL deployment dry-run commands")
    pal_deploy_sub = pal_deploy_parser.add_subparsers(dest="pal_deploy_command", required=True)
    pal_deploy_plan_parser = pal_deploy_sub.add_parser(
        "plan",
        help="Print a dry-run PAL deployment plan without remote writes",
    )
    pal_deploy_plan_parser.add_argument("project_root", type=Path)
    pal_deploy_plan_parser.add_argument(
        "--manifest",
        type=Path,
        help="Override the deployment manifest path; relative paths resolve under PROJECT_ROOT",
    )
    pal_deploy_plan_parser.add_argument(
        "--remote-inventory",
        type=Path,
        help="Local JSON remote inventory snapshot; no SSH or live remote probe is performed",
    )
    pal_deploy_plan_parser.add_argument("--json", action="store_true", help="Print deploy plan JSON")
    pal_deploy_apply_parser = pal_deploy_sub.add_parser(
        "apply",
        help="Apply PAL deployment changes to a local fake remote inventory after approval",
    )
    pal_deploy_apply_parser.add_argument("project_root", type=Path)
    pal_deploy_apply_parser.add_argument(
        "--manifest",
        type=Path,
        help="Override the deployment manifest path; relative paths resolve under PROJECT_ROOT",
    )
    pal_deploy_apply_parser.add_argument(
        "--remote-inventory",
        type=Path,
        required=True,
        help="Local JSON fake remote inventory snapshot to update; no SSH is performed",
    )
    pal_deploy_apply_parser.add_argument(
        "--approve-apply",
        action="store_true",
        help="Approve writing the supplied fake remote inventory snapshot",
    )
    pal_deploy_apply_parser.add_argument(
        "--backup-id",
        help="Override the local backup artifact id for deterministic tests",
    )
    pal_deploy_apply_parser.add_argument("--json", action="store_true", help="Print deploy apply JSON")
    pal_deploy_rollback_parser = pal_deploy_sub.add_parser(
        "rollback",
        help="Restore a PAL deploy backup into a local fake remote inventory after approval",
    )
    pal_deploy_rollback_parser.add_argument("project_root", type=Path)
    pal_deploy_rollback_parser.add_argument(
        "--manifest",
        type=Path,
        help="Accepted for deploy CLI consistency; rollback metadata comes from the backup artifact",
    )
    pal_deploy_rollback_parser.add_argument(
        "--remote-inventory",
        type=Path,
        required=True,
        help="Local JSON fake remote inventory snapshot to update; no SSH is performed",
    )
    pal_deploy_rollback_parser.add_argument(
        "--backup-id",
        required=True,
        help="Local backup artifact id under .promptclaw/pal-deploy/backups",
    )
    pal_deploy_rollback_parser.add_argument(
        "--approve-rollback",
        action="store_true",
        help="Approve writing restored backup content to the supplied fake remote inventory snapshot",
    )
    pal_deploy_rollback_parser.add_argument("--json", action="store_true", help="Print deploy rollback JSON")

    pal_cost_parser = pal_sub.add_parser(
        "cost",
        help="Print hourly, daily, and monthly PAL burn estimates",
    )
    pal_cost_parser.add_argument(
        "--hourly-rate-usd",
        type=float,
        required=True,
        help="Hourly USD rate for the PAL instance (e.g. Vast.ai listing price)",
    )
    pal_cost_parser.add_argument(
        "--vast-instance-id",
        help="Optional Vast.ai instance id to include in the burn summary",
    )
    pal_cost_parser.add_argument("--json", action="store_true", help="Print burn summary JSON")

    pal_kb_parser = pal_sub.add_parser("kb", help="PAL local knowledge-base commands")
    pal_kb_sub = pal_kb_parser.add_subparsers(dest="pal_kb_command", required=True)
    pal_kb_build_parser = pal_kb_sub.add_parser("build", help="Build the local PAL knowledge index")
    pal_kb_build_parser.add_argument("project_root", type=Path)
    pal_kb_build_parser.add_argument("--max-chars", type=int, default=2000)
    pal_kb_build_parser.add_argument("--output", type=Path)
    pal_kb_build_parser.add_argument("--json", action="store_true", help="Print build summary JSON")
    pal_kb_query_parser = pal_kb_sub.add_parser("query", help="Query the local PAL knowledge index")
    pal_kb_query_parser.add_argument("project_root", type=Path)
    pal_kb_query_parser.add_argument("--query", required=True)
    pal_kb_query_parser.add_argument("--limit", type=int, default=5)
    pal_kb_query_parser.add_argument("--index", type=Path)
    pal_kb_query_parser.add_argument("--json", action="store_true", help="Print query results JSON")

    pal_agent_parser = pal_sub.add_parser("agent", help="Run bounded PAL agent workflows")
    pal_agent_sub = pal_agent_parser.add_subparsers(dest="pal_agent_command", required=True)
    pal_agent_triage_parser = pal_agent_sub.add_parser(
        "triage",
        help="Run a bounded PAL ops triage workflow",
    )
    pal_agent_triage_parser.add_argument("project_root", type=Path)
    pal_agent_triage_parser.add_argument(
        "--task",
        default=DEFAULT_TRIAGE_TASK,
        help="Operator task for PAL to triage",
    )
    pal_agent_triage_parser.add_argument("--json", action="store_true", help="Print triage result JSON")
    pal_agent_actions_parser = pal_agent_sub.add_parser(
        "actions",
        help="Propose and optionally execute approval-gated PAL actions",
    )
    pal_agent_actions_parser.add_argument("project_root", type=Path)
    pal_agent_actions_parser.add_argument(
        "--task",
        default=DEFAULT_ACTION_TASK,
        help="Operator task for PAL action planning",
    )
    pal_agent_actions_parser.add_argument(
        "--approve",
        action="append",
        default=[],
        metavar="ACTION_ID",
        help="Approve one proposed allow-listed action for execution; repeat for multiple actions",
    )
    pal_agent_actions_parser.add_argument("--json", action="store_true", help="Print action result JSON")

    pal_agent_approve_parser = pal_agent_sub.add_parser(
        "approve",
        help="Approve a previously proposed PAL agent action by run id",
    )
    pal_agent_approve_parser.add_argument("project_root", type=Path)
    pal_agent_approve_parser.add_argument(
        "--run-id",
        required=True,
        help="Run id of the prior PAL agent actions run that proposed the action",
    )
    pal_agent_approve_parser.add_argument(
        "--action",
        required=True,
        action="append",
        default=[],
        metavar="ACTION_ID",
        help="Approve the given proposed action id; repeat for multiple actions",
    )
    pal_agent_approve_parser.add_argument(
        "--json",
        action="store_true",
        help="Print approval result JSON",
    )

    asset_bus_parser = subparsers.add_parser(
        "asset-bus", help="Deniable Asset Bus commands"
    )
    asset_bus_sub = asset_bus_parser.add_subparsers(
        dest="asset_bus_command", required=True
    )
    asset_bus_validate_parser = asset_bus_sub.add_parser(
        "validate",
        help="Validate one request file against the v0.1 schema",
    )
    asset_bus_validate_parser.add_argument(
        "--request",
        required=True,
        type=Path,
        help="Path to a requests/<request_id>.json file",
    )

    # --- coherence subcommand group ---
    coherence_parser = subparsers.add_parser("coherence", help="Coherence engine commands")
    coherence_sub = coherence_parser.add_subparsers(dest="coherence_command", required=True)

    coh_status_parser = coherence_sub.add_parser("status", help="Show coherence engine status")
    coh_status_parser.add_argument("project_root", type=Path)

    coh_decisions_parser = coherence_sub.add_parser("decisions", help="List active architectural decisions")
    coh_decisions_parser.add_argument("project_root", type=Path)

    coh_record_parser = coherence_sub.add_parser("record-decision", help="Record a new architectural decision")
    coh_record_parser.add_argument("project_root", type=Path)
    coh_record_parser.add_argument("--title", required=True, help="Decision title")
    coh_record_parser.add_argument("--context", required=True, help="Why this decision was made")
    coh_record_parser.add_argument("--decision", required=True, help="What was decided")
    coh_record_parser.add_argument("--rationale", required=True, help="The reasoning")
    coh_record_parser.add_argument("--tags", nargs="*", default=[], help="Tags for the decision")
    coh_record_parser.add_argument("--files", nargs="*", default=[], help="File paths affected")

    coh_replay_parser = coherence_sub.add_parser("replay", help="Replay events for a run")
    coh_replay_parser.add_argument("project_root", type=Path)
    coh_replay_parser.add_argument("--run-id", required=True, help="Run ID to replay")

    coh_doctor_parser = coherence_sub.add_parser("doctor", help="Validate coherence system health")
    coh_doctor_parser.add_argument("project_root", type=Path)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    created = init_project(args.path, args.name)
    print(banner(args.name, "Project Scaffold"))
    print(status_line(f"Created {len(created)} files in {args.path}", "🧱"))
    if args.no_wizard or not sys.stdin.isatty() or not sys.stdout.isatty():
        print(status_line("Startup wizard skipped. Run `promptclaw wizard <project-root>` any time. 🎈", "⏭️"))
        return 0
    run_startup_wizard(project_root=args.path, project_name=args.name)
    return 0


def cmd_wizard(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    run_startup_wizard(project_root=args.project_root, project_name=config.project.name)
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(args.project_root)
    for name, check in report.checks.items():
        status = check["status"].upper()
        print(f"- {name}: {status} — {check['message']}")
        for detail in check.get("details", []):
            print(f"  - {detail}")
    if report.ok:
        print(status_line("Doctor OK ✅", "🩺"))
        return 0
    print("Doctor found issues:")
    return 1


def cmd_bootstrap(args: argparse.Namespace) -> int:
    run_id = bootstrap_project(args.project_root)
    print(status_line(f"Bootstrap run created: {run_id} 🚀", "🦀"))
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    orchestrator = PromptClawOrchestrator(args.project_root)
    task_text = args.task if args.task else read_text(args.task_file)
    state = orchestrator.run(task_text=task_text, title="PromptClaw Run")
    result = {
        "run_id": state.run_id,
        "status": state.status,
        "phase": state.current_phase,
        "lead_agent": state.lead_agent,
        "verifier_agent": state.verifier_agent,
        "summary": state.final_summary_path,
    }
    if state.errors:
        result["errors"] = state.errors
        result["recovery_actions"] = state.recovery_actions
    print(json.dumps(result, indent=2))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    orchestrator = PromptClawOrchestrator(args.project_root)
    state = orchestrator.resume(run_id=args.run_id, answer=args.answer)
    print(json.dumps({
        "run_id": state.run_id,
        "status": state.status,
        "phase": state.current_phase,
        "summary": state.final_summary_path,
    }, indent=2))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    paths = ProjectPaths(project_root=args.project_root, config=config)
    store = StateStore(paths)
    if args.run_id:
        state = store.load(args.run_id)
        print(json.dumps({
            "run_id": state.run_id,
            "title": state.title,
            "status": state.status,
            "current_phase": state.current_phase,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "lead_agent": state.lead_agent,
            "verifier_agent": state.verifier_agent,
            "clarification_question": state.clarification_question,
            "final_summary_path": state.final_summary_path,
        }, indent=2))
        return 0
    runs = store.list_runs()
    print(json.dumps([
        {
            "run_id": state.run_id,
            "title": state.title,
            "status": state.status,
            "phase": state.current_phase,
            "created_at": state.created_at,
        }
        for state in runs
    ], indent=2))
    return 0


def _build_coherence_engine(project_root: Path):
    """Instantiate a CoherenceEngine for the given project root."""
    from .coherence.engine import CoherenceEngine
    from .coherence.models import CoherenceConfig

    config = CoherenceConfig()
    return CoherenceEngine(config, project_root)


def cmd_coherence_status(args: argparse.Namespace) -> int:
    """Show coherence engine status: enforcement mode, trust scores, recent violations."""
    engine = _build_coherence_engine(args.project_root)
    trust_scores = engine.trust_manager.all_scores()
    decisions = engine.decision_store.list_active()
    result = {
        "enforcement_mode": engine.config.mode.value,
        "auto_graduate": engine.config.auto_graduate,
        "constitution_loaded": engine.constitution.rules_for_phase("routing") != [],
        "active_decisions": len(decisions),
        "trust_scores": {
            agent: {
                "score": round(ts.score, 4),
                "hard_violations": ts.hard_violations,
                "soft_violations": ts.soft_violations,
                "compliant_actions": ts.compliant_actions,
                "last_updated": ts.last_updated,
            }
            for agent, ts in trust_scores.items()
        },
    }
    print(json.dumps(result, indent=2))
    return 0


def cmd_coherence_decisions(args: argparse.Namespace) -> int:
    """List all active architectural decisions."""
    engine = _build_coherence_engine(args.project_root)
    decisions = engine.decision_store.list_active()
    print(json.dumps([
        {
            "decision_id": d.decision_id,
            "created_at": d.created_at,
            "title": d.title,
            "context": d.context,
            "decision": d.decision_text,
            "rationale": d.rationale,
            "status": d.status,
            "tags": d.tags,
            "file_paths": d.file_paths,
        }
        for d in decisions
    ], indent=2))
    return 0


def cmd_coherence_record_decision(args: argparse.Namespace) -> int:
    """Record a new architectural decision."""
    engine = _build_coherence_engine(args.project_root)
    decision = engine.record_decision(
        title=args.title,
        context=args.context,
        decision_text=args.decision,
        rationale=args.rationale,
        tags=args.tags,
        file_paths=args.files,
    )
    print(json.dumps({
        "decision_id": decision.decision_id,
        "title": decision.title,
        "status": decision.status,
        "created_at": decision.created_at,
    }, indent=2))
    return 0


def cmd_coherence_replay(args: argparse.Namespace) -> int:
    """Replay events for a specific run."""
    engine = _build_coherence_engine(args.project_root)
    events = engine.replay(args.run_id)
    print(json.dumps([
        {
            "event_id": e.event_id,
            "run_id": e.run_id,
            "timestamp": e.timestamp,
            "event_type": e.event_type,
            "phase": e.phase,
            "agent": e.agent,
            "role": e.role,
            "sequence_number": e.sequence_number,
            "payload": e.payload,
        }
        for e in events
    ], indent=2))
    return 0


def cmd_coherence_doctor(args: argparse.Namespace) -> int:
    """Validate coherence system health."""
    project_root = args.project_root
    checks_passed = 0
    checks_failed = 0

    def _pass(label: str, detail: str = "") -> None:
        nonlocal checks_passed
        checks_passed += 1
        msg = f"  PASS: {label}"
        if detail:
            msg += f" ({detail})"
        print(msg)

    def _fail(label: str, detail: str = "") -> None:
        nonlocal checks_failed
        checks_failed += 1
        msg = f"  FAIL: {label}"
        if detail:
            msg += f" ({detail})"
        print(msg)

    print("Coherence Doctor")
    print("=" * 40)

    # Check 1: Constitution file exists and parses without errors
    constitution_path = project_root / "constitution.yaml"
    if constitution_path.exists():
        try:
            from .coherence.constitution import Constitution
            const = Constitution(constitution_path)
            _pass("Constitution file", f"{len(const.rules)} rules loaded from {constitution_path.name}")
        except Exception as exc:
            _fail("Constitution file", f"parse error: {exc}")
    else:
        # Also check constitution.json as fallback
        constitution_json = project_root / "constitution.json"
        if constitution_json.exists():
            try:
                from .coherence.constitution import Constitution
                const = Constitution(constitution_json)
                _pass("Constitution file", f"{len(const.rules)} rules loaded from {constitution_json.name}")
            except Exception as exc:
                _fail("Constitution file", f"parse error: {exc}")
        else:
            _pass("Constitution file", "no constitution file present (optional)")

    # Check 2: Coherence DB exists and has valid schema
    db_path = project_root / ".promptclaw" / "coherence.db"
    if db_path.exists():
        try:
            import sqlite3
            conn = sqlite3.connect(str(db_path), timeout=5)
            conn.row_factory = sqlite3.Row
            # Check events table
            tables = [
                row[0] for row in
                conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            ]
            has_events = "events" in tables
            has_decisions = "decisions" in tables
            if has_events and has_decisions:
                _pass("Coherence DB schema", "events and decisions tables present")
            elif has_events:
                _pass("Coherence DB schema", "events table present, decisions table missing")
            elif has_decisions:
                _fail("Coherence DB schema", "events table missing")
            else:
                _fail("Coherence DB schema", "neither events nor decisions table found")
            conn.close()
        except Exception as exc:
            _fail("Coherence DB schema", f"database error: {exc}")
    else:
        _fail("Coherence DB", f"database not found at {db_path}")

    # Check 3: All decision records have required fields
    try:
        engine = _build_coherence_engine(project_root)
        decisions = engine.decision_store.list_active()
        invalid_decisions = []
        for d in decisions:
            missing = []
            if not d.decision_id:
                missing.append("decision_id")
            if not d.title:
                missing.append("title")
            if not d.created_at:
                missing.append("created_at")
            if not d.decision_text:
                missing.append("decision_text")
            if missing:
                invalid_decisions.append((d.decision_id or "<no-id>", missing))
        if not invalid_decisions:
            _pass("Decision records", f"{len(decisions)} active decisions, all valid")
        else:
            details = "; ".join(f"{did} missing {', '.join(fields)}" for did, fields in invalid_decisions)
            _fail("Decision records", details)
    except Exception as exc:
        _fail("Decision records", f"could not query: {exc}")

    # Check 4: No orphaned events (events referencing non-existent runs)
    try:
        engine = _build_coherence_engine(project_root)
        all_events = engine.event_store.replay_all()
        # Collect unique run_ids from events
        event_run_ids = set()
        for ev in all_events:
            event_run_ids.add(ev.run_id)
        # Check which run_ids have a run_started event
        started_runs = set()
        for ev in all_events:
            if ev.event_type == "run_started":
                started_runs.add(ev.run_id)
        orphaned = event_run_ids - started_runs
        if not orphaned:
            _pass("Orphaned events", f"{len(event_run_ids)} run(s) found, none orphaned")
        else:
            _fail("Orphaned events", f"{len(orphaned)} run(s) with events but no run_started: {', '.join(sorted(orphaned))}")
    except Exception as exc:
        _fail("Orphaned events", f"could not check: {exc}")

    # Check 5: Trust scores are within valid range [0.0, 1.0]
    try:
        engine = _build_coherence_engine(project_root)
        scores = engine.trust_manager.all_scores()
        out_of_range = []
        for agent, ts in scores.items():
            if ts.score < 0.0 or ts.score > 1.0:
                out_of_range.append(f"{agent}={ts.score:.4f}")
        if not out_of_range:
            _pass("Trust scores", f"{len(scores)} agent(s) tracked, all in [0.0, 1.0]")
        else:
            _fail("Trust scores", f"out of range: {', '.join(out_of_range)}")
    except Exception as exc:
        _fail("Trust scores", f"could not check: {exc}")

    # Summary
    print("=" * 40)
    total = checks_passed + checks_failed
    if checks_failed == 0:
        print(f"All {total} checks passed.")
        return 0
    else:
        print(f"{checks_failed} of {total} checks failed.")
        return 1


def cmd_show_config(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    print(json.dumps({
        "project": {
            "name": config.project.name,
            "description": config.project.description,
        },
        "artifacts": {
            "root": config.artifacts.root,
        },
        "control_plane": {
            "mode": config.control_plane.mode,
            "agent": config.control_plane.agent,
            "allow_fallback": config.control_plane.allow_fallback,
        },
        "routing": {
            "verification_enabled": config.routing.verification_enabled,
            "max_retries": config.routing.max_retries,
            "ask_user_on_ambiguity": config.routing.ask_user_on_ambiguity,
            "default_task_type": config.routing.default_task_type,
        },
        "pal": {
            "enabled": config.pal.enabled,
            "base_url": config.pal.base_url,
            "default_model": config.pal.default_model,
            "timeout_s": config.pal.timeout_s,
            "health_timeout_s": config.pal.health_timeout_s,
            "knowledge_sources": config.pal.knowledge_sources,
        },
        "agents": {
            name: {
                "enabled": agent.enabled,
                "kind": agent.kind,
                "shell_command": agent.shell_command,
                "command": agent.command,
                "env": agent.env,
                "capabilities": agent.capabilities,
                "instruction_file": agent.instruction_file,
            }
            for name, agent in config.agents.items()
        },
    }, indent=2))
    return 0


def cmd_pal_health(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    client = PALRouterClient.from_config(config)
    print(json.dumps(client.health(), indent=2))
    return 0


def cmd_pal_query(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    client = PALRouterClient.from_config(config)
    result = client.query(
        prompt=args.prompt,
        system=args.system,
        model=args.model,
        temperature=args.temperature,
    )
    if args.text:
        print(result.text)
    else:
        print(json.dumps(result.raw, indent=2))
    return 0


def cmd_pal_smoke(args: argparse.Namespace) -> int:
    config = load_config(args.project_root)
    client = PALRouterClient.from_config(config)
    report = run_pal_smoke(client)
    report_path = write_smoke_report(args.project_root, report, output=args.output)
    if args.json:
        payload = dict(report)
        payload["report_path"] = str(report_path)
        print(json.dumps(payload, indent=2))
    else:
        summary = report["summary"]
        print(
            "PAL smoke: "
            f"{report['status'].upper()} "
            f"passed={summary['passed']} "
            f"failed={summary['failed']} "
            f"total_latency_s={summary['total_latency_s']} "
            f"report={report_path}"
        )
    return 0 if report["status"] == "pass" else 1


def cmd_pal_baseline(args: argparse.Namespace) -> int:
    reports = load_smoke_reports(args.project_root)
    summary = summarize_smoke_reports(reports)
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(format_baseline_summary(summary))
    return 0


def cmd_pal_diagnose_slow_inference(args: argparse.Namespace) -> int:
    result = run_pal_slow_inference_diagnosis(args.project_root, task=args.task)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        executed_tools = ",".join(result["executed_tools"]) or "none"
        mutating_actions = ",".join(result["mutating_actions"]) or "none"
        print(
            "PAL slow-inference diagnosis: "
            f"{result['status'].upper()} "
            f"run_id={result['run_id']} "
            f"severity={result['severity']} "
            f"findings={result['finding_count']} "
            f"executed_tools={executed_tools} "
            f"mutating_actions={mutating_actions} "
            f"diagnosis={result['diagnosis_path']} "
            f"summary={result['summary_path']}"
        )
    return 0 if result["status"] == "complete" else 1


def cmd_pal_validate_restart(args: argparse.Namespace) -> int:
    result = run_pal_restart_validation(args.project_root, task=args.task)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        executed_tools = ",".join(result["executed_tools"]) or "none"
        mutating_actions = ",".join(result["mutating_actions"]) or "none"
        print(
            "PAL restart validation: "
            f"{result['status'].upper()} "
            f"run_id={result['run_id']} "
            f"validation_status={result['validation_status']} "
            f"executed_tools={executed_tools} "
            f"mutating_actions={mutating_actions} "
            f"validation={result['validation_path']} "
            f"summary={result['summary_path']}"
        )
    return 0 if result["status"] == "complete" and result["validation_status"] != "fail" else 1


def cmd_pal_audit_shutdown(args: argparse.Namespace) -> int:
    result = run_pal_shutdown_audit(args.project_root, task=args.task)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        executed_tools = ",".join(result["executed_tools"]) or "none"
        mutating_actions = ",".join(result["mutating_actions"]) or "none"
        print(
            "PAL shutdown audit: "
            f"{result['status'].upper()} "
            f"run_id={result['run_id']} "
            f"audit_status={result['audit_status']} "
            f"shutdown_enabled={result['shutdown_enabled_state']} "
            f"override={result['override_state']} "
            f"next_shutdown_window={result['next_shutdown_window']} "
            f"executed_tools={executed_tools} "
            f"mutating_actions={mutating_actions} "
            f"audit={result['audit_path']} "
            f"summary={result['summary_path']}"
        )
    return 0 if result["status"] == "complete" and result["audit_status"] != "fail" else 1


def cmd_pal_report_phase2_readiness(args: argparse.Namespace) -> int:
    result = run_pal_phase2_readiness_report(args.project_root, task=args.task)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        executed_tools = ",".join(result["executed_tools"]) or "none"
        mutating_actions = ",".join(result["mutating_actions"]) or "none"
        phase2_execution_actions = ",".join(result["phase2_execution_actions"]) or "none"
        print(
            "PAL Phase 2 readiness: "
            f"{result['status'].upper()} "
            f"run_id={result['run_id']} "
            f"readiness_status={result['readiness_status']} "
            f"overall_score={result['overall_score']:.2f} "
            f"prerequisites={result['prerequisite_count']} "
            f"executed_tools={executed_tools} "
            f"mutating_actions={mutating_actions} "
            f"phase2_execution_actions={phase2_execution_actions} "
            f"report={result['readiness_path']} "
            f"summary={result['summary_path']}"
        )
    return 0 if result["status"] == "complete" else 1


def cmd_pal_deploy_plan(args: argparse.Namespace) -> int:
    project_root = args.project_root
    manifest_path = _resolve_project_path(project_root, args.manifest) if args.manifest else None
    remote_inventory_path = (
        _resolve_project_path(project_root, args.remote_inventory) if args.remote_inventory else None
    )
    remote_inventory = (
        load_pal_remote_inventory_snapshot(remote_inventory_path)
        if remote_inventory_path is not None
        else ()
    )
    plan = build_pal_deploy_plan(
        project_root,
        manifest_path=manifest_path,
        remote_inventory=remote_inventory,
        remote_inventory_source=str(remote_inventory_path) if remote_inventory_path is not None else "empty",
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2))
    else:
        print(format_pal_deploy_plan(plan))
    return 0


def cmd_pal_deploy_apply(args: argparse.Namespace) -> int:
    project_root = args.project_root
    manifest_path = _resolve_project_path(project_root, args.manifest) if args.manifest else None
    remote_inventory_path = _resolve_project_path(project_root, args.remote_inventory)
    if not args.approve_apply:
        payload = {
            "workflow_id": "pal_deploy_apply",
            "status": "rejected",
            "approved": False,
            "remote_writes": False,
            "remote_transport": "fake-remote-inventory",
            "live_ssh": False,
            "service_restarts": False,
            "remote_inventory_path": str(remote_inventory_path),
            "reason": "PAL deploy apply requires --approve-apply before fake remote writes",
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                "PAL deploy apply: REJECTED "
                "approved=false remote_writes=false live_ssh=false "
                "service_restarts=false reason=missing --approve-apply"
            )
        return 1

    remote_inventory = load_pal_remote_inventory_snapshot(remote_inventory_path)
    manifest = load_pal_deployment_manifest(project_root, manifest_path=manifest_path)
    backup_id = args.backup_id or default_pal_deploy_apply_backup_id()
    result = apply_pal_deployment_changes(
        manifest,
        project_root,
        remote_inventory=remote_inventory,
        remote_inventory_path=remote_inventory_path,
        backup_root=project_root / ".promptclaw" / "pal-deploy" / "backups",
        backup_id=backup_id,
        approved=True,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_pal_deploy_apply_result(result))
    return 0


def cmd_pal_deploy_rollback(args: argparse.Namespace) -> int:
    project_root = args.project_root
    remote_inventory_path = _resolve_project_path(project_root, args.remote_inventory)
    backup_path = _pal_deploy_backup_path(project_root, args.backup_id)
    if not args.approve_rollback:
        payload = {
            "workflow_id": "pal_deploy_rollback",
            "status": "rejected",
            "approved": False,
            "remote_writes": False,
            "remote_transport": "fake-remote-inventory",
            "live_ssh": False,
            "service_restarts": False,
            "remote_inventory_path": str(remote_inventory_path),
            "backup_id": args.backup_id,
            "backup_path": str(backup_path),
            "reason": "PAL deploy rollback requires --approve-rollback before fake remote writes",
        }
        if args.json:
            print(json.dumps(payload, indent=2))
        else:
            print(
                "PAL deploy rollback: REJECTED "
                "approved=false remote_writes=false live_ssh=false "
                "service_restarts=false reason=missing --approve-rollback"
            )
        return 1

    backup = load_pal_deployment_backup(backup_path)
    remote_inventory = load_pal_remote_inventory_snapshot(remote_inventory_path)
    result = rollback_pal_deployment_backup(
        backup,
        remote_inventory=remote_inventory,
        remote_inventory_path=remote_inventory_path,
        approved=True,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2))
    else:
        print(format_pal_deploy_rollback_result(result))
    return 0


def cmd_pal_cost(args: argparse.Namespace) -> int:
    burn = compute_pal_cost_burn(
        args.hourly_rate_usd,
        vast_instance_id=args.vast_instance_id,
    )
    if args.json:
        print(json.dumps(burn.to_dict(), indent=2))
    else:
        print(format_pal_cost_burn(burn))
    return 0


def cmd_pal_kb_build(args: argparse.Namespace) -> int:
    result = write_pal_knowledge_index(
        args.project_root,
        max_chars=args.max_chars,
        output_path=args.output,
    )
    payload = {
        "index_path": str(result.index_path),
        "source_count": result.source_count,
        "chunk_count": result.chunk_count,
        "max_chars": result.max_chars,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(
            "PAL KB build: "
            f"sources={result.source_count} "
            f"chunks={result.chunk_count} "
            f"max_chars={result.max_chars} "
            f"index={_display_path(args.project_root, result.index_path)}"
        )
    return 0


def cmd_pal_kb_query(args: argparse.Namespace) -> int:
    results = query_pal_knowledge_index(
        args.project_root,
        args.query,
        index_path=args.index,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps([asdict(result) for result in results], indent=2))
    else:
        print(f"PAL KB query: matches={len(results)}")
        for result in results:
            print(
                f"{result.rank}. {result.source_path}:{result.start_line}-{result.end_line} "
                f"score={result.score:.3f} chunk={result.chunk_id}"
            )
            print(f"   {result.snippet}")
    return 0


def cmd_pal_agent_triage(args: argparse.Namespace) -> int:
    result = run_pal_ops_triage(args.project_root, task=args.task)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        executed_tools = ",".join(result["executed_tools"]) or "none"
        ignored_tools = ",".join(result["ignored_tools"]) or "none"
        print(
            "PAL agent triage: "
            f"{result['status'].upper()} "
            f"run_id={result['run_id']} "
            f"plan_source={result['plan_source']} "
            f"executed_tools={executed_tools} "
            f"ignored_tools={ignored_tools} "
            f"summary={result['summary_path']}"
        )
    return 0 if result["status"] == "complete" else 1


def cmd_pal_agent_actions(args: argparse.Namespace) -> int:
    result = run_pal_ops_actions(args.project_root, task=args.task, approved_actions=tuple(args.approve))
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        executed_actions = ",".join(result["executed_actions"]) or "none"
        pending_approval = ",".join(result["pending_approval"]) or "none"
        ignored_actions = ",".join(result["ignored_actions"]) or "none"
        ignored_approvals = ",".join(result["ignored_approvals"]) or "none"
        print(
            "PAL agent actions: "
            f"{result['status'].upper()} "
            f"run_id={result['run_id']} "
            f"plan_source={result['plan_source']} "
            f"proposed_actions={','.join(result['proposed_actions']) or 'none'} "
            f"executed_actions={executed_actions} "
            f"pending_approval={pending_approval} "
            f"ignored_actions={ignored_actions} "
            f"ignored_approvals={ignored_approvals} "
            f"summary={result['summary_path']}"
        )
    return 0 if result["status"] == "complete" else 1


def cmd_pal_agent_approve(args: argparse.Namespace) -> int:
    actions = list(args.action)
    try:
        saved = load_pal_action_results(args.project_root, args.run_id)
    except (FileNotFoundError, ValueError) as exc:
        message = str(exc)
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "rejected",
                        "run_id": args.run_id,
                        "project_root": str(args.project_root),
                        "approved_actions": actions,
                        "unknown_actions": actions,
                        "reason": message,
                    },
                    indent=2,
                )
            )
        else:
            print(
                "PAL agent approve: REJECTED "
                f"run_id={args.run_id} "
                f"approved_actions={','.join(actions) or 'none'} "
                f"reason={message}"
            )
        return 1

    proposed = list(saved.get("proposed_actions") or [])
    proposed_set = set(proposed)
    unknown = [action_id for action_id in actions if action_id not in proposed_set]
    if unknown:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "rejected",
                        "run_id": args.run_id,
                        "project_root": str(args.project_root),
                        "approved_actions": actions,
                        "unknown_actions": unknown,
                        "proposed_actions": proposed,
                    },
                    indent=2,
                )
            )
        else:
            print(
                "PAL agent approve: REJECTED "
                f"run_id={args.run_id} "
                f"approved_actions={','.join(actions) or 'none'} "
                f"unknown_actions={','.join(unknown)} "
                f"proposed_actions={','.join(proposed) or 'none'}"
            )
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "status": "pending",
                    "run_id": args.run_id,
                    "project_root": str(args.project_root),
                    "approved_actions": actions,
                },
                indent=2,
            )
        )
    else:
        print(
            "PAL agent approve: PENDING "
            f"run_id={args.run_id} "
            f"approved_actions={','.join(actions) or 'none'} "
            f"project_root={args.project_root}"
        )
    return 0


def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "init":
        return cmd_init(args)
    if args.command == "wizard":
        return cmd_wizard(args)
    if args.command == "doctor":
        return cmd_doctor(args)
    if args.command == "bootstrap":
        return cmd_bootstrap(args)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "resume":
        return cmd_resume(args)
    if args.command == "status":
        return cmd_status(args)
    if args.command == "show-config":
        return cmd_show_config(args)
    if args.command == "pal":
        return _dispatch_pal(args)
    if args.command == "asset-bus":
        return _dispatch_asset_bus(args)
    if args.command == "coherence":
        return _dispatch_coherence(args)
    return 2


def _dispatch_pal(args: argparse.Namespace) -> int:
    if args.pal_command == "health":
        return cmd_pal_health(args)
    if args.pal_command == "query":
        return cmd_pal_query(args)
    if args.pal_command == "smoke":
        return cmd_pal_smoke(args)
    if args.pal_command == "baseline":
        return cmd_pal_baseline(args)
    if args.pal_command == "diagnose" and args.pal_diagnose_command == "slow-inference":
        return cmd_pal_diagnose_slow_inference(args)
    if args.pal_command == "validate" and args.pal_validate_command == "restart":
        return cmd_pal_validate_restart(args)
    if args.pal_command == "audit" and args.pal_audit_command == "shutdown":
        return cmd_pal_audit_shutdown(args)
    if args.pal_command == "report" and args.pal_report_command == "phase2-readiness":
        return cmd_pal_report_phase2_readiness(args)
    if args.pal_command == "deploy" and args.pal_deploy_command == "plan":
        return cmd_pal_deploy_plan(args)
    if args.pal_command == "deploy" and args.pal_deploy_command == "apply":
        return cmd_pal_deploy_apply(args)
    if args.pal_command == "deploy" and args.pal_deploy_command == "rollback":
        return cmd_pal_deploy_rollback(args)
    if args.pal_command == "cost":
        return cmd_pal_cost(args)
    if args.pal_command == "kb" and args.pal_kb_command == "build":
        return cmd_pal_kb_build(args)
    if args.pal_command == "kb" and args.pal_kb_command == "query":
        return cmd_pal_kb_query(args)
    if args.pal_command == "agent" and args.pal_agent_command == "triage":
        return cmd_pal_agent_triage(args)
    if args.pal_command == "agent" and args.pal_agent_command == "actions":
        return cmd_pal_agent_actions(args)
    if args.pal_command == "agent" and args.pal_agent_command == "approve":
        return cmd_pal_agent_approve(args)
    return 2


def cmd_asset_bus_validate(args: argparse.Namespace) -> int:
    request_path: Path = args.request
    try:
        raw = request_path.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"asset-bus validate: cannot read {request_path}: {exc}", file=sys.stderr)
        return 2
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(
            f"asset-bus validate: {request_path} is not valid JSON: {exc}",
            file=sys.stderr,
        )
        return 2
    try:
        request = validate_request(data)
    except SchemaError as exc:
        print(f"asset-bus validate: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(request.to_dict(), indent=2))
    return 0


def _dispatch_asset_bus(args: argparse.Namespace) -> int:
    if args.asset_bus_command == "validate":
        return cmd_asset_bus_validate(args)
    return 2


def _dispatch_coherence(args: argparse.Namespace) -> int:
    if args.coherence_command == "status":
        return cmd_coherence_status(args)
    if args.coherence_command == "decisions":
        return cmd_coherence_decisions(args)
    if args.coherence_command == "record-decision":
        return cmd_coherence_record_decision(args)
    if args.coherence_command == "replay":
        return cmd_coherence_replay(args)
    if args.coherence_command == "doctor":
        return cmd_coherence_doctor(args)
    return 2


def main(argv: list[str] | None = None) -> int:
    try:
        from cypherclaw.first_boot import bootstrap_identity
        bootstrap_identity()
    except ImportError:
        pass

    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _dispatch(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        command = getattr(args, "command", "unknown")
        diag = diagnose(exc, phase=command)
        print(f"\n{format_diagnosis(diag)}", file=sys.stderr)
        if state := _try_extract_state(args):
            print(f"\n  Run state may be partially saved. Check: promptclaw status {state} --run-id <id>", file=sys.stderr)
        return 1


def _try_extract_state(args: argparse.Namespace) -> str | None:
    """Try to extract the project root from args for error messages."""
    for attr in ("project_root", "path"):
        val = getattr(args, attr, None)
        if val is not None:
            return str(val)
    return None


def _display_path(project_root: Path, path: Path) -> str:
    try:
        return path.relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return str(path)


def _resolve_project_path(project_root: Path, path: Path) -> Path:
    if path.is_absolute():
        return path
    return project_root / path


def _pal_deploy_backup_path(project_root: Path, backup_id: str) -> Path:
    backup_id_path = Path(backup_id)
    if backup_id_path.name != backup_id or backup_id in {"", ".", ".."}:
        raise ValueError("PAL deploy backup id must be a single directory name")
    return project_root / ".promptclaw" / "pal-deploy" / "backups" / backup_id


if __name__ == "__main__":
    raise SystemExit(main())
