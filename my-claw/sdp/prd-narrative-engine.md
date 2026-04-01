# PRD: GlyphWeave Narrative Engine

## Overview

The Narrative Engine is the brain of CypherClaw's 30-minute automatic art generation cycle. Every piece of GlyphWeave art is driven by a **story beat** — a narrative moment with theme, mood, symbols, characters, and arc position. The engine maintains a **persistent world** (SQLite-backed entity graph + event log) that accumulates narrative history across cycles and sessions, producing coherent, evolving visual storytelling.

**Depends on:** `prd-glyphweave-art-studio.md` (art generation pipeline, scoring rubric), `prd-model-awareness.md` (model registry, agent selector, fitness scoring)

**Key integration points:**
- GlyphWeave DSL (`tools/glyphweave/dsl.py`) — Canvas, Animation, Motif, 6 palettes (WATER, SPACE, CUTE, DRAGON, NIGHT, UI)
- GlyphWeave scenes (`tools/glyphweave/scenes.py`) — CypherClawArt class with startup_banner, status_display, processing_indicator, pet_status_display, pet_interaction_scene
- Tamagotchi pets (`tools/tamagotchi.py`) — 4 pets (claude, codex, gemini, cypherclaw) with mood, energy, hunger, stage
- CypherClaw daemon (`tools/cypherclaw_daemon.py`) — scheduler, agent semaphore, health monitoring
- Healer (`tools/healer.py`) — severity-based self-healing on failure
- Agent selector (`tools/agent_selector.py`) — fitness-based multi-agent selection with rotation
- Ollama (local) — `nomic-embed-text` for embeddings, `qwen3.5:9b` for prose generation

## Design Decisions

1. **Full system** — all 9 phases implemented: data models, world state, embeddings, symbols, arc templates, characters, translator, evaluator, engine, daemon integration
2. **Dual character layer** — 4 Tamagotchi pets exist as "residents" of the narrative world (their agent behavior patterns inform their arcs); 3 abstract archetypal characters ("The Wanderer", "The Shadow", "The Fool") act as narrative "forces" that intersect with the pets
3. **Calibration-first multi-agent prose generation** — 14-day calibration period where ALL available agents/models are tried for prose generation (local Ollama: qwen3.5:9b, qwen3.5:4b, qwen3.5:27b, gemma3:4b, llama3.2:3b; cloud: claude, codex, gemini). 14-day pure round-robin calibration: every agent gets equal attempts in strict rotation for the full 14 days to build comprehensive baseline data. After calibration (day 15+), settle on best-per-task while maintaining 10% exploration. All results recorded in both narrative.db (narrative-specific quality: prose quality, symbol accuracy, tone match, DSL validity) AND Observatory (global fitness). Generate/verify/fix/repeat pattern on every attempt, matching sdp-cli behavior.
4. **30-minute timer with I/O protection** — art cycle runs on fixed 30-min schedule wrapped in `ionice -c3 nice -n19 IOWriteBandwidthMax`; respects the agent semaphore (waits for pipeline tasks to finish, never fights for agent slots)
5. **Template fallback** — if all agents fail prose generation, assemble prose from templates using symbol/tone/arc data; never block the art cycle
6. **Unified scoring** — narrative-specific quality scores (prose quality, symbol accuracy, tone match, DSL validity) feed back into Observatory as weighted signals, so the global agent fitness system learns what's good at narrative prose alongside all other task types

## Architecture

```
tools/narrative/
├── __init__.py
├── engine.py           # NarrativeEngine — main class, entry point
├── world.py            # WorldState — SQLite entity graph + event log
├── memory.py           # NarrativeMemory — nomic-embed-text retrieval via Ollama
├── beat.py             # StoryBeat + GlyphWeavePrompt data models
├── symbols.py          # SymbolLibrary — archetypes, metaphors, tarot, elements
├── structures.py       # ArcTemplates — Hero's Journey, Three-Act, Kishotenketsu etc.
├── tone.py             # ToneController — tone vector space + trajectory
├── characters.py       # CharacterEngine — want/need, personality, relationships
├── evaluator.py        # BeatEvaluator — coherence + quality scoring
├── translator.py       # GlyphWeaveTranslator — StoryBeat -> DSL prompt params
├── migrations/
│   └── 001_initial.sql # World state schema
├── data/
│   ├── archetypes.json  # 12 Jungian archetypes
│   ├── metaphors.json   # 12 conceptual metaphors
│   ├── tarot.json       # 22 Major Arcana
│   └── elements.json    # 5 elements (classical + aether)
└── seed_world.py        # One-time world seeding script

tools/art_cycle.py       # Daemon integration — called every 30 min
```

