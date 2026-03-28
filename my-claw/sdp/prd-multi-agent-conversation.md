# PRD: Multi-Agent Conversation System

## Overview

Elevate the existing three-way chat (Anthony, CypherClaw, MacBook Claude) into a first-class multi-agent conversation system. All entities -- Anthony, CypherClaw, MacBook Claude, and any spawned agents -- participate as peers on a shared conversation bus. The Redis-backed event stream and inbox system already handles N-participant messaging. This PRD adds the missing coordination layer: structured turn-taking, cross-participant context sharing, topic tracking, and automatic decision extraction so that conversations produce actionable outcomes rather than sprawling threads.

**Depends on:** Redis conversation bus (existing), event stream + inbox system (existing), `prd-proactive-intelligence.md` (context injection), `prd-verification-system.md` (message verification)

## Design Principles

1. **Peers, not hierarchy** -- every participant (human or agent) has equal speaking rights. Priority is granted by topic relevance, not role.
2. **Context is shared, not repeated** -- participants inject their unique context once; the bus distributes it. No re-explaining across agents.
3. **Conversations produce decisions** -- every multi-turn exchange should either resolve a question, record a decision, or explicitly mark itself as "ongoing."
4. **Graceful degradation** -- if one participant disconnects, the conversation continues. Missed messages are queued in their inbox.
5. **Transparent coordination** -- turn-taking and topic tracking are visible metadata, not hidden orchestration.

## Architecture

```
                    +------------------+
                    |  Conversation    |
                    |    Manager       |
                    | (topic tracking, |
                    |  turn-taking,    |
                    |  decision        |
                    |  extraction)     |
                    +--------+---------+
                             |
                     +-------+-------+
                     | Redis         |
                     | Conversation  |
                     | Bus           |
                     | (pub/sub +    |
                     |  streams)     |
                     +-------+-------+
                             |
         +----------+--------+--------+-----------+
         |          |                 |            |
    +----+----+ +---+------+ +-------+---+ +------+------+
    | Anthony  | | Cypher-  | | MacBook   | | Spawned     |
    | (Telegram| | Claw     | | Claude    | | Agents      |
    |  + Web)  | | (daemon) | | (sdp-cli) | | (task-spec) |
    +----------+ +----------+ +-----------+ +-------------+
```

### Message Flow

