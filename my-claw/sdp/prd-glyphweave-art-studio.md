# PRD: GlyphWeave Art Studio — CypherClaw as Generative Artist

## Overview

Transform CypherClaw from a system that *uses* GlyphWeave art into one that *creates* it. Every 30 minutes, CypherClaw generates a new original GlyphWeave artwork — static or animated — featuring its Tamagotchi pets, using a scientific experimentation framework that tests every available LLM model at every effort/temperature setting to discover what produces the best hybrid ASCII+emoji art. Results are displayed in Telegram alongside health checks, served through an interactive web gallery, and tracked with detailed statistics. A 3-day calibration period runs first to map the model-quality landscape before settling on optimal configurations.

**Depends on:** `prd-model-awareness.md` (model registry, model selector, per-model fitness scoring — currently being implemented by sdp-cli on server), `prd-glyphweave-studio-loop.md` (fast preview/watch loop, context compaction, source-map/indexing, golden render fixtures)

**Reference:** `glyphweave-foundations.md` (research document, copied to server at `/home/user/cypherclaw/docs/glyphweave-foundations.md`)

## Design Principles (from Research)

1. **Constraint is generative** — fixed grid, limited vocabulary, defined palettes enable creativity
2. **Two-phase LLM generation** — free reasoning/planning phase, then constrained grid output
3. **Modular composition over freeform** — assemble pre-defined blocks; LLMs are far more reliable this way
4. **Image export is non-negotiable** — emoji width inconsistencies across platforms require a rasterization layer
5. **Small grids win** — under 15x15 for reliable generation, but calibration tests the full range
6. **Programmatic verification loops** — generate → validate → feedback → refine (3-5 iterations max)
7. **The cell model must be grapheme-cluster-native** — store EGC strings with explicit display widths

## Scoring Rubric (User-Defined Priority Order)

| Weight | Criterion | Description | Score Range |
|--------|-----------|-------------|-------------|
| 30% | Use of Medium | Leverages hybrid ASCII+emoji nature; not just one or the other; exploits grid, palettes, motifs | 1-10 |
| 25% | Visual Appeal | Pleasing to look at; good composition, color harmony, balance | 1-10 |
| 20% | Expressiveness | Conveys emotion, tells a story, feels alive; pet personality comes through | 1-10 |
| 15% | Creativity | Surprising, novel, doing something unexpected with the medium | 1-10 |
| 10% | Technical Precision | Lines aligned, widths correct, no rendering glitches, valid AEAF | 1-10 |