**Database:** `~/.promptclaw/narrative.db` (SQLite, alongside existing observatory.db)

## The 30-Minute Art Cycle

```
[Timer fires or on-demand trigger]
  1. NarrativeEngine.next_beat()
     a. Get current cycle number + arc position from world state
     b. Select/advance arc template
     c. Compute tone vector at current position
     d. Load context from memory (recent beats + semantic retrieval)
     e. Load character cast; select active characters for this beat
     f. Select symbols for tone + arc position
     g. Generate prose (Ollama -> cloud agents -> template fallback)
     h. Verify prose quality (generate/verify/fix loop, max 3 retries)
     i. Translate to GlyphWeavePrompt via translator
     j. Evaluate beat (6 coherence checks)
     k. On failure: adjust and retry (max 3 attempts)
  2. GlyphWeave renders art from GlyphWeavePrompt
  3. Save rendered output + JSON sidecar with beat metadata
  4. Gallery display refreshes with new art + prose caption
  5. Beat committed to world state + embedded in memory
  6. World state updates (character states, relationship scores, arc progress)
```

## Requirements

### NE-001: Data Files — Jungian Archetypes (T1)
Create `data/archetypes.json` with all 12 Jungian archetypes (hero, shadow, anima, animus, self, persona, trickster, mentor, child, great_mother, wise_old_man, death_rebirth). Each entry: id, narrative_roles, visual_symbols, color_palette, elemental_affinity, animal_totems, emotional_register, glyph_motifs (validated against dsl.py), composition_notes.

### NE-002: Data Files — Metaphors, Tarot, Elements (T1)
Create `data/metaphors.json` (12 conceptual metaphors), `data/tarot.json` (22 Major Arcana with arc_position_hint 0.0-1.0), `data/elements.json` (5 elements with Wu Xing generation/destruction relationships, tone_vector_hints). All glyph_motifs fields validated against dsl.py.

### NE-003: Database Schema (T1)
Create `migrations/001_initial.sql` with tables: entities, relationships, events, beats, character_arcs, embeddings, canon. All tables use TEXT primary keys (UUIDs). Events and beats tables are append-only. Embeddings table stores numpy float32 arrays as BLOBs. Schema must pass `sqlite3 /tmp/test.db < 001_initial.sql` without error.

### NE-004: StoryBeat and GlyphWeavePrompt Data Models (T1)
Create `beat.py` with StoryBeat dataclass (id, cycle_number, session_id, arc_template, arc_position, structure_stage, tone_vector, active_themes, active_symbols, active_characters, prose_description, pregnant_moment, narrative_mode, glyph_prompt, evaluation_scores, passed_evaluation, created_at) and GlyphWeavePrompt dataclass. GlyphWeavePrompt fields must map directly to parameters that dsl.py and scenes.py accept — no invented fields. Valid scene types from scenes.py: startup_banner, status_display, processing_indicator, pet_status_display, pet_interaction_scene. Valid palettes from dsl.py: PALETTE_WATER, PALETTE_SPACE, PALETTE_CUTE, PALETTE_DRAGON, PALETTE_NIGHT, PALETTE_UI.

### NE-005: WorldState — SQLite Entity Graph (T1)
Create `world.py` with WorldState class. Methods: initialize() (runs migrations), upsert_entity/get_entity/get_entities_by_type, upsert_relationship/get_relationships/update_trust, append_event/get_recent_events/get_events_by_character, save_beat/get_last_beat/get_cycle_number, get_arc/update_arc, assert_canon/get_canon/check_contradiction. Default db_path: `~/.promptclaw/narrative.db`. Write tests in `tests/test_narrative_world.py` covering entity round-trip, event log, cycle number, canon contradiction detection. All tests must pass.