1. A participant posts a message to the bus via `XADD conversation:{topic_id}`.
2. The Conversation Manager consumes the message, updates topic state, and evaluates turn-taking rules.
3. If another participant is next in the turn order (or the message is addressed to them), the Manager routes a notification to their inbox.
4. The addressed participant reads the message, formulates a response with their context injected, and posts back to the bus.
5. At key junctures (agreement, explicit decision, or vote), the Decision Extractor parses the exchange and records an ADR via the Coherence Engine.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|----|-------------|----------|------|---------------------|
| MAC-001 | Create `ConversationManager` class that coordinates all multi-agent conversations. Maintains a registry of active conversations, their participants, current topic, and turn state. Backed by Redis hashes. | MUST | T1 | - Manager tracks active conversations<br/>- Participant list per conversation<br/>- Topic and turn state persisted in Redis<br/>- Manager recoverable after restart |
| MAC-002 | Implement structured message format: every message on the bus includes `sender`, `addressed_to` (optional, list), `topic_id`, `message_type` (statement, question, proposal, decision, ack), `context_refs` (list of prior message IDs), `timestamp`, and `body`. | MUST | T1 | - All fields present in every message<br/>- Schema validated on publish<br/>- Invalid messages rejected with error<br/>- Backwards compatible with existing 3-way format |
| MAC-003 | Implement turn-taking protocol. Rules: (a) addressed participant speaks next, (b) if no addressee, round-robin among active participants, (c) Anthony always has interrupt priority, (d) agents yield after 2 consecutive messages without human response, (e) configurable timeout per turn (default 60s for agents, unlimited for Anthony). | MUST | T2 | - Addressed participant notified within 1s<br/>- Round-robin fair across participants<br/>- Anthony can interrupt any time<br/>- Agent yield after 2 consecutive messages<br/>- Turn timeout triggers next participant<br/>- Turn order visible in conversation metadata |
| MAC-004 | Implement context injection for each participant. Before a participant responds, the Manager assembles a context window: (a) last N messages in the conversation (configurable, default 20), (b) any referenced messages, (c) the participant's unique context (e.g., CypherClaw's server state, MacBook Claude's local file system state), (d) relevant architectural decisions from the Coherence Engine. | MUST | T2 | - Context window assembled before each turn<br/>- Last N messages included<br/>- Referenced messages resolved<br/>- Participant-specific context injected<br/>- Coherence decisions included when relevant<br/>- Total context stays under model token limit |
| MAC-005 | Implement topic tracking. Each conversation has a `topic_id` and `topic_summary` that evolves. The Manager detects topic drift (>3 messages diverging from original topic) and either forks a new conversation or asks participants to refocus. Topic tags are extracted from message content. | MUST | T2 | - Topic ID assigned at conversation start<br/>- Topic summary updated after each message<br/>- Drift detected after 3 divergent messages<br/>- Fork or refocus suggested on drift<br/>- Topic tags extracted and searchable |
| MAC-006 | Implement decision extraction. When a conversation contains a proposal followed by agreement from 2+ participants, extract the decision and record it via `CoherenceEngine.record_decision()`. Decisions include: what was decided, who agreed, the conversation context, and affected file paths if mentioned. | MUST | T2 | - Proposals detected by message_type or keyword<br/>- Agreement tracked per participant<br/>- Decision recorded when 2+ agree<br/>- Decision includes full provenance<br/>- Recorded via Coherence Engine API<br/>- Participants notified of recorded decision |
| MAC-007 | Implement participant management: join, leave, and presence. New agents can join mid-conversation. Participants can leave gracefully (sends departure message) or disconnect (detected by heartbeat timeout). Presence status: active, idle, disconnected. | MUST | T1 | - Join adds participant to conversation<br/>- Leave sends departure notification<br/>- Heartbeat every 30s for agents<br/>- Disconnect detected within 60s<br/>- Presence status queryable<br/>- Participant list updates broadcast to all |
| MAC-008 | Implement conflict resolution protocol. When two agents disagree: (a) each states their position with evidence, (b) other agents can weigh in, (c) if no consensus after 3 rounds, escalate to Anthony with a summary of positions. Votes are tracked per participant. | SHOULD | T3 | - Disagreement detected from contradictory proposals<br/>- Evidence-based position statements requested<br/>- Voting tracked per participant<br/>- 3-round limit before escalation<br/>- Anthony receives summary with positions and evidence<br/>- Resolution recorded as decision |
| MAC-009 | Implement conversation memory and search. Completed conversations are archived with their topic, participants, decisions, and full transcript. Searchable by topic, participant, date range, and keywords. Retention: 90 days in Redis, then archived to SQLite. | SHOULD | T2 | - Completed conversations archived<br/>- Search by topic, participant, date, keyword<br/>- Redis retention 90 days<br/>- SQLite archive for older conversations<br/>- Archive queryable via CLI |
| MAC-010 | Add conversation threading. A message can spawn a sub-thread (linked by `parent_message_id`). Sub-threads have their own turn order but inherit the parent topic. Sub-threads auto-close after 5 minutes of inactivity and their summary is posted to the parent. | SHOULD | T3 | - Sub-thread creation from any message<br/>- Parent topic inherited<br/>- Independent turn order in sub-thread<br/>- Auto-close after 5 min inactivity<br/>- Summary posted to parent on close<br/>- Sub-threads visible in conversation view |
| MAC-011 | Implement message priority levels: `normal`, `urgent`, `fyi`. Urgent messages bypass turn-taking and notify all participants immediately. FYI messages are delivered but do not advance the turn. | MUST | T1 | - Three priority levels supported<br/>- Urgent bypasses turn order<br/>- Urgent triggers immediate notification<br/>- FYI delivered without advancing turn<br/>- Priority visible in message metadata |
| MAC-012 | Create CLI commands for conversation management: `promptclaw conversation list`, `promptclaw conversation show <id>`, `promptclaw conversation search --topic <t> --participant <p>`, `promptclaw conversation decisions <id>`. | SHOULD | T2 | - List active and recent conversations<br/>- Show full conversation transcript<br/>- Search by topic and participant<br/>- List decisions from a conversation<br/>- Output as formatted JSON |
| MAC-013 | Implement rate limiting per participant. Agents limited to 10 messages/minute per conversation. Anthony unlimited. Burst allowance of 3 messages. Rate limit violations logged to Observatory. | MUST | T2 | - Agent rate limit: 10 msg/min<br/>- Anthony unlimited<br/>- Burst of 3 allowed<br/>- Rate limit violations logged<br/>- Exceeded limit queues messages rather than dropping |
| MAC-014 | Implement cross-conversation context. When a participant references a topic from another conversation (detected by topic tag or explicit link), the Manager fetches the relevant summary and injects it as context. Prevents the "we discussed this already" problem. | SHOULD | T3 | - Cross-references detected by tag or link<br/>- Referenced conversation summary fetched<br/>- Summary injected as context<br/>- Source conversation credited<br/>- Works across archived conversations |
| MAC-015 | Add observability: emit structured events to Observatory for every conversation lifecycle event (created, participant_joined, message_sent, topic_drifted, decision_extracted, conversation_closed). Dashboard shows active conversations, message volume, and decision throughput. | MUST | T2 | - All lifecycle events emitted<br/>- Events include conversation_id and participant<br/>- Observatory dashboard section for conversations<br/>- Message volume chart (per hour)<br/>- Decision throughput visible<br/>- Latency between turns tracked |
| MAC-016 | Implement message acknowledgement. Each message gets a delivery receipt when read by the addressed participant. Unacknowledged messages after turn timeout are re-delivered once, then flagged as missed. | SHOULD | T3 | - Delivery receipt on read<br/>- Unacknowledged messages re-delivered after timeout<br/>- Missed messages flagged<br/>- Acknowledgement visible in message metadata<br/>- Re-delivery limited to 1 retry |

