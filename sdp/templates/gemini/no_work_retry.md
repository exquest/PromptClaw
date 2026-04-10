<!--
  sdp-cli agent-specific template for gemini
  Edit this file to tune how gemini handles no_work_retry.md.
  The shipped default lives at src/sdp/prompts/templates/no_work_retry.md.
  Delete this file to revert to the default.
-->
# Retry: Task {{ task_id }}

**Task:** {{ task_description }}

## Problem

Your previous attempt on this task produced zero commits and ran out of time. You must commit earlier this time.

## Instructions

1.  **Focus**: Do NOT re-read files you already explored. Do NOT restart discovery. Use the `AGENTS.md` file in your context.
2.  **Smallest Step**: Identify the smallest possible change that moves the task forward.
3.  **Implement & Commit**: Implement that one change and commit it within the first 5 minutes.
4.  **Iterate**: Continue with the next small change and commit again.

Zero commits = another failure. One commit with a small change = progress.
