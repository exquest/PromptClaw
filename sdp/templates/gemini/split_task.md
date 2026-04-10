<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles split_task.md.
  The shipped default lives at src/sdp/prompts/templates/split_task.md.
  Delete this file to revert to the default.
-->
The original task `{{ task_id }}` ({{ task_description }}) was too large to complete in one attempt.

Your goal is to break it down into 2-3 smaller, independent subtasks. Do not implement them now. This is a planning step.

For each subtask, define a clear, completable goal.

Output a JSON array of the subtasks, following this exact format:
```json
[
    {
        "id": "a",
        "description": "First subtask description.",
        "tier": "{{ tier }}"
    },
    {
        "id": "b",
        "description": "Second subtask description.",
        "tier": "{{ tier }}"
    }
]
```
