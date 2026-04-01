# PRD: PromptClaw Federation — Networked Instance Communication

## Overview

A secure, invite-only federation protocol that allows multiple PromptClaw instances to communicate as peers. Each instance has a cryptographic identity (name + keypair), exposes a signed REST API, and collaborates with other instances through status sharing, task delegation, shared knowledge, coherence enforcement, and social interaction — all governed by layered permissions.

**This is a core PromptClaw feature** — it lives in the `promptclaw/` package, not in CypherClaw-specific tools.

## Design Decisions

1. **Invite-only federation** — new instances join by having their public key added to a trusted registry by an existing owner-level member. No open discovery.
2. **Human-readable name + Ed25519 keypair** — each instance gets a name (e.g., "cypherclaw") and a cryptographic keypair. Name is display, key proves identity. All messages are signed.
3. **Full collaboration** — status, task delegation, shared knowledge (decisions, canon), shared coherence (constitutional rules), narrative world state, art, and social (discussion, debate, discovery sharing).
4. **HTTP/REST with signed JSON** — each instance exposes a FastAPI endpoint. Messages are JSON payloads signed with Ed25519. Works over Tailscale, public internet, or local network. No broker.
5. **Layered permissions** — instance-level roles (owner/collaborator/observer) set the ceiling. Per-data-type visibility (public/shared/private) narrows further. Observer can never delegate tasks. Collaborator sees shared but not private.

## Identity

Each PromptClaw instance generates identity on first init:

```json
{
  "instance_id": "cypherclaw",
  "display_name": "CypherClaw",
  "public_key": "ed25519:base64...",
  "created_at": "2026-03-29T00:00:00Z",
  "capabilities": ["status", "tasks", "knowledge", "coherence", "narrative", "art"],
  "endpoint": "https://cypherclaw.tail1234.ts.net:8443/federation/v1"
}
```

Private key stored in `.promptclaw/federation/identity.key` (never shared, never committed to git).
Public identity stored in `.promptclaw/federation/identity.json`.

## Permission Model

### Instance Roles (ceiling)

| Role | Status | Tasks | Knowledge | Coherence | Narrative | Art |
|------|--------|-------|-----------|-----------|-----------|-----|
| **owner** | read/write | delegate/receive | read/write | enforce | full access | full access |
| **collaborator** | read | delegate/receive | read + propose | read | read shared | read shared |
| **observer** | read | none | read public | read public | read public | read public |

### Per-Data-Type Visibility (narrowing)

Each data category can be set to:
- **public** — any authenticated network member can access
- **shared** — only specific named instances can access
- **private** — local only, never transmitted

Default for new instances: status=public, tasks=shared, knowledge=shared, coherence=shared, narrative=private, art=public.

## Message Protocol

All messages are signed JSON:

```json
{
  "from": "cypherclaw",
  "to": "macbook-claw",
  "type": "task_delegate",
  "payload": { ... },
  "timestamp": "2026-03-29T13:00:00Z",
  "nonce": "random-uuid",
  "signature": "ed25519:base64..."
}
```

Message types:
- `heartbeat` — periodic status (load, pipeline progress, capabilities)
- `task_delegate` — send a task to another instance for execution
- `task_result` — return results from a delegated task
- `knowledge_share` — share decisions, canon facts, discoveries
- `coherence_sync` — share constitutional rules, violation reports
- `narrative_update` — share world state changes, story beats
- `art_share` — share generated art pieces with metadata
- `social` — free-form discussion, debate, questions between instances
- `join_request` — new instance requesting to join the network
- `join_approved` — owner approving a join request (includes the new instance's public key)

## API Endpoints

Each instance exposes on its federation port:

```
POST /federation/v1/message       — receive a signed message
GET  /federation/v1/identity      — return public identity (public)
GET  /federation/v1/status        — return current status (permission-gated)
GET  /federation/v1/capabilities  — return what this instance can do (public)
POST /federation/v1/join          — request to join this instance's network
GET  /federation/v1/network       — list known instances (owner only)
```

## Architecture

```
promptclaw/federation/
├── __init__.py
├── identity.py          # Keypair generation, signing, verification
├── registry.py          # Trusted instance registry (who's in the network)
├── permissions.py       # Role + data-type permission evaluation
├── transport.py         # HTTP client — send signed messages to peers
├── server.py            # FastAPI endpoints — receive messages from peers
├── protocol.py          # Message types, validation, serialization
├── sync.py              # Knowledge, coherence, narrative sync logic
├── delegation.py        # Task delegation — send work to peers, receive results
└── discovery.py         # Capability announcement, heartbeat management
```

## Requirements

| ID | Description | Tier |
|----|-------------|------|
| FD-001 | Create `promptclaw/federation/identity.py` — Ed25519 keypair generation on first init. Store private key in `.promptclaw/federation/identity.key`, public identity in `identity.json`. Sign and verify message functions. Use `cryptography` library. | T1 |
| FD-002 | Create `promptclaw/federation/protocol.py` — define all message types as dataclasses. Validation, serialization to/from JSON. Nonce for replay protection. Timestamp validation (reject messages older than 5 minutes). | T1 |
| FD-003 | Create `promptclaw/federation/registry.py` — SQLite-backed trusted instance registry. Add/remove instances. Store public keys, roles, per-data-type permissions. Join request/approval workflow. | T1 |
| FD-004 | Create `promptclaw/federation/permissions.py` — evaluate whether instance X can perform action Y on data type Z. Layered check: role ceiling first, then data-type visibility. Return allow/deny with reason. | T1 |
| FD-005 | Create `promptclaw/federation/transport.py` — HTTP client for sending signed messages to peer endpoints. Retry with backoff on failure. Queue messages for offline peers. Verify response signatures. | T2 |
| FD-006 | Create `promptclaw/federation/server.py` — FastAPI app exposing federation endpoints. Verify incoming message signatures. Check permissions before processing. Rate limiting per instance. | T2 |
| FD-007 | Create `promptclaw/federation/delegation.py` — task delegation protocol. Send task to peer, track status, receive result. Respect agent semaphore on receiving end. Report delegation to Observatory. | T2 |
| FD-008 | Create `promptclaw/federation/sync.py` — sync shared knowledge (decisions, canon), coherence rules (constitutional violations), and narrative state between instances. Conflict resolution: last-write-wins for facts, union for rules. | T2 |
| FD-009 | Create `promptclaw/federation/discovery.py` — periodic heartbeat broadcast to all known instances. Capability announcements. Detect offline instances. Update registry with last-seen timestamps. | T2 |
| FD-010 | Add `promptclaw init` federation setup — on project init, generate keypair and create identity. Add `--join-network` flag to request joining an existing instance's network. | T1 |
| FD-011 | Add federation CLI commands: `promptclaw federation status` (show network), `promptclaw federation invite` (generate join token), `promptclaw federation join` (join with token), `promptclaw federation send` (send message to peer). | T2 |
| FD-012 | Integration with CypherClaw daemon — register CypherClaw as a federation instance, expose federation API on a configurable port, handle incoming messages in the daemon's event loop. Add `/network` Telegram command showing connected instances. | T2 |
| FD-013 | Art sharing — when gallery gets new art, optionally broadcast to network peers with art=public or art=shared. Receiving instances add to their own gallery. Includes beat metadata sidecar. | T2 |
| FD-014 | Write comprehensive tests: identity signing/verification round-trip, permission evaluation (all role x visibility combinations), message serialization, replay protection, delegation lifecycle, sync conflict resolution. TDD — tests first. | T2 |
