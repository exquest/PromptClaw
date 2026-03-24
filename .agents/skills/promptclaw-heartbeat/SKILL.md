---
name: promptclaw-heartbeat
description: Process inbox items, groom the backlog, and either complete one bounded action or create one delegation packet.
---

# PromptClaw heartbeat

## Workflow
1. Read `.promptclaw/INBOX.md`, `.promptclaw/BACKLOG.md`, `.promptclaw/STATE.json`, and recent journal entries.
2. Process inbox items first.
3. If `.promptclaw/STATE.json` has `integrations.sdp_cli.enabled = true`, run `python3 .promptclaw/scripts/sdp_cli_bridge.py --json`.
4. If `.promptclaw/STATE.json` has `integrations.workspace.enabled = true`, run `python3 .promptclaw/scripts/workspace_snapshot.py --json`.
5. Use the `sdp-cli` bridge summary to prioritize operator-facing work:
   - open escalations first
   - pending approvals next
   - quota alerts and queue pressure after that
6. Use the workspace snapshot to identify which priority repo is active, stale, or under-documented before choosing a bounded action.
7. If there is a clear bounded task:
   - route it
   - complete it if this lane is appropriate
   - otherwise create a delegation packet
8. If there is no meaningful action:
   - write a compact no-op heartbeat entry and stop
9. Update `.promptclaw/STATE.json` and today's journal.
10. Avoid vanity commits when nothing meaningful changed.
