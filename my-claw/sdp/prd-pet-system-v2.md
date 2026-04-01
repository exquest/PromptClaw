# PRD: Pet System V2 — Multi-Class Evolution & Deep Integration

## Overview

Transform CypherClaw's Tamagotchi pet system from a simple XP/stage tracker into a deep multi-class evolution system where pets develop unique personalities, earn XP from all system activity, gain functional abilities that influence agent selection, and maintain a permanent historical record of their growth. Each pet evolves through unbounded levels across multiple classes, develops shifting personality traits based on real behavior, and can undergo rebirth cycles that carry forward legacy memories.

**Depends on:** `prd-model-awareness.md` (agent selector integration), `prd-glyphweave-art-studio.md` (art generation XP), `prd-local-llm-integration.md` (local model XP)

## Design Principles

1. **Reflect reality** — pet stats mirror what agents actually do, not arbitrary mechanics
2. **Long-term investment** — evolution takes weeks/months, creating a sense of history
3. **Meaningful but not dominant** — functional bonuses are subtle tiebreakers (5-10%), not decisive
4. **Every action counts** — pipeline tasks, chat routing, health checks, art generation all contribute
5. **Permanent record** — daily snapshots create an album of each pet's journey over time

## Class System

### Classes (earned from behavior, not assigned)

| Class | Earned By | Personality Flavor | Functional Bonus |
|-------|-----------|-------------------|-----------------|
| Scholar | Research, analysis, architecture, planning | Contemplative, methodical, quotes philosophers | +5-10% selector score for research/architecture tasks |
| Engineer | Coding, implementation, debugging, testing | Hands-on, fast-talking, shows-not-tells | +5-10% selector score for coding/implementation tasks |
| Explorer | Web search, research, long-context analysis | Curious, tangential, connects distant ideas | +5-10% selector score for research/web tasks |
| Artist | GlyphWeave art generation, image assessment | Aesthetic, expressive, sees beauty in code | +5-10% selector score for art/creative tasks |
| Guardian | Health checks, healing, server maintenance, monitoring | Protective, alert, worries about stability | +5-10% selector score for maintenance/review tasks |
| Diplomat | Routing, classification, multi-agent coordination | Balanced, fair, good at delegation | +5-10% selector score for routing tasks |

Pets accumulate XP in ALL classes simultaneously. The dominant class (highest level) is displayed as primary, but all are tracked.

### Level System (Unbounded, Diminishing Returns)

XP required for level N: `floor(100 * N * ln(N + 1))`

| Level | Total XP Required | Difficulty |
|-------|-------------------|-----------|
| 1 | 69 | Easy — a few tasks |
| 5 | 895 | A solid day of work |
| 10 | 2,397 | Several days |
| 20 | 6,592 | Weeks of consistent use |
| 50 | 22,649 | Months — impressive |
| 100 | 54,612 | Legendary — sustained excellence |

