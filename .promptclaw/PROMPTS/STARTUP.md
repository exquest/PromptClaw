Use the provider-native startup workflow.

Required behavior:
1. Read PromptClaw core files and latest journal.
2. If persona is not initialized, run persona onboarding and stop.
3. Otherwise produce:
   - persona summary
   - top backlog items
   - inbox summary
   - `sdp-cli` integration summary when enabled in `.promptclaw/STATE.json`
   - workspace snapshot summary when enabled in `.promptclaw/STATE.json`
   - routing suggestions
4. Append a startup journal entry.

When `.promptclaw/STATE.json` enables the `sdp_cli` integration, prefer:

`python3 .promptclaw/scripts/sdp_cli_bridge.py --json`

Summarize:
- queue counts
- pending approvals
- open escalations
- quota alerts

When `.promptclaw/STATE.json` enables the `workspace` integration, prefer:

`python3 .promptclaw/scripts/workspace_snapshot.py --json`

Summarize:
- highest-priority repos
- current branch
- status source (`sdp`, `progress`, or `docs`)
- best available current-focus headline from `progress.md` or `SESSION_NOTES.md`
