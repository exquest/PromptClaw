# Task frac-0046 Specification: PromptClaw Config Depth 2

## Problem Statement

`promptclaw/config.py` owns PromptClaw's on-disk configuration contract:
default project layout, JSON load/save, and validation rules used by the
bootstrap, orchestrator, and CLI surfaces. It currently classifies at
fractal depth 1 (`3/5 trivial, 2 real`) because the default-builder, path
helper, and save helper are direct projections, leaving only `load_config`
and `validate_config` as real-logic surfaces.

Operators and downstream callers (CLI status, bootstrap repair flows) have
no module-owned way to:

- Load a project config with a one-path "load if present, otherwise
  initialize defaults" fallback so that callers do not have to re-implement
  the `FileNotFoundError` recovery shape.
- Inspect a config's enabled-agent surface as a stable, deterministic
  tuple without manually filtering the `agents` dict.
- Combine validation issues with a JSON-safe operator summary in a single
  diagnostic call.

This task deepens the module to a simple depth-2 implementation by adding
a typed config-status report, a one-path load-or-default helper, and a
deterministic enabled-agent helper around the existing behavior. All
existing public functions keep their signatures and behavior, and no new
dependencies, migrations, columns, or runtime state files are introduced.

## Technical Approach

- Add a frozen `ConfigStatusReport` dataclass exposing operator-readable
  state for one config: project name, artifact root, control-plane mode,
  control-plane agent (or empty string), default task type, total agent
  count, sorted tuple of enabled agent names, sorted tuple of disabled
  agent names, validation-clean boolean, and a tuple of validation issues
  (the same strings `validate_config` returns).
- Add `enabled_agents(config: PromptClawConfig) -> tuple[str, ...]` that
  returns the names of enabled agents in deterministic alphabetical order.
- Add `config_status_report(config: PromptClawConfig) -> ConfigStatusReport`
  that builds the report by iterating `config.agents` once and reusing
  `validate_config` for the issues field.
- Add `summarize_config(config: PromptClawConfig) -> dict[str, Any]` that
  returns a JSON-safe operator summary (built from
  `config_status_report`) suitable for `json.dumps` without custom
  encoders. Tuples are rendered as sorted lists.
- Add `load_or_default(project_root: Path, project_name: str = "New PromptClaw") -> PromptClawConfig`
  that returns `load_config(project_root)` when the config file exists and
  otherwise returns `default_project_config(project_name)`. One algorithm
  path, no edge cases beyond the file-existence check.
- Keep `default_project_config`, `config_path`, `load_config`,
  `save_config`, and `validate_config` signatures and behavior unchanged.
- Use only the standard library plus the module's existing imports.

## Edge Cases

- `enabled_agents` returns an empty tuple when no agents are enabled and
  preserves alphabetical order across mixed enabled/disabled inputs.
- `config_status_report.control_plane_agent` is `""` when the config does
  not name a control-plane agent (mode `heuristic` with `agent=None`).
- `config_status_report.is_valid` is `True` only when
  `validate_config(config)` returns an empty list; otherwise the tuple of
  issues mirrors that list in order.
- `summarize_config` is JSON-safe (`json.dumps(summary)` succeeds with no
  custom encoder) and exposes lists rather than tuples for downstream
  consumers.
- `load_or_default` uses `config_path(project_root).exists()` as the only
  branch point; missing config returns the same defaults
  `default_project_config(project_name)` produces and does not write to
  disk.
- No new dependencies, migrations, database columns, secrets, or runtime
  state files are added.

## Acceptance Criteria

1. Existing config behavior remains unchanged.
   VERIFY: `pytest tests/test_config.py -q`

2. `enabled_agents` returns enabled agent names in deterministic
   alphabetical order across mixed enabled/disabled inputs.
   VERIFY: `pytest tests/test_promptclaw_config_depth.py::test_enabled_agents_returns_sorted_enabled_names -q`

3. `config_status_report` produces a typed `ConfigStatusReport` with
   meaningful operator state for the default config.
   VERIFY: `pytest tests/test_promptclaw_config_depth.py::test_config_status_report_summarizes_default_config -q`

4. `config_status_report` mirrors `validate_config` issues when the config
   is invalid.
   VERIFY: `pytest tests/test_promptclaw_config_depth.py::test_config_status_report_reflects_validation_issues -q`

5. `summarize_config` is JSON-safe and exposes sorted enabled/disabled
   agent lists plus the issues list.
   VERIFY: `pytest tests/test_promptclaw_config_depth.py::test_summarize_config_is_json_safe -q`

6. `load_or_default` returns the persisted config when present and
   defaults when the config file is missing.
   VERIFY: `pytest tests/test_promptclaw_config_depth.py::test_load_or_default_returns_persisted_or_defaults -q`

7. Fractal depth for `promptclaw/config.py` reaches at least depth 2.
   VERIFY: `pytest tests/test_promptclaw_config_depth.py::test_config_module_reaches_depth_two -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
