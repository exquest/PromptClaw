---
name: promptclaw-adp-t2-run
description: "Run the full ADP Tier 2 workflow: explore, specify, test, implement, verify, document, and commit."
---

# PromptClaw adp-t2-run

## Required sequence
Explore → Specify → Gate 1 → Test (Red) → Gate 2 → Lock tests → Implement → Gate 3 → Verify → Document → Commit

## Workflow details
1. Explore
   - read the affected area
   - trace relevant data flow
   - inspect existing tests and patterns
   - update `progress.md`
   - do not write implementation code here
2. Specify
   - create `SPEC.md`
   - include acceptance criteria with VERIFY commands
   - include scope boundaries and file lists
   - ensure no TBD / TODO / PLACEHOLDER text remains
3. Test (Red)
   - write tests from the spec
   - confirm they fail before implementation
   - lock tests if the project has a lock mechanism configured
4. Implement
   - minimal code
   - no fabricated dependencies
   - preserve existing patterns
5. Verify
   - run configured test/lint/typecheck/coverage commands when available
   - if commands are missing, log that fact to `ESCALATIONS.md`
6. Document
   - update README / notes / session docs when relevant
7. Commit
   - use a conventional commit message
