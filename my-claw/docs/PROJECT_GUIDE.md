# Project Guide

```text
 /\_/\
( o.o )  PromptClaw project guide 🦀✨
 > ^ <
```

## What this project is

This is a PromptClaw project. The orchestrator reads your prompts, routes work to agents,
writes all handoffs to `.promptclaw/`, and pauses only for blocking ambiguity.

## Fastest setup path

1. Run the startup wizard: `promptclaw wizard .`
2. Review `docs/STARTUP_PROFILE.md`
3. Run `promptclaw doctor .`
4. Run `promptclaw bootstrap .`
5. Replace mock agents with live command agents when ready.

## CypherClaw daemon notes

- Set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in the environment before starting `tools/cypherclaw_daemon.py` if you want to override the default bot target.
- Set `PROMPTCLAW_PETS_FILE` if you need the Tamagotchi state persisted somewhere other than `~/.promptclaw/pets.json`.
- Pet controls are available through Telegram with `/pets`, `/feed <agent>`, and `/play <agent>`.
- `tools/cypherclaw_daemon.py` leaves `sdp-cli run` uncapped so the pipeline can use its own tier budgets; only `status` and `tasks list` probes keep a short timeout.
- `tools/sdp_bridge.py` now follows the task's stored lead agent and `sdp-cli`'s verifier selection defaults instead of forcing a fixed Claude/Codex pair.

## Where the wizard writes

- `prompts/00-project-vision.md`
- `prompts/01-agent-roles.md`
- `prompts/02-routing-rules.md`
- `docs/STARTUP_PROFILE.md`
- `docs/STARTUP_TRANSCRIPT.md`
