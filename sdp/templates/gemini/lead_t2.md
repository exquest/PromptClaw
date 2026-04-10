<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles lead_t2.md.
  The shipped default lives at src/sdp/prompts/templates/lead_t2.md.
  Delete this file to revert to the default.
-->
# Task {{ task_id }}: {{ task_description }}

{% if acceptance_criteria %}
## Acceptance Criteria

{{ acceptance_criteria }}
{% endif %}

**Tier:** {{ tier }}

## Instructions

1.  **Explore**: Use `grep` or `rg` to find relevant files. Read up to 10 files to understand the context. Do not read more.
2.  **Implement**: Write the code to satisfy the request. Focus on a direct solution.
3.  **Test**: Add or modify tests to cover the new code.
4.  **Commit**: Commit after the first working change. Do not batch all commits until the end. Use message format: `feat(scope): summary [{{ task_id }}]`

## Rules

- If you have questions, document them in `ESCALATIONS.md` and proceed with the most reasonable assumption.
- Follow the project's existing coding style and conventions.
- Do not refactor code outside the scope of the task.

## Validation

Run this command before finishing:
```bash
pytest tests/ -x --tb=short && ruff check src/ tests/ && mypy src/
```