## Implementation Phases

### Phase 1: Foundation (T1) -- Week 1-2
- MAC-001: ConversationManager core
- MAC-002: Structured message format
- MAC-007: Participant management and presence
- MAC-011: Message priority levels

**Milestone:** Agents can join a conversation, send structured messages, and see each other's presence. Replaces ad-hoc 3-way chat with formal bus protocol.

### Phase 2: Coordination (T2) -- Week 3-4
- MAC-003: Turn-taking protocol
- MAC-004: Context injection
- MAC-005: Topic tracking
- MAC-006: Decision extraction
- MAC-009: Conversation memory and search
- MAC-013: Rate limiting
- MAC-015: Observability

**Milestone:** Conversations are coordinated with fair turn-taking, shared context, tracked topics, and automatically extracted decisions. Full observability.

### Phase 3: Advanced (T3) -- Week 5-6
- MAC-008: Conflict resolution protocol
- MAC-010: Conversation threading
- MAC-012: CLI commands
- MAC-014: Cross-conversation context
- MAC-016: Message acknowledgement

**Milestone:** Full multi-agent conversation system with threading, conflict resolution, cross-conversation context, and CLI management.

## Success Metrics

| Metric | Target |
|--------|--------|
| Message delivery latency | <500ms between send and inbox delivery |
| Turn-taking fairness | No participant gets >40% of turns in a 5+ participant conversation |
| Decision extraction accuracy | >80% of explicit agreements captured as decisions |
| Context injection relevance | >90% of injected context rated useful by reviewing agent |
| Topic drift detection | >75% of significant topic changes detected |
| Conversation completion rate | >90% of conversations produce at least 1 decision or explicit close |
| Participant reconnection time | <5s to rejoin after disconnect |
| Conflict resolution rate | >70% resolved without Anthony escalation |
| Message loss rate | 0% (all messages delivered or flagged as missed) |
| Archive search latency | <2s for keyword search across 90 days |