### NE-006: NarrativeMemory — Embedding Retrieval (T2)
Create `memory.py` with NarrativeMemory class. Uses Ollama `/api/embeddings` with `nomic-embed-text:latest` for embedding. Store embeddings as `numpy.ndarray.tobytes()` in SQLite BLOB. Cosine similarity via numpy. Methods: embed(text), store_beat(beat), store_event(event), retrieve_similar_beats(query, top_k=5), retrieve_relevant_context(theme_ids, arc_position). Graceful fallback: if Ollama unavailable, skip embedding storage (don't crash). Write tests with mocked Ollama in `tests/test_narrative_memory.py`.

### NE-007: SymbolLibrary — Static Knowledge Access (T1)
Create `symbols.py` with SymbolLibrary class. Loads all 4 JSON data files on init. Methods: get_archetype, get_tarot_card, get_metaphor, get_element, symbols_for_tone(tone_vector), symbols_for_arc_position(arc_position, arc_template), glyph_motifs_for_symbols(symbol_ids). glyph_motifs_for_symbols must validate each motif exists in the live DSL — return only confirmed motifs.

### NE-008: ArcTemplates — Narrative Structure (T2)
Create `structures.py` with 5 arc templates: three_act (6 stages), kishotenketsu (4 stages), heros_journey (8 compressed stages), gag_strip (4 stages), story_circle (8 Dan Harmon steps). Each stage has name, position_range, tension_target, optional is_turn/is_climax flags. ArcTemplates class with: get_stage_for_position, select_template (scores templates against tone/scale/conflict_intensity), advance_arc_position (default ~0.02/cycle, wraps at 1.0).

### NE-009: ToneController — Tone Vector Space (T2)
Create `tone.py` with 8-dimension tone vector (darkness, humor, intimacy, epic_scale, surrealism, irony, consequence_permanence, hope). 5 named trajectories: descent, ascent, oscillating, flat, shattering. ToneController class with: tone_at_position(arc_position), mechanical_params(tone_vector) (returns sentence_length, vocabulary_register, pacing), blend(tone_a, tone_b, weight).

### NE-010: CharacterEngine — Want/Need/Arc Tracking (T2)
Create `characters.py` with Character dataclass (id, name, want, need, awareness_score, arc_type, arc_position, Big Five personality traits, archetype_roles, conflicts, visual_tokens, signature_colors). CharacterEngine class with: load_or_create_cast() (creates 2+ characters if empty, seeding from archetypes), select_active_characters(beat_context), advance_character(character, event), voice_params(character). Starter cast: 3 abstract characters + 4 pet-mapped characters (7 total).

### NE-011: GlyphWeaveTranslator — Beat to DSL Params (T2)
Create `translator.py` with GlyphWeaveTranslator class. On init, load valid scene_types, palette names, and motif names from actual dsl.py/scenes.py source. translate(beat) maps: tone_vector -> scene_type, active_symbols -> palette_name (color overlap matching), symbols -> motifs (max 3), tone -> mood_tokens. validate_prompt(prompt) returns list of errors. Raises TranslationError for any invalid output. Write tests in `tests/test_narrative_translator.py`.

### NE-012: BeatEvaluator — 6 Coherence Checks (T2)
Create `evaluator.py` with BeatEvaluator class. 6 binary checks: check_canon_consistency (entity states match world state), check_arc_validity (position within 0.05 of expected), check_symbol_coherence (no climax symbols before arc_position 0.7, tone alignment), check_novelty (no symbol/prose repetition from last 3 beats), check_character_continuity (arcs advance, awareness respected), check_glyph_prompt_validity (translator validation). All 6 must pass for beat acceptance. Write tests in `tests/test_narrative_evaluator.py`.

### NE-013: NarrativeEngine — Main Entry Point (T2)
Create `engine.py` with NarrativeEngine class. Wires all components (world, memory, symbols, arcs, tone, characters, evaluator, translator). Primary method: next_beat() implements the full algorithm (steps 1a-1k from the cycle spec). Prose generation uses calibration-aware agent selection (see NE-017): during calibration, agents are rotated per schedule; after calibration, best agent is selected with 10% exploration. Every prose generation attempt follows generate/verify/fix pattern. On total failure (all agents), use template-based fallback. Max 3 retry attempts on evaluation failure. Never block — after 3 failures, use last attempted beat with passed_evaluation=False. Also: generate_world_summary(), force_arc_event(event_type). Write tests in `tests/test_narrative_engine.py` with mocked agents.

### NE-017: Calibration System — Multi-Agent Prose Scoring (T2)
Create prose generation calibration aligned with Art Studio PRD's calibration schedule. Available agents: local Ollama (qwen3.5:9b, qwen3.5:4b, qwen3.5:27b, gemma3:4b, llama3.2:3b) + cloud (claude, codex, gemini). Phase 1 (days 1-14): pure round-robin, every agent gets strictly equal attempts in rotation. No optimization during this period — pure data collection. Phase 2 (day 15+): settled selection using accumulated scores, with 10% exploration to detect model improvements over time. Score each attempt on 4 narrative-specific dimensions: prose_quality (coherence, vividness), symbol_accuracy (symbols correctly referenced), tone_match (output tone matches requested tone_vector), dsl_validity (translator accepts the output). Record scores in narrative.db AND feed weighted signal to Observatory for global agent fitness. Use agent_selector.py for routing with a new `"narrative_prose"` task category.

### NE-014: Art Cycle Integration (T2)
Create `tools/art_cycle.py` with run_art_cycle(config) function. Full cycle: instantiate NarrativeEngine, call next_beat(), pass GlyphWeavePrompt to GlyphWeave renderer, save output + JSON sidecar, trigger gallery refresh. Returns result dict with success, beat_id, image_path, prose_description, arc_position, evaluation_passed. get_engine_status() for daemon health reporting. Hook into daemon's art generation scheduler (single call, don't modify daemon extensively). On failure, notify healer with gate_failure event. Wrap execution in I/O protection (ionice/nice). Respect agent semaphore for cloud agent calls.