**XP scaling:** Higher-level pets get diminishing XP per action. A Level 1 pet gets full XP; a Level 20 pet gets `XP * (5 / (5 + current_level))` — so at Level 20, they get ~20% of base XP. This prevents runaway leveling while still rewarding continued use.

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| PET-001 | Create PostgreSQL schema for the pet system. Tables: `pets` (id, agent_name, stage, total_xp, energy, mood, hunger, created_at, last_active, incarnation, legacy_json), `pet_class_xp` (pet_id, class_name, xp, level, updated_at), `pet_traits` (pet_id, trait_name, value_float, earned_at, last_updated), `pet_level_events` (pet_id, class_name, old_level, new_level, timestamp), `pet_snapshots` (pet_id, snapshot_date, data_json), `pet_incarnations` (pet_id, incarnation_num, born_at, died_at, peak_level, peak_class, legacy_json). Migrate existing JSON data from `~/.promptclaw/pets.json` to PostgreSQL. | MUST | T2 | - All tables created in cypherclaw_observatory database<br/>- Existing 4 pets migrated with current XP/stage preserved<br/>- pet_class_xp seeded with initial class based on agent personality<br/>- Queries work for all tables |
| PET-002 | Implement the multi-class XP system. Create `tools/pet_classes.py` with: `CLASS_DEFINITIONS` dict mapping class names to descriptions and matching task categories, `award_xp(pet, class_name, base_xp)` that applies diminishing returns based on current level (`xp * 5/(5+level)`), `get_level(xp)` using the natural log formula, `get_dominant_class(pet)` returning the highest-level class. When a pet levels up in any class, fire a level-up event (stored in `pet_level_events`, announced in Telegram). | MUST | T2 | - 6 classes defined with task category mappings<br/>- `award_xp()` applies diminishing returns correctly<br/>- `get_level(100)` returns 1, `get_level(2397)` returns 10<br/>- Level-up events stored in PostgreSQL<br/>- Level-up announced in Telegram with pet portrait |
| PET-003 | Implement XP earning from ALL sources. Create `tools/pet_xp_bridge.py` that awards XP for: (a) sdp-cli pipeline tasks — read from sdp-cli's SQLite `task_runs` table every 30 min, lead agent pet gets +15 XP PASS / +8 PASS_WITH_NOTES / +2 ESCALATED, verify agent pet gets +8 XP; (b) Telegram daemon agent calls — on task_end in existing pet system; (c) routing decisions — cypherclaw pet gets +2 XP per route; (d) health checks — cypherclaw pet gets +1 XP per check; (e) art generation — generating pet gets +10 XP, assessing pet gets +5 XP. XP is assigned to the matching class (coding task → Engineer, research → Explorer, etc.). Track `last_synced_task_id` to avoid double-counting sdp-cli tasks. | MUST | T2 | - sdp-cli task completions award XP to correct pets and classes<br/>- All 5 XP sources working<br/>- No double-counting (last_synced_task_id tracked)<br/>- XP assigned to correct class based on task category<br/>- Sync runs every 30 min via heartbeat |
| PET-004 | Implement full stat impact from activity. When an agent is actively working: energy drains proportional to task duration (`-1 per minute of work`), hunger increases faster (`+1 per 10 min active` vs `+1 per 20 min idle`), mood drops on failure (`-10 per failed task`) and rises on success (`+5 per success`). Token budget consumption maps to energy: `energy = 100 * (remaining_tokens / token_limit)`. When tokens are fully consumed, energy hits 0 and the pet shows as exhausted. Token reset restores energy. | MUST | T2 | - Energy drains during active agent work<br/>- Hunger increases faster when active<br/>- Mood reflects success/failure ratio<br/>- Token budget maps to energy (0 tokens = 0 energy)<br/>- Stats visible in /pets and /pet commands |
| PET-005 | Implement personality traits that evolve from behavior. Traits are continuous floats (-1.0 to 1.0): `boldness` (negative=cautious, positive=bold — shifts toward bold on successes, cautious on failures), `focus` (negative=scattered, positive=focused — shifts toward focused when doing same task type repeatedly), `sociability` (negative=solitary, positive=social — shifts toward social when doing multi-agent/parallel tasks), `creativity` (negative=methodical, positive=creative — shifts toward creative for art/novel tasks). Traits shift by ±0.05 per relevant event, capped at ±1.0. Traits affect narration text in pet_animations.py (bold pet: "charging ahead!", cautious pet: "carefully considering..."). | SHOULD | T2 | - 4 traits tracked per pet as floats<br/>- Traits shift based on actual events<br/>- Trait descriptions change at thresholds (-0.5, 0, 0.5)<br/>- Narration text varies based on traits<br/>- Traits visible in /pet detail view |
| PET-006 | Implement functional bonuses in agent selector. When the daemon's `agent_selector.select()` evaluates agents, add a class bonus: if the task category matches a pet's dominant class, add `min(0.10, pet_level * 0.005)` to that agent's fitness score. This means a Level 10 Engineer adds 5% bonus for coding tasks, capping at 10% (Level 20+). The bonus is a subtle tiebreaker, not a dominant factor. Log when a class bonus influences selection to Observatory. | SHOULD | T2 | - Class bonus added to agent selector scoring<br/>- Bonus caps at 10% (0.10)<br/>- Level 10 in matching class = 5% bonus<br/>- Bonus logged when it changes selection outcome<br/>- Bonus disabled during exploration rolls (10% random selection) |
| PET-007 | Implement the rebirth cycle. If a pet's stats are critical (energy < 5, mood < 5, hunger > 95) for more than 24 hours continuously, trigger rebirth: (a) record the incarnation in `pet_incarnations` with peak_level, peak_class, and legacy_json containing all class XP and traits; (b) reset pet to Egg stage, all class XP to 0, traits to neutral (0.0); (c) set incarnation counter +1; (d) announce rebirth in Telegram with a special animation showing the old pet fading and a new egg appearing; (e) the legacy_json is accessible via `/pet <name> legacy`. Each incarnation's history is preserved forever. | SHOULD | T3 | - Rebirth triggers after 24h of critical stats<br/>- Incarnation recorded with full state<br/>- Pet resets to Egg with clean stats<br/>- Incarnation counter increments<br/>- Legacy viewable via command<br/>- Rebirth animation plays in Telegram |
| PET-008 | Implement daily snapshots. Every day at midnight, snapshot each pet's full state to `pet_snapshots`: all class XP and levels, traits, stats, stage, incarnation. This creates the "album" — a queryable history of how each pet evolved over time. Snapshots are never deleted. Add a `/pet <name> history` command that shows the last 7 snapshots as a compact evolution timeline. | SHOULD | T2 | - Daily snapshot at midnight for all 4 pets<br/>- Snapshot includes all class XP, levels, traits, stats<br/>- `/pet claude history` shows 7-day evolution<br/>- Snapshots stored in PostgreSQL, never deleted<br/>- Snapshot data queryable from gallery dashboard |
| PET-009 | Update `/pets` command for compact multi-class display. Format: one line per pet showing: agent icon, name, dominant class + level, secondary class + level, trait keyword, energy/mood/hunger bars. Example: `🟣 Claude — Scholar 12 / Engineer 8 [Bold] ⚡72 😊85 🍖30`. Keep it under 4 lines per pet so the full display fits in one Telegram message. | MUST | T1 | - `/pets` shows all 4 pets in compact format<br/>- Dominant + secondary class with levels shown<br/>- Trait keyword shown<br/>- Energy/mood/hunger as numbers or small bars<br/>- Fits in one Telegram message |
| PET-010 | Create `/pet <name>` detailed card command. Shows: full ASCII portrait (stage-appropriate), all class levels as bars, all traits with descriptions, current stats with visual bars, XP to next level in dominant class, recent activity log (last 5 XP events), incarnation history summary, current functional bonus. Send as a code block for monospace alignment. | MUST | T2 | - `/pet claude` shows full detail card<br/>- All 6 classes shown with level bars<br/>- Traits shown with descriptive text<br/>- Recent XP events listed<br/>- Incarnation count shown<br/>- Renders correctly in Telegram monospace |
| PET-011 | Migrate the existing pet_sprites.py to support class-influenced portraits. The dominant class should subtly influence the pet's ASCII art: Scholar pets get a book/scroll accessory, Engineers get a wrench/gear, Explorers get a compass, Artists get a paintbrush, Guardians get a shield, Diplomats get a balance scale. These are small 2-3 character additions to the existing stage portraits, not full redesigns. | SHOULD | T2 | - 6 class accessories designed as small ASCII additions<br/>- Dominant class accessory added to pet portrait<br/>- Accessories scale with stage (bigger at higher stages)<br/>- Existing portraits still recognizable<br/>- Works within 30-char width constraint |
| PET-012 | Wire the pet system into the GlyphWeave art pipeline. When a pet appears in generated art (per GW-010), its class, level, and traits should influence the scene: a high-level Scholar Claude might be shown reading ancient texts, a bold Engineer Codex might be shown hammering at a forge, a creative Explorer Gemini might be shown sailing between stars. Pass pet metadata to the art generation prompts. | SHOULD | T2 | - Pet metadata (class, level, traits) available to art engine<br/>- Art prompts reference pet personality<br/>- Generated art scenes reflect pet class<br/>- At least 3 class-specific scene templates |

