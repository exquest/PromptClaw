from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .bootstrap import bootstrap_project, init_project
from .config import load_config, validate_config
from .diagnostics import diagnose, format_diagnosis
from .orchestrator import PromptClawOrchestrator
from .paths import ProjectPaths
from .state_store import StateStore
from .ui import banner, status_line
from .utils import executable_exists, read_text
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
    config = load_config(args.project_root)
    issues = validate_config(config)
    for name, agent in config.agents.items():
        if agent.enabled and agent.kind == "command":
            if agent.command:
                program = str(agent.command[0])
                # Resolve relative paths against the project root
                program_path = Path(program)
                if not program_path.is_absolute() and (str(program_path) != program_path.name):
                    resolved = (args.project_root / program_path).resolve()
                    if resolved.exists():
                        program = str(resolved)
                if not executable_exists(program):
                    issues.append(f"agent '{name}' command executable not found: {program}")
            elif agent.shell_command:
                pass
    if issues:
        print("Doctor found issues:")
        for issue in issues:
            print(f"- {issue}")
        return 1
    print(status_line("Doctor OK ✅", "🩺"))
    return 0


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
