# Task frac-0121 Specification: test_wizard Depth 2

## Problem Statement

`tests/test_wizard.py` currently exercises the startup wizard surface in
`promptclaw/wizard.py` at focused helper depth: roster parsing defaults
(`test_parse_agent_roster_defaults`), one realistic interactive run that
writes the project vision and updates the config
(`test_wizard_writes_profile_and_updates_config`), and follow-up question
detection for vague inputs (`test_follow_up_detection_for_vague_inputs`).

The production module already implements a simple one-path solution:
`StartupWizard.run()` walks a base questionnaire, expands per-agent
strength questions and follow-ups, applies the resulting `StartupProfile`
to the project (writing `prompts/00-project-vision.md`,
`prompts/01-agent-roles.md`, `prompts/02-routing-rules.md`,
`prompts/agents/<agent>.md`, `docs/STARTUP_PROFILE.md`,
`docs/STARTUP_TRANSCRIPT.md`, `.promptclaw/onboarding/startup-session.md`,
and `promptclaw.json`), routes through `parse_agent_roster(...)`,
`infer_capabilities(...)`, `looks_vague(...)`, `mentions_any(...)`,
`as_bullets(...)`, `sentence_or_list(...)`, `lead_lane_text(...)`, and
`verification_fit_text(...)`, and produces banner / question /
files-written / summary / status output. This task therefore deepens the
base test file rather than changing production code unless the red tests
expose a concrete gap.

The generated startup identity hardening bullets target the existing
identity startup subsystem. Current CLI, first-boot, daemon-ordering,
standalone / federated persistence, and narrative ASGI tests already
cover `bootstrap_identity()` being invoked before `FirstBootAnnouncer`
and identity persistence between boots. This task keeps those tests as
mandatory regression anchors instead of changing unrelated startup flow.

The active ADP process is the task prompt's
Explore -> Specify -> Test -> Implement -> Verify -> Document workflow,
as mirrored in `sdp/templates/candidates/lead_t2/v006.md`.

## Technical Approach

- Add `tests/test_test_wizard_depth.py` using the recent depth-gate
  pattern from `tests/test_test_voice_aliases_depth.py` and
  `tests/test_test_theramini_duet_depth.py`. The gate requires:
  - `WizardEndToEndTests` exists in `tests/test_wizard.py`;
  - the named method
    `test_startup_wizard_lifecycle_round_trips_json_diagnostic` exists;
  - `classify_depth("tests/test_wizard.py").depth >= 2`;
  - the test module declares a machine-readable depth-2 marker either in
    the module docstring (`depth: 2`) or as a top-level `DEPTH = 2`
    constant.
- Confirm the red phase by running the new depth gate before the
  end-to-end class and marker exist.
- Extend `tests/test_wizard.py` without modifying existing locked
  assertions:
  - add a module docstring with `depth: 2`;
  - import `json` alongside the existing imports plus
    `infer_capabilities`, `lead_lane_text`, `looks_vague`,
    `mentions_any`, `parse_agent_roster`, `sentence_or_list`, and
    `verification_fit_text` from `promptclaw.wizard` as needed;
  - append `WizardEndToEndTests` (a `unittest.TestCase` subclass for
    consistency with the rest of the file) with one deterministic
    end-to-end lifecycle test.
