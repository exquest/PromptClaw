Run a bounded PromptClaw heartbeat.

Required behavior:
- process inbox
- use the `sdp-cli` bridge when enabled in `.promptclaw/STATE.json`
- use the workspace snapshot when enabled in `.promptclaw/STATE.json`
- groom backlog
- perform one useful bounded action or create one delegation packet
- update state and journal
- avoid vanity commits

Preferred command:

`python3 .promptclaw/scripts/sdp_cli_bridge.py --json`

Additional command:

`python3 .promptclaw/scripts/workspace_snapshot.py --json`