Composite score = (medium * 0.30) + (appeal * 0.25) + (expression * 0.20) + (creativity * 0.15) + (precision * 0.10)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    GlyphWeave Art Studio                        │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │  Art Engine   │  │  Experiment  │  │   Gallery Server      │ │
│  │  (generator)  │  │  Framework   │  │   (FastAPI + HTMX)    │ │
│  │              │  │  (calibrator) │  │                       │ │
│  │ - plan phase │  │ - model grid │  │ - browse/filter       │ │
│  │ - gen phase  │  │ - param sweep│  │ - remix/variations    │ │
│  │ - validate   │  │ - scoring    │  │ - live canvas         │ │
│  │ - assess     │  │ - statistics │  │ - stats dashboard     │ │
│  │ - render PNG │  │ - leaderboard│  │ - PNG/text/AEAF view  │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────┘ │
│         │                 │                       │             │
│  ┌──────┴─────────────────┴───────────────────────┴───────────┐ │
│  │                    Art Repository (PostgreSQL)              │ │
│  │  artworks, experiments, model_scores, generation_logs      │ │
│  └────────────────────────────┬────────────────────────────────┘ │
│                               │                                 │
│  ┌────────────────────────────┴────────────────────────────────┐ │
│  │              Integration Layer                              │ │
│  │  - Daemon scheduler (30-min cycle)                         │ │
│  │  - Telegram display (text + PNG)                           │ │
│  │  - Model Registry (from model-awareness PRD)               │ │
│  │  - Observatory (event logging)                             │ │
│  │  - Pet system (Tamagotchi state for scene context)         │ │
│  └─────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| GW-001 | Create `tools/art_engine.py` implementing the two-phase generation pipeline: Phase 1 (Plan) — LLM describes layout, theme, palette, pet placement in natural language; Phase 2 (Generate) — LLM writes Canvas DSL code that produces the artwork. Both phases use the existing GlyphWeave DSL (`tools/glyphweave/dsl.py`). The engine accepts parameters: model_id, effort_level, temperature (if supported), art_type (static/animated), dimensions (width x height), theme, pets_to_feature, and palette. Returns a GenerationResult with the artwork, code, validation results, and timing. | MUST | T2 | - Engine produces valid Canvas output for static art<br/>- Engine produces valid AEAF output for animated art<br/>- Plan phase output is parseable natural language layout<br/>- Generate phase produces executable DSL code<br/>- All parameters are respected in output<br/>- Generation times are recorded in result |
| GW-002 | Create `tools/art_validator.py` implementing programmatic verification loops. After each generation attempt: (1) validate Canvas dimensions match requested size, (2) validate all lines have consistent display width using wcwidth, (3) validate emoji placement doesn't break grid alignment, (4) for AEAF: validate frame count, frame dimensions consistency, and header format, (5) validate output fits within Telegram's 4096-char message limit for text mode. On validation failure, construct a specific error message (e.g., "Line 3 is 22 chars wide, expected 20") and feed it back to the LLM for correction. Maximum 5 retry iterations per generation attempt. | MUST | T2 | - Validator catches width mismatches with specific line numbers<br/>- Validator catches broken emoji alignment<br/>- Validator catches AEAF format errors<br/>- Retry loop fixes issues within 5 iterations >70% of the time<br/>- Telegram char limit enforced<br/>- Each iteration's errors are logged |
| GW-003 | Create `tools/art_assessor.py` that uses vision-capable LLMs to score artwork against the 5-criterion rubric. The assessor: (1) renders the artwork to PNG using the image renderer (GW-005), (2) sends the PNG to a vision model (Gemini Pro or Claude with vision) with the scoring rubric as a structured prompt, (3) parses the returned scores (1-10 per criterion), (4) computes the weighted composite score, (5) stores the assessment in the art repository. The assessor should also extract qualitative feedback (what works, what doesn't) for use in future generation prompts. Must handle vision API failures gracefully with retry. | MUST | T2 | - Assessor returns scores for all 5 criteria<br/>- Composite score computed with correct weights<br/>- Qualitative feedback extracted as structured text<br/>- Scores stored in PostgreSQL art repository<br/>- Vision API failures retry up to 3 times<br/>- Assessment includes the model that judged it |
| GW-004 | Create `tools/art_sandbox.py` adapting PromptLab's sandbox execution model for CypherClaw. Execute LLM-generated Canvas DSL code in a sandboxed subprocess with: AST validation (only allow imports from {textwrap, itertools, math, random, string, wcwidth, json, re}), memory limit (256MB via RLIMIT), 30-second timeout, and the GlyphWeave DSL auto-injected. The sandbox captures stdout as the art output and returns success/failure with error details. This replaces direct `exec()` for all art generation. | MUST | T2 | - Sandbox blocks dangerous imports (os, subprocess, sys)<br/>- Sandbox blocks exec/eval/__import__/open<br/>- Memory limit prevents runaway allocations<br/>- Timeout kills hung generations<br/>- DSL classes available without explicit import in sandboxed code<br/>- Error messages include line numbers from generated code |
| GW-005 | Create `tools/art_renderer.py` that renders GlyphWeave art to PNG images. Use Pillow (PIL) to: (1) render each cell on a fixed grid using a monospace font (JetBrains Mono or similar), (2) render emoji using Noto Color Emoji font or Unicode fallback, (3) support palette-based coloring (foreground/background per cell), (4) produce both thumbnail (400px wide for gallery) and full-size (800px wide for detail view) versions, (5) for AEAF animations, render each frame as a PNG and assemble into an animated GIF. Store rendered images on disk at `/home/user/cypherclaw/gallery/renders/`. | MUST | T3 | - Static art renders to PNG with correct monospace grid<br/>- Emoji render at correct width (2 cells) in the image<br/>- Palette colors applied to foreground/background<br/>- Thumbnails and full-size both generated<br/>- AEAF animations produce animated GIF<br/>- Rendered files stored at correct path with unique filenames |
| GW-006 | Create the PostgreSQL art repository schema and data access layer at `tools/art_repository.py`. Tables: `artworks` (id, created_at, art_type, theme, dimensions, palette, pets_featured, canvas_text, aeaf_text, generated_code, png_path, gif_path, thumbnail_path, composite_score, scores_json, qualitative_feedback, generation_model, generation_effort, generation_temperature, assessment_model, generation_time_ms, assessment_time_ms, retry_count, experiment_id, is_favorite, tags), `experiments` (id, created_at, experiment_name, model_id, effort_level, temperature, art_type, dimensions, theme_category, generation_config_json), `model_art_scores` (id, model_id, effort_level, art_type, avg_composite, avg_medium_use, avg_visual_appeal, avg_expressiveness, avg_creativity, avg_precision, sample_count, last_updated). Use psycopg2 with connection pooling. | MUST | T2 | - All tables created in cypherclaw_observatory PostgreSQL database<br/>- CRUD operations work for artworks, experiments, model_art_scores<br/>- Connection pooling with max 5 connections<br/>- Artwork insert returns generated ID<br/>- Query by model, score range, art_type, date range all work<br/>- model_art_scores auto-updated on new assessment |
| GW-007 | Create `tools/art_experimenter.py` implementing the scientific calibration framework. The experimenter maintains a grid of configurations to test: (model × effort × temperature × art_type × dimensions × theme_category). During the 3-day calibration period, it systematically works through this grid, running each configuration at least 3 times for statistical significance. It tracks: success_rate (valid art produced), avg_composite_score, score_variance, generation_time, retry_count. After calibration, it produces a ranked leaderboard of model configurations and recommends the optimal config for each art_type. The experimenter should also detect when models change (e.g., provider updates) and trigger re-calibration for affected configurations. | MUST | T3 | - Experiment grid covers all available models from model registry<br/>- Each config tested minimum 3 times during calibration<br/>- Statistics computed: mean, variance, success rate per config<br/>- Leaderboard ranked by composite score<br/>- Recommended configs exported as JSON<br/>- Re-calibration triggered when model registry changes<br/>- Progress trackable (X/Y configs tested) |
| GW-008 | Create the gallery web server at `tools/art_gallery/` using FastAPI + HTMX + Jinja2 templates. Pages: (1) Gallery grid — all artworks as thumbnails with composite score overlay, filterable by model, art_type, score range, date, pet, theme; sortable by score, date, recency. (2) Artwork detail — full-size render, text version in code block, AEAF player for animations, generation stats (model, effort, time, retries), assessment scores radar chart, qualitative feedback. (3) Experiment dashboard — calibration progress, model leaderboard table, score distributions per model (box plots), generation time comparison, success rate heatmap (model × art_type). (4) Live canvas — prompt input, model/effort/size/palette selectors, generate button, real-time status, result display with scores. (5) Remix — take existing artwork, modify parameters, regenerate. Serve static files (rendered PNGs) from disk. Run as a systemd service on port 8080, accessible via Tailscale. | MUST | T3 | - Gallery grid loads with thumbnail images and scores<br/>- Filtering by model, art_type, score, date works<br/>- Detail page shows PNG, text, scores, generation stats<br/>- AEAF animations play in browser (JS frame player)<br/>- Experiment dashboard shows calibration progress and leaderboard<br/>- Live canvas generates art on demand and displays result<br/>- Remix modifies parameters and regenerates<br/>- Server runs on port 8080 as systemd service |
| GW-009 | Integrate art generation into the daemon's 30-minute scheduler. Every 30 minutes (offset from health checks): (1) select art parameters — theme based on system state 50% of the time (server load, pet moods, active tasks, time of day) and pure creative exploration 50% of the time, (2) select model configuration — during calibration, pick the next untested config from the experiment grid; after calibration, use the optimal config with 20% exploration of other configs, (3) generate artwork via art engine, (4) assess via art assessor, (5) store in repository, (6) display in Telegram — send text version in code block + rendered PNG as photo, (7) log everything to Observatory. The art display should accompany (not replace) the health check when they coincide. | MUST | T2 | - Art generated every 30 minutes automatically<br/>- Theme selection alternates between reactive and creative<br/>- During calibration: systematic config testing<br/>- After calibration: optimal config with 20% exploration<br/>- Text version sent as Telegram code block<br/>- PNG sent as Telegram photo<br/>- Observatory event logged with all metadata<br/>- Health check and art display coexist when scheduled together |
| GW-010 | Implement pet-scene generation. Every artwork must feature one or more of CypherClaw's Tamagotchi pets. Scene modes: (a) **Artist attribution** — the pet whose model generated the piece is shown creating/presenting it, (b) **State reflection** — pet's current Tamagotchi state (mood, energy, hunger, stage) determines the scene (tired pet napping, happy pet playing, hungry pet searching for food), (c) **Multi-pet interaction** — collaborative scenes with 2+ pets (teaching, playing, competing, exploring together). The scene mode is varied across generations, with equal probability for each mode. Pet portraits from `pet_sprites.py` should be composited into the Canvas using the DSL's `composite()` method. | MUST | T2 | - Each artwork features at least one pet<br/>- Artist attribution mode: generating model's pet shown<br/>- State reflection mode: current Tamagotchi stats drive scene<br/>- Multi-pet interaction mode: 2+ pets in scene<br/>- Modes distributed roughly equally over time<br/>- Pet sprites from pet_sprites.py used via Canvas.composite()<br/>- Pet stage (Egg through Master) reflected in portrait used |
| GW-011 | Implement Tamagotchi-style animations for Telegram. Animated pieces should be short (3-5 frames), loop-friendly, and evoke the feel of a virtual pet game. Frame transitions should show pet movement, expression changes, or environmental shifts. Use the existing AEAF player (`tools/glyphweave/player.py`) for Telegram message-edit playback at 3000ms minimum frame interval. Also render as animated GIF for the gallery. Animation themes: pet idle animations, pet reactions to events (task complete, evolution, feeding), weather/time-of-day cycles, mini-scenes (pet cooking, coding, stargazing). | SHOULD | T2 | - Animations are 3-5 frames long<br/>- Frame interval >= 3000ms (Telegram rate limit)<br/>- AEAF player used for Telegram display<br/>- Animated GIF generated for gallery<br/>- Pet expression/position changes between frames<br/>- At least 5 distinct animation themes implemented<br/>- Animations feel cohesive (smooth transitions, no jarring jumps) |
| GW-012 | Implement model experiment logging with full telemetry. For every generation attempt, log to PostgreSQL: timestamp, model_id, effort_level, temperature, prompt_text (plan phase + generate phase), raw_llm_output, generated_code, sandbox_execution_time_ms, validation_passes (list of pass/fail per check), retry_count, retry_error_messages, final_art_output, assessment_scores, assessment_model, total_pipeline_time_ms, token_count_estimate, cost_estimate. Provide query functions for the experiment dashboard: per-model aggregates, time-series of scores, comparison matrices. | MUST | T2 | - Every generation attempt logged with all fields<br/>- Failed attempts logged too (for success rate calculation)<br/>- Query by model returns aggregate statistics<br/>- Time-series query returns score progression<br/>- Comparison matrix: model × art_type with avg scores<br/>- Logs queryable from gallery dashboard<br/>- Cost estimates computed from model registry pricing |
| GW-013 | Build prompt templates for art generation. Create two sets of prompts: (1) **Plan prompts** — instruct the LLM to describe the artwork layout in natural language before generating code. Include: the GlyphWeave DSL API reference, the scoring rubric, 2-3 canonical examples of good art with their Canvas code, the specific theme/pet/palette parameters, and negative examples showing common failures (width miscounts, emoji misalignment). (2) **Generate prompts** — take the plan output and instruct the LLM to produce executable Canvas/Animation DSL code. Include: the DSL API, the plan text, dimension constraints, a code template skeleton. Store in `tools/art_prompts/`. Use the VoT (Visualization-of-Thought) strategy: have the model sketch a rough grid in the plan phase. | MUST | T2 | - Plan prompt produces coherent layout descriptions<br/>- Plan prompt includes DSL API reference, rubric, examples<br/>- Generate prompt produces executable Canvas code<br/>- VoT strategy: plan includes rough ASCII sketch of layout<br/>- Negative examples included showing common failures<br/>- 2-3 canonical examples with working Canvas code<br/>- Templates parametrized for theme, pet, palette, dimensions |
| GW-014 | Implement the "view rendered" option in Telegram. After sending art as a code block, offer an inline keyboard button "View Rendered" that, when pressed, sends the PNG render of the same artwork as a photo message. For animations, offer both "View Rendered" (static first frame as PNG) and "Play Animation" (triggers AEAF player edit sequence). Also add a "View in Gallery" button that links to the artwork's detail page on the gallery website. | SHOULD | T2 | - Text art sent with inline keyboard buttons<br/>- "View Rendered" sends PNG as photo reply<br/>- "Play Animation" triggers AEAF player for animated pieces<br/>- "View in Gallery" links to gallery detail URL<br/>- Buttons only appear on art messages, not all messages<br/>- Callback query handlers registered in daemon |
| GW-015 | Integrate with the model registry from the model-awareness PRD. The art experimenter (GW-007) should pull available models from `tools/model_registry.py` (being built by the model-awareness pipeline). When the model registry adds or removes models, the experimenter detects the change and queues new calibration runs for the changed models. Art generation calls should use `run_agent()` with the model parameter (REQ-004 from model-awareness PRD) to invoke specific model+effort combinations. Fitness scores from art generation should feed back into the Observatory's per-model tracking (REQ-007, REQ-008). | MUST | T2 | - Art engine reads available models from model_registry<br/>- Model changes detected and trigger re-calibration<br/>- run_agent() used with model parameter for generation<br/>- Art scores recorded in Observatory per-model tracking<br/>- Art-specific fitness scores (composite, per-criterion) tracked separately from code task fitness |
| GW-016 | Install required dependencies on the server: Pillow (PIL) for PNG rendering, a monospace font (JetBrains Mono), Noto Color Emoji font, psycopg2 for PostgreSQL, Jinja2 for templates, python-multipart for file uploads in FastAPI. Ensure FastAPI and uvicorn are available. Create the gallery directory structure: `/home/user/cypherclaw/gallery/renders/`, `/home/user/cypherclaw/gallery/templates/`, `/home/user/cypherclaw/gallery/static/`. | MUST | T1 | - Pillow importable: `python3 -c "from PIL import Image"`<br/>- JetBrains Mono font installed and locatable<br/>- Noto Color Emoji font installed and locatable<br/>- psycopg2 importable<br/>- Gallery directories exist with correct permissions<br/>- FastAPI + uvicorn + Jinja2 installed |
| GW-017 | Create a systemd service for the gallery web server at `/etc/systemd/system/cypherclaw-gallery.service`. The service should: run as user `user`, start after postgresql and cypherclaw services, use the same TMPDIR and environment as the daemon, restart on failure with 10-second delay, bind to port 8080. Add an Nginx reverse proxy config to serve the gallery at a clean URL if Nginx is available. | SHOULD | T1 | - Service file created and enabled<br/>- Gallery starts on boot after postgresql<br/>- Gallery accessible at cypherclaw:8080<br/>- Service restarts automatically on crash<br/>- Logs go to journalctl |
| GW-018 | Add `/art` command to Telegram daemon. Subcommands: `/art` (show latest artwork), `/art generate <prompt>` (generate on-demand with custom prompt, display result), `/art gallery` (link to gallery website), `/art stats` (show model leaderboard — top 5 configs by composite score), `/art calibration` (show calibration progress during 3-day period). On-demand generation via `/art generate` uses the live canvas pipeline and responds with both text and PNG. | SHOULD | T2 | - `/art` shows most recent artwork in chat<br/>- `/art generate <prompt>` creates custom art and displays it<br/>- `/art gallery` sends gallery URL<br/>- `/art stats` shows top model configs with scores<br/>- `/art calibration` shows X/Y configs tested, ETA<br/>- All commands respond within reasonable time (generation may take 30-60s) |
| GW-019 | During the 3-day calibration period, the experimenter should test the following parameter grid systematically. Models: all models from model registry (claude-opus, claude-sonnet, claude-haiku, gpt-5.4, gemini-pro, gemini-flash, llama3.2:3b via Ollama). Effort levels: low, standard, high, xhigh (where supported). Art types: static, animated. Dimensions: 8x8, 12x12, 15x15, 20x15, 20x20. Theme categories: system-state, nature, space, cyberpunk, cozy, abstract, pet-daily-life. The experimenter should prioritize breadth first (one sample per unique config), then depth (repeat best configs for statistical significance). Track wall-clock time so the 30-minute cycle isn't exceeded. | MUST | T2 | - All 7 models tested during calibration<br/>- Multiple effort levels tested per model<br/>- Both static and animated tested<br/>- All 5 dimension sets tested<br/>- All 7 theme categories tested<br/>- Breadth-first strategy: cover all configs before repeating<br/>- Single generation fits within 30-minute cycle<br/>- Progress tracked: configs_tested / total_configs |
| GW-020 | Copy the GlyphWeave foundations research document to the server at `/home/user/cypherclaw/docs/glyphweave-foundations.md`. This document should be included (or summarized) in generation prompts so the LLM understands the art form's history, principles, and constraints. The art engine should reference specific principles from the foundations when constructing prompts — e.g., citing the "Structure = Content" principle from concrete poetry, or the Paul Smith constraint-based creativity lesson. | MUST | T1 | - Foundations document present on server at specified path<br/>- Art prompts reference specific principles from the document<br/>- At least 3 principles cited in generation prompts<br/>- Document accessible to all generation processes |

## Implementation Phases

### Phase 1: Foundation (GW-016, GW-020, GW-004, GW-006)
Install dependencies, copy reference docs, create sandbox, create PostgreSQL schema. No LLM calls yet — pure infrastructure.

### Phase 2: Generation Pipeline (GW-001, GW-002, GW-013, GW-005)
Build the art engine, validator, prompt templates, and PNG renderer. This is the core creation pipeline. Test with manual invocation.

### Phase 3: Assessment & Experimentation (GW-003, GW-007, GW-012)
Add vision-based scoring, the calibration framework, and full telemetry. Begin the 3-day calibration period.

### Phase 4: Integration (GW-009, GW-010, GW-011, GW-015)
Wire into daemon scheduler, pet system, animation system, and model registry. Art starts appearing in Telegram every 30 minutes.

### Phase 5: Gallery & Interaction (GW-008, GW-014, GW-017, GW-018)
Build the web gallery, Telegram buttons, systemd service, and `/art` commands. Full interactive experience.

### Phase 6: Calibration Analysis (GW-019)
Run the full calibration grid, analyze results, produce recommendations. After 3 days, reassess with Anthony.

## Dependency on Model Awareness PRD

This PRD depends on the following requirements from `prd-model-awareness.md`, currently being implemented:

| Model Awareness REQ | Used By | How |
|---------------------|---------|-----|
| REQ-001 (model registry) | GW-007, GW-015 | Art experimenter reads available models from registry |
| REQ-003 (model selector) | GW-009 | Daemon uses selector to pick art generation model |
| REQ-004 (run_agent model param) | GW-001 | Art engine invokes specific models via run_agent() |
| REQ-007 (Observatory model tracking) | GW-012 | Art scores feed into per-model Observatory tracking |
| REQ-008 (fitness scoring) | GW-015 | Art-specific fitness scores complement code task scores |

If model awareness requirements are not yet complete when art studio tasks begin, the art engine should fall back to direct CLI invocation with hardcoded model flags until the registry is available.

## Success Metrics

| Metric | Target (after calibration) |
|--------|---------------------------|
| Art generated per day | 48 pieces (every 30 min) |
| Average composite score | > 6.0 / 10.0 |
| Generation success rate | > 80% (valid art on first or retry) |
| Validation pass rate (first attempt) | > 50% |
| Gallery uptime | > 99% |
| Calibration configs tested (3 days) | > 200 unique configurations |
| Models tested | All 7 available models |
| PNG render quality | Readable at 400px thumbnail |
