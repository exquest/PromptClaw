# Test Report

## Version

PromptClaw v2.1.0

## Unit tests

Command:

```bash
python -m unittest discover -s tests -v
```

Result:

- 15 tests run
- 15 tests passed
- 0 failures
- 0 errors

Covered areas:

- scaffold creation
- bootstrap task composition
- config loading and validation
- heuristic routing
- ambiguity pause/resume flow
- startup wizard follow-up detection
- startup wizard config/profile generation

## Smoke tests

### Scaffold + doctor + bootstrap + run

Commands executed successfully:

```bash
PYTHONPATH=. python -m promptclaw.cli init /tmp/<project> --name "Demo Claw" --no-wizard
PYTHONPATH=. python -m promptclaw.cli doctor /tmp/<project>
PYTHONPATH=. python -m promptclaw.cli bootstrap /tmp/<project>
PYTHONPATH=. python -m promptclaw.cli run /tmp/<project> --task-file examples/tasks/sample-task.md
```

Observed behavior:

- scaffold created successfully
- doctor returned OK
- bootstrap produced a run id
- run completed and wrote a final summary

### Wizard smoke test

A scripted run of `promptclaw wizard .` completed successfully and generated:

- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`
- `.promptclaw/onboarding/startup-session.md`
- updated prompt files
- updated `promptclaw.json`

## Notes

The startup wizard is heuristic-first. It does not require live agent CLIs to function.
