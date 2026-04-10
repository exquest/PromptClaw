<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles fix_verify.md.
  The shipped default lives at src/sdp/prompts/templates/fix_verify.md.
  Delete this file to revert to the default.
-->
# Fix Verification Issues: Task {{ task_id }}

Your work was rejected by the verifier on attempt {{ attempt }}.

## Verifier Feedback
```
{{ feedback }}
```

## Instructions

1.  **Analyze**: Read the feedback above. Address each blocking point directly. Do not re-do the entire task.
2.  **Act**:
    *   If the feedback is about bugs or test failures, fix them.
    *   If the feedback is purely about style or formatting (`PASS WITH NOTES`), do not just blindly accept it. Document the disagreement in `ESCALATIONS.md` and proceed.
3.  **Verify**: Run all tests and quality checks.
4.  **Commit**: Commit your fixes with the exact message: `fix(scope): address verify feedback [{{ task_id }}]`
