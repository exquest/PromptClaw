<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles fix_gate.md.
  The shipped default lives at src/sdp/prompts/templates/fix_gate.md.
  Delete this file to revert to the default.
-->
# Fix Gate Failures: Task {{ task_id }}

Your previous work failed the quality gate.

## Gate Output

```
{{ gate_output }}
```

## Instructions

1.  **Analyze**: Read the gate output above. Identify the specific errors.
2.  **Auto-Fix First**: For linting errors, run `ruff check . --fix` first, as it may solve many issues automatically.
3.  **Manual Fix**: Manually fix any remaining test failures or type errors. Fix ONLY what the gate complained about. Do not refactor other code.
4.  **Verify**: Run the full validation suite to confirm all issues are resolved.
5.  **Commit**: Commit the fix with the exact message: `fix(scope): address gate failures [{{ task_id }}]`