### NE-015: Beat Metadata Sidecar (T1)
Every rendered image gets a `.json` sidecar with: beat_id, cycle_number, arc_position, arc_template, structure_stage, prose_description, pregnant_moment, active_symbols, tone_vector, evaluation_passed, generated_at. This is the gallery display's source of truth for story context shown alongside each image.

### NE-016: World Seeding Script (T1)
Create `tools/narrative/seed_world.py`. Seeds: 3 abstract characters (The Wanderer/hero, The Shadow/shadow, The Fool/trickster) + 4 pet-mapped characters (one per agent pet, roles derived from agent behavior patterns). Each with want/need pair creating dramatic tension. 5 opening canon facts. Arc_position 0.0, awareness_score 0.1. Logs "world_genesis" event. Idempotent — running twice does not duplicate records.

## Acceptance Criteria

1. All JSON data files are valid JSON with glyph_motifs validated against dsl.py
2. SQL schema creates without error
3. WorldState round-trips entities, events, beats, canon correctly
4. NarrativeMemory embeds and retrieves with cosine similarity (mocked Ollama in tests)
5. SymbolLibrary loads all data and queries by tone/arc_position correctly
6. ArcTemplates selects appropriate template for given parameters
7. ToneController interpolates tone vectors along trajectories
8. CharacterEngine seeds cast on empty world, selects active characters correctly
9. GlyphWeaveTranslator produces only valid DSL parameters — raises on invalid
10. BeatEvaluator catches canon violations, arc regressions, symbol repetition, invalid prompts
11. NarrativeEngine.next_beat() returns a complete StoryBeat with all fields
12. Retry logic engages on failure; template fallback engages when all agents fail
13. art_cycle.py runs end-to-end, writes image + sidecar, respects I/O limits
14. seed_world.py creates 7 characters, 5 canon facts, 1 genesis event idempotently
15. All tests pass: `pytest tests/test_narrative_*.py -v`

## Task Decomposition