## Implementation Phases

### Phase 1: Database & Migration (PET-001)
Create PostgreSQL schema, migrate existing JSON data. No behavior changes yet.

### Phase 2: Multi-Class Core (PET-002, PET-003, PET-004)
Implement the class XP system, all XP sources, and full stat impact. Pets start leveling from real activity.

### Phase 3: Display (PET-009, PET-010)
Update Telegram commands to show the new multi-class system. Users can see their pets evolving.

### Phase 4: Personality & Bonuses (PET-005, PET-006)
Add shifting traits and functional selector bonuses. The pet system becomes part of the intelligence layer.

### Phase 5: Lifecycle & History (PET-007, PET-008)
Add rebirth cycles and daily snapshots. Long-term evolution tracking begins.

### Phase 6: Visual Integration (PET-011, PET-012)
Class-influenced portraits and GlyphWeave art integration. Pets look and act their class.

## XP Award Table

| Source | Base XP | Class | Frequency |
|--------|---------|-------|-----------|
| sdp-cli lead: PASS | 15 | task-dependent | Per task |
| sdp-cli lead: PASS WITH NOTES | 8 | task-dependent | Per task |
| sdp-cli lead: ESCALATED | 2 | task-dependent | Per task |
| sdp-cli verify: any | 8 | Guardian | Per task |
| Telegram agent task: success | 10 | task-dependent | Per interaction |
| Telegram agent task: failure | 2 | task-dependent | Per interaction |
| Routing decision | 2 | Diplomat | Per message |
| Health check | 1 | Guardian | Every 30 min |
| Art generation | 10 | Artist | Per piece |
| Art assessment | 5 | Artist | Per assessment |
| Uptime | 1 | Guardian | Per hour |

