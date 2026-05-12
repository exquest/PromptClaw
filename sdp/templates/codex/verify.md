<!--
  sdp-cli agent-specific template for codex
  Edit this file to tune how codex handles verify.md.
  The shipped default lives at src/sdp/prompts/templates/verify.md.
  Delete this file to revert to the default.
-->
# Verification: Task {{ task_id }}

**Task:** {{ task_description }}
**Tier:** {{ tier }}

Verify by executing the change and checking outcomes. Do not write a deep design review.

{% if acceptance_criteria %}
## Acceptance Criteria

{{ acceptance_criteria }}
{% endif %}

## Review Checklist

1. Check `git status --short`, but make the dirty-worktree decision task-scoped.
   Uncommitted changes introduced by the lead for this task are blocking.
   Pre-existing unrelated dirty or untracked files are notes only; do not ask the
   lead to clean, revert, or commit unrelated workspace state.
2. Review the task commit(s) and changed files only.
3. Run the smallest relevant test command first. If scope is broad or unclear, run the full validation below.
4. Compare observed behavior against the acceptance criteria and changed code paths.
5. Report only reproducible issues, missing behavior, regressions, or real risks.

## Blocking vs Notes

- `FAIL`: failing checks, missing required behavior, regressions, or uncommitted task-scoped tracked work.
- `PASS WITH NOTES`: behavior is correct but minor cleanup or follow-up remains.
- `PASS WITH NOTES`: also use this when acceptance passes but the repository has
  unrelated pre-existing dirty state outside the task scope.
- `PASS`: acceptance criteria are met and no blocking issues remain.

## Output

Write your verification report and all findings to this exact path:
`sdp/verification/{{ task_id | lower }}-verify.md`
Do not use a different filename or directory.

If you need a full validation pass, run:
```bash
pip install -e '.[dev]'
pytest tests/ -x --tb=short
ruff check src/ tests/
mypy src/
```

Use this format:

```markdown
# Verification Report — {{ task_id }}

**Verify Agent:** [your agent name]
**Date:** [today]
**Artifacts Reviewed:** [files and commits]
**Commands Run:** [commands]

## Acceptance Criteria Check
[met / not met, with evidence]

## Issues Found
- [ ] [blocking/minor] [issue]
- [ ] None

## Verdict: PASS | PASS WITH NOTES | FAIL

## Notes for Lead Agent
[actionable next steps only]
```

Commit the verification report.
