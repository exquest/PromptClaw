<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles lead_t1.md.
  The shipped default lives at src/sdp/prompts/templates/lead_t1.md.
  Delete this file to revert to the default.
-->
# Task {{ task_id }}: {{ task_description }}

{% if acceptance_criteria %}
## Acceptance Criteria

{{ acceptance_criteria }}
{% endif %}

**Tier:** {{ tier }}

## Instructions

1. Read the failing test or bug report to understand the core issue.
2. Make the minimal code change required to fix the problem.
3. Run the relevant tests to confirm the fix and ensure no regressions were introduced.
4. Commit the change with a clear commit message: `fix(scope): summary [{{ task_id }}]`

## Rules

- Do not expand scope; address only the reported problem.
- Follow existing code style and patterns.
- Commit your working change immediately.

## Validation

Run this command before finishing:
```bash
pytest tests/ -x --tb=short && ruff check src/ tests/ && mypy src/
```