All base XP subject to diminishing returns: `actual_xp = base_xp * (5 / (5 + current_class_level))`

## Trait Descriptions

| Trait | Range | Low (-1.0 to -0.5) | Neutral (-0.5 to 0.5) | High (0.5 to 1.0) |
|-------|-------|--------------------|-----------------------|-------------------|
| Boldness | -1.0 to 1.0 | "Cautious" — hesitates, double-checks | "Balanced" — measured approach | "Bold" — charges ahead, confident |
| Focus | -1.0 to 1.0 | "Scattered" — jumps between topics | "Adaptable" — switches when needed | "Focused" — deep concentration |
| Sociability | -1.0 to 1.0 | "Solitary" — works alone, quiet | "Cooperative" — works well with others | "Social" — seeks collaboration |
| Creativity | -1.0 to 1.0 | "Methodical" — follows patterns | "Practical" — creative when needed | "Creative" — novel approaches |

## Success Metrics

| Metric | Target |
|--------|--------|
| Pet XP from sdp-cli synced | Every 30 min, no missed tasks |
| Class accuracy | >80% of XP assigned to correct class |
| Level progression | Pets reach Level 5+ within first week |
| Trait stability | Traits don't oscillate wildly (moving average smoothing) |
| Selector bonus impact | <5% of selections changed by pet bonus |
| Snapshot reliability | 100% daily snapshot capture rate |
| Rebirth trigger accuracy | Only triggers on genuinely neglected pets |