- The end-to-end test will:
  - initialize a fresh temporary project with `init_project(...)`;
  - drive `run_startup_wizard(...)` with a deterministic answer iterator
    that exercises the base questionnaire, the follow-up triggered by a
    `"fully autonomous"` autonomy answer (`permission_boundaries`), and
    the default-roster path (Enter on `agent_roster`) so per-agent
    strength questions for `codex`, `claude`, and `gemini` are queued;
  - assert all expected files exist and carry the answers
    (`prompts/00-project-vision.md`,
    `prompts/01-agent-roles.md`, `prompts/02-routing-rules.md`,
    `prompts/agents/codex.md`, `prompts/agents/claude.md`,
    `prompts/agents/gemini.md`, `docs/STARTUP_PROFILE.md`,
    `docs/STARTUP_TRANSCRIPT.md`,
    `.promptclaw/onboarding/startup-session.md`, and
    `promptclaw.json`);
  - assert the resulting `load_config(...)` agrees with the answers:
    description matches the project pitch, `routing.verification_enabled`
    is `True`, `routing.ask_user_on_ambiguity` is `True`, the agent
    roster equals `["codex", "claude", "gemini"]`, each agent is enabled
    with the inferred capability list, and each agent's
    `instruction_file` points to `prompts/agents/<slug>.md`;
  - assert the focused helpers agree with the lifecycle outputs:
    `parse_agent_roster("codex, claude, gemini")` returns
    `["codex", "claude", "gemini"]`, `parse_agent_roster("")` returns
    the default roster, `looks_vague("anything")` is `True` and
    `looks_vague("a focused mission with concrete outputs")` is
    `False`, `mentions_any(...)` returns `True` when any keyword
    matches and `False` otherwise, `infer_capabilities(...)` for each
    default-strength text contains the expected core capability tags,
    `lead_lane_text("coding, implementation")` returns
    `"code-heavy execution and implementation"`, and
    `verification_fit_text("verification, analysis")` returns
    `"strong verifier candidate"`;
  - assert `sentence_or_list(...)` produces a single line for one item
    and a `- `-prefixed bulleted list for multiple items (covering
    `as_bullets(...)`);
  - assert the wizard captured banner / status / summary output by
    confirming at least one captured block contains `"Startup Wizard"`
    and at least one contains `"Ready"`;
  - round-trip a JSON-safe diagnostic of the captured roster, applied
    config description, per-agent capabilities and instruction files,
    routing flags, written file list (relative to the temp project
    root), and a small focused-helper map through
    `json.dumps(..., sort_keys=True)` and `json.loads(...)`.
- Preserve production behavior unless the red tests reveal a source gap.
- Introduce no new dependencies, migrations, provider secrets, database
  columns, runtime state directories, HTTP routes, auth behavior, or
  agent command strings.

## Edge Cases

- This is intentionally one happy-path lifecycle test. Existing focused
  tests remain responsible for individual roster parsing defaults,
  follow-up detection, and the existing wizard run.
- Vague-input follow-up paths and the broader follow-up matrix remain
  covered by `test_follow_up_detection_for_vague_inputs` and the
  end-to-end coverage exercises only the `permission_boundaries`
  follow-up path so the answer iterator stays deterministic.
- Captured output is asserted by substring rather than exact rendering,
  so banner/icon/spacing changes in `promptclaw/ui.py` do not destabilize
  the diagnostic test.
- The diagnostic payload only stores strings, booleans, ints, lists, and
  nested dictionaries, so JSON serialization remains deterministic and
  hermetic.
- No database schema changes are introduced, so no migration or index
  work is required.
- Startup identity hardening remains a regression anchor and is not
  widened inside the wizard tests.

## Acceptance Criteria

1. Existing wizard assertions remain green.
   VERIFY: `pytest tests/test_wizard.py -q`

2. The depth gate confirms `tests/test_wizard.py` reaches depth >= 2 and
   contains the named end-to-end class/method plus the machine-readable
   depth-2 marker.
   VERIFY: `pytest tests/test_test_wizard_depth.py -q`

3. `WizardEndToEndTests` drives full project scaffolding, config
   application, captured-output verification, focused helper agreement,
   and JSON-safe diagnostic round-trip through one meaningful path.
   VERIFY: `pytest tests/test_wizard.py::WizardEndToEndTests -q`

4. Startup identity hardening remains covered for CLI startup, daemon
   startup ordering, standalone/federated identity persistence, and
   narrative ASGI import persistence.
   VERIFY: `pytest tests/test_cli_identity_hardening.py tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_first_boot.py::TestStartupIdentityModePersistence tests/test_governor_integration.py::TestStartupIdentityWiring tests/test_narrative_api_main.py::test_asgi_module_startup_bootstraps_identity_persistence_between_imports -q`

5. Product-facing task notes mention the frac-0121 wizard test deepening
   with no new dependencies or migrations.
   VERIFY: `grep -n "frac-0121" CHANGELOG.md progress.md ESCALATIONS.md`

6. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
