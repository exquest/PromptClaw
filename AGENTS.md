# AGENTS.md

<!-- PROMPTCLAW:BEGIN -->
## PromptClaw

PromptClaw is enabled for this repository.

**Tagline:** *No claw needed, just prompts.*

Before doing meaningful work in this repository:

1. Read these files in order:
   - `.promptclaw/CORE.md`
   - `.promptclaw/ROUTER.md`
   - `.promptclaw/PERSONA.md`
   - `.promptclaw/ADP.md`
   - `.promptclaw/MEMORY.md`
   - `.promptclaw/BACKLOG.md`
   - `.promptclaw/INBOX.md`
   - `.promptclaw/STATE.json`
   - the latest entry in `.promptclaw/JOURNAL/`

2. First-run guard:
   - If `.promptclaw/STATE.json` does not contain `"persona": {"initialized": true}` then **do not continue with normal work**.
   - Immediately run `$promptclaw-persona-onboarding`.
   - Ask the full onboarding interview in one numbered message.
   - Wait for the user's answers.
   - After onboarding is complete, write the persona to `.promptclaw/PERSONA.md`, `.promptclaw/MEMORY.md`, `.promptclaw/STATE.json`, and today's journal.

3. Session startup:
   - At the beginning of each new session, run `$promptclaw-startup-checklist`.
   - Produce a one-screen startup summary before deeper work.

4. Routing discipline:
   - **Gemini lane:** live-web research, vendor reconnaissance, current docs, fast evidence gathering.
   - **Claude lane:** explore, specify, architecture, task framing.
   - **Codex lane:** implementation, tests, verification, repo edits.
   - If the current provider is not the best lane, create a delegation packet under `.promptclaw/delegations/` instead of pretending to be another provider.

5. Research-first rule:
   - For factual claims, current information, or external-tool behavior, research first.
   - Prefer primary sources and official docs.
   - Save research notes in `.promptclaw/NOTES/`.
   - Cite sources in the response and in the journal entry.

6. Development protocol:
   - For coding tasks, classify the work as T1, T2, or T3 using `.promptclaw/ADP.md`.
   - Follow the required phases for the tier.
   - Do not silently widen scope.
   - Log ambiguity, disputes, or missing configuration to `ESCALATIONS.md` and continue where safe.

7. Persistent paper trail:
   - Append a journal entry to `.promptclaw/JOURNAL/YYYY-MM-DD.md` for each meaningful task.
   - Update `.promptclaw/BACKLOG.md` when follow-up work is discovered.
   - Update `.promptclaw/MEMORY.md` only with stable facts and preferences.
   - Update `.promptclaw/STATE.json` after startup, onboarding, and significant tasks.

8. Safety and hygiene:
   - Never store secrets in PromptClaw files.
   - Warn in the journal before any destructive or irreversible action.
   - Prefer additive changes and preserve host-repo instructions outside this block.

9. Commit discipline:
   - If this is a git repo, make meaningful commits with conventional commit messages.
   - Avoid vanity commits for no-op maintenance.

### Definition of Done

A task is done when:
- the correct lane was used or delegated,
- required ADP steps were followed,
- research notes / spec / tests / docs exist when required,
- journal and backlog were updated,
- the repo is left in a coherent state,
- and a commit was made when meaningful files changed.
<!-- PROMPTCLAW:END -->