| ID | Description | Tier | Dependencies |
|----|-------------|------|-------------|
| NE-001 | Create `tools/narrative/data/archetypes.json` with all 12 Jungian archetypes. Each entry: id, narrative_roles, visual_symbols, color_palette, elemental_affinity, animal_totems, emotional_register, glyph_motifs (validated against dsl.py), composition_notes. | T1 | — |
| NE-002 | Create `tools/narrative/data/metaphors.json` (12 conceptual metaphors), `data/tarot.json` (22 Major Arcana with arc_position_hint), `data/elements.json` (5 elements with Wu Xing relationships and tone_vector_hints). All glyph_motifs validated against dsl.py. | T1 | — |
| NE-003 | Create `tools/narrative/migrations/001_initial.sql` with tables: entities, relationships, events, beats, character_arcs, embeddings, canon. All TEXT primary keys. Must pass `sqlite3 /tmp/test.db < 001_initial.sql` without error. | T1 | — |
| NE-004 | Create `tools/narrative/beat.py` with StoryBeat and GlyphWeavePrompt dataclasses. GlyphWeavePrompt fields must map directly to dsl.py/scenes.py parameters — no invented fields. Valid palettes: PALETTE_WATER, PALETTE_SPACE, PALETTE_CUTE, PALETTE_DRAGON, PALETTE_NIGHT, PALETTE_UI. | T1 | — |
| NE-005 | Create `tools/narrative/world.py` — WorldState class with SQLite entity graph. Methods: initialize, upsert_entity, get_entity, get_entities_by_type, upsert_relationship, get_relationships, update_trust, append_event, get_recent_events, save_beat, get_last_beat, get_cycle_number, get_arc, update_arc, assert_canon, get_canon, check_contradiction. Default db: ~/.promptclaw/narrative.db. Write tests in tests/test_narrative_world.py. | T1 | NE-003, NE-004 |
| NE-006 | Create `tools/narrative/memory.py` — NarrativeMemory class using Ollama nomic-embed-text for embeddings. Store as numpy bytes in SQLite BLOB. Cosine similarity via numpy. Methods: embed, store_beat, store_event, retrieve_similar_beats, retrieve_relevant_context. Graceful fallback if Ollama unavailable. Write tests with mocked Ollama in tests/test_narrative_memory.py. | T2 | NE-005 |
| NE-007 | Create `tools/narrative/symbols.py` — SymbolLibrary class. Loads all 4 JSON data files. Methods: get_archetype, get_tarot_card, get_metaphor, get_element, symbols_for_tone, symbols_for_arc_position, glyph_motifs_for_symbols (validates against live DSL). | T1 | NE-001, NE-002 |
| NE-008 | Create `tools/narrative/structures.py` — 5 arc templates (three_act, kishotenketsu, heros_journey, gag_strip, story_circle) with stages, tension targets, turn/climax flags. ArcTemplates class: get_stage_for_position, select_template, advance_arc_position (~0.02/cycle, wraps at 1.0). | T2 | — |
| NE-009 | Create `tools/narrative/tone.py` — 8-dimension tone vector (darkness, humor, intimacy, epic_scale, surrealism, irony, consequence_permanence, hope). 5 trajectories (descent, ascent, oscillating, flat, shattering). ToneController: tone_at_position, mechanical_params, blend. | T2 | — |
| NE-010 | Create `tools/narrative/characters.py` — Character dataclass with Big Five personality, want/need, awareness_score, arc_type, archetype_roles, conflicts, visual_tokens. CharacterEngine: load_or_create_cast (seeds 3 abstract + 4 pet-mapped characters), select_active_characters, advance_character, voice_params. | T2 | NE-005, NE-007 |
| NE-011 | Create `tools/narrative/translator.py` — GlyphWeaveTranslator. Reads valid scene_types, palettes, motifs from dsl.py/scenes.py at init. translate(beat) maps tone->scene_type, symbols->palette, symbols->motifs (max 3). validate_prompt returns errors. Raises TranslationError for invalid output. Write tests in tests/test_narrative_translator.py. | T2 | NE-004, NE-007 |
| NE-012 | Create `tools/narrative/evaluator.py` — BeatEvaluator with 6 checks: canon_consistency, arc_validity, symbol_coherence, novelty (no repetition from last 3 beats), character_continuity, glyph_prompt_validity. All must pass for beat acceptance. Write tests in tests/test_narrative_evaluator.py. | T2 | NE-005, NE-006, NE-011 |
| NE-013 | Create `tools/narrative/engine.py` — NarrativeEngine main class. Wires all components. next_beat() implements full algorithm. Uses calibration-aware agent selection for prose generation. Generate/verify/fix pattern. Template fallback on total failure. Max 3 retries. Also: generate_world_summary, force_arc_event. Write tests in tests/test_narrative_engine.py. | T2 | NE-005 thru NE-012, NE-017 |
| NE-014 | Create `tools/art_cycle.py` — daemon integration. run_art_cycle(config): instantiate engine, next_beat, render via GlyphWeave, save output + sidecar, trigger gallery refresh. Wrapped in I/O protection. Respects agent semaphore. Notifies healer on failure. get_engine_status for health reporting. | T2 | NE-013 |
| NE-015 | Implement beat metadata sidecar — every rendered image gets a .json sidecar with beat_id, cycle_number, arc_position, arc_template, structure_stage, prose_description, pregnant_moment, active_symbols, tone_vector, evaluation_passed, generated_at. | T1 | NE-004 |
| NE-016 | Create `tools/narrative/seed_world.py` — seeds 3 abstract characters (Wanderer/hero, Shadow/shadow, Fool/trickster) + 4 pet-mapped characters. Want/need pairs with triangular tension. 5 opening canon facts. world_genesis event. Idempotent (upsert). | T1 | NE-005, NE-007, NE-010 |
| NE-017 | Create calibration system for multi-agent prose scoring. 14-day pure round-robin across all agents (Ollama: qwen3.5:9b/4b/27b, gemma3:4b, llama3.2:3b; cloud: claude, codex, gemini). Score on 4 dimensions: prose_quality, symbol_accuracy, tone_match, dsl_validity. Record in narrative.db AND Observatory. After day 14: best-per-task with 10% exploration. Add narrative_prose category to agent_selector.py. | T2 | NE-005, NE-013 |
