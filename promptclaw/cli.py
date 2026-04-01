from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bootstrap import bootstrap_project, init_project
from .config import load_config
from .diagnostics import diagnose, format_diagnosis
from .doctor import run_doctor
from .orchestrator import PromptClawOrchestrator
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
    if args.command == "coherence":
        return _dispatch_coherence(args)
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


if __name__ == "__main__":
    raise SystemExit(main())
