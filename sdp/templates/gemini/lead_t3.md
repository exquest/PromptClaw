<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles lead_t3.md.
  The shipped default lives at src/sdp/prompts/templates/lead_t3.md.
  Delete this file to revert to the default.
-->
# Task {{ task_id }}: {{ task_description }}

{% if acceptance_criteria %}
## Acceptance Criteria

{{ acceptance_criteria }}
{% endif %}

**Tier:** {{ tier }}

## Overview

This is a complex task. Plan your work carefully and commit progress at each phase.

## Phases

1.  **Specify**: Create a plan of attack. Write a brief specification in `sdp/specs/{{ task_id | lower }}.md`. Outline your approach, files to be modified, and new tests to be added. Commit the spec.
2.  **Test**: Write the tests for the new functionality. They should fail initially. Commit the new tests.
3.  **Implement**: Write the code to make the tests pass. Commit the implementation.
4.  **Verify**: Run the full validation suite.

## Rules

- Commit after each phase is complete.
- If the plan changes, update the specification file.
- Log any ambiguities in `ESCALATIONS.md`.

## Validation

Run this command before finishing:
```bash
pytest tests/ -x --tb=short && ruff check src/ tests/ && mypy src/
```
