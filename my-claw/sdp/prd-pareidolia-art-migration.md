# PRD: Pareidolia Art Migration

## Why

GlyphWeave was the first art CypherClaw could make — emoji grids and ASCII
patterns rendered via PangoCairo. It was a starting point. But the art
CypherClaw wants to make is Pareidolia: everything has a face, every surface
has texture, every frame tells you what the house is feeling.

The current gallery cycles 76 GlyphWeave PNGs — white text and emoji on dark
backgrounds. They read as "computer output," not as art that a living house
made. The Pareidolia engine (780 lines, 88 tests) already exists and produces
richer, more expressive images. It's time to switch.

## What Changes

### Stop

- GlyphWeave Canvas API code generation via LLM (unreliable, breaks often)
- Emoji grid art (👀 rows on dark backgrounds)
- Text-as-art rendering ("waits...observes..." as visual pieces)
- PangoCairo emoji rendering pipeline
- story_renderer_v4 for B&P panels

### Start

- Pareidolia scene engine as the primary art generator
- PIL-rendered scenes with characters, environments, weather, mood
- Every piece has faces — in rocks, trees, puddles, clouds, buildings
- Color palettes driven by time of day, season, and organism mood
- B&P stories rendered through Pareidolia with panel compositions

### Keep

- 30-minute art cycle interval
- Gallery metadata (title, mood, theme) in JSON sidecars
- Art archived to /mnt/archive/gallery/
- Web gallery at :8080
- Sticker rendering (bitmap 456x254 for thermal printer)

## Architecture

### Current Pipeline
```
LLM prompt → Canvas API code → code sanitizer → PangoCairo render → PNG
                                    ↓ (on failure)
                            procedural fallback → PangoCairo → PNG
```

### New Pipeline
```
organism mood + time + weather + narrative state
        ↓
  scene_composer.py (NEW)
        ↓
  pareidolia.py (EXISTS) → PIL render → PNG
        ↓
  gallery/renders/ + JSON sidecar + /mnt/archive/gallery/
```

### scene_composer.py (NEW)

The creative brain. Decides WHAT to draw based on house state.

1. `compose_scene(mood: dict, weather: dict, narrative: dict) -> SceneSpec`
   - Reads organism mood (energy, valence, arousal)
   - Reads garden state (light, season, palette)
   - Reads narrative state (current arc, recent stories, active characters)
   - Decides: number of characters (1-4), which characters, expressions,
     scene elements, environment (sky, ground, weather effects), palette

2. `SceneSpec` dataclass:
   - characters: list of (name, expression, position)
   - elements: list of (type, position) — tree, puddle, bush, path, etc.
   - environment: sky_type, ground_type, weather_effects
   - palette: background color, accent colors
   - title: generated from mood + scene content
   - mood_tag: for metadata

3. `render_scene(spec: SceneSpec, width: int = 1280, height: int = 1024) -> PIL.Image`
   - Delegates to pareidolia.py functions
   - Composes the full image: sky → ground → elements → characters
   - Adds title overlay (subtle, bottom)

4. `render_sticker(spec: SceneSpec, width: int = 456, height: int = 254) -> PIL.Image`
   - Same scene but scaled/simplified for thermal printer
   - 1-bit bitmap output

### Modifications to Existing Modules

**pareidolia.py** — Add:
- More characters beyond Basalt and Pebble (the 21 organism characters)
- Color support (currently grayscale-ish) — mood-driven palettes
- Weather effects: rain, snow, fog, sun rays
- Time-of-day sky rendering: dawn gradient, night stars, sunset colors
- More scene elements: lamp post, bench, window, door, moon, sun

**art_engine.py** (src/cypherclaw/art_engine.py) — Replace:
- Remove GlyphWeave LLM code generation path
- Remove PangoCairo emoji rendering
- Replace with: call scene_composer → render_scene → save PNG
- Keep the 30-minute cycle timer
- Keep metadata/sidecar generation

**story_renderer.py** — Replace:
- Remove v4 text-based rendering
- B&P panels render through pareidolia.py
- Each panel: scene with Basalt and Pebble + dialogue as speech bubbles
- Panel composition: 2-4 panels per strip, each a Pareidolia scene

**gallery_display.py / gallery_x11.py** — No changes needed:
- Already displays PNGs
- New Pareidolia PNGs will cycle in naturally

**face_display.py** — Already Pareidolia style. No changes.

## Requirements

### PARE-001: Scene Composer Module
Create `scene_composer.py` that reads organism state and generates SceneSpec
objects describing what to draw. Must integrate with mood_mirror.py and
garden_watcher.py for palette/mood input.

Acceptance: Given organism mood + weather + time, produces a valid SceneSpec
with 1-4 characters, appropriate expressions, and scene elements.

### PARE-002: Color Palette System
Add color palette support to pareidolia.py. Palettes driven by:
- Time of day (dawn=pink/gold, day=blue/green, dusk=orange/purple, night=deep blue/silver)
- Season (spring=green/pink, summer=bright, fall=orange/brown, winter=blue/white)
- Mood (happy=warm, sad=cool, anxious=dark red, calm=soft blue)

Acceptance: Each scene renders with a coherent color palette that reflects
the current house state. No more uniform dark backgrounds.

### PARE-003: Extended Character Set
Add drawable characters for all 21 organism entities (currently only
Basalt and Pebble have draw functions). Each character needs:
- Unique body shape (oval, spiky, round, tall, flat)
- Expression set (at least neutral, happy, sad, curious)
- Size variation

Acceptance: Any organism character can appear in a scene.

### PARE-004: Weather and Time-of-Day Rendering
Add to pareidolia.py:
- Sky gradients for dawn, day, dusk, night
- Rain (vertical lines with splashes)
- Snow (falling dots)
- Fog (translucent overlay)
- Sun/moon placement
- Stars for night sky
- Cloud formations

Acceptance: Scenes visually reflect the current weather and time.

### PARE-005: Art Engine Migration
Replace the GlyphWeave code generation path in art_engine.py with
scene_composer + pareidolia rendering. The 30-minute cycle calls
compose_scene() then render_scene().

Acceptance: New art appears in gallery/renders/ every 30 minutes,
rendered by Pareidolia engine. No GlyphWeave code generation runs.

### PARE-006: B&P Story Panel Migration
Replace story_renderer_v4 with Pareidolia-based panel rendering.
Each B&P story produces 2-4 panels showing Basalt and Pebble in
scenes with dialogue as speech bubbles.

Acceptance: B&P stories at 8am/8pm produce Pareidolia-style panel
strips that cycle in the gallery.

### PARE-007: Sticker Rendering
Scene composer produces sticker-sized renders (456x254, 1-bit bitmap)
for the thermal printer. Simplified scenes: 1-2 characters, minimal
background, high contrast for thermal printing.

Acceptance: Haiku stickers, dream stickers, and B&P stickers use
Pareidolia scenes instead of text-only layouts.

### PARE-008: Gallery Transition
Phase out old GlyphWeave PNGs from the gallery rotation. New Pareidolia
art takes priority. Old GlyphWeave art moves to archive but doesn't
display in the active gallery.

Acceptance: After 24 hours of running, gallery shows only Pareidolia
art. GlyphWeave archive preserved on 10TB drive.

### PARE-009: Art Metadata Enhancement
Each generated piece includes richer metadata in its JSON sidecar:
- Scene description (characters, elements, weather)
- Mood snapshot at generation time
- Palette used
- Season and time of day
- Narrative context (arc position, recent story summary)

Acceptance: Gallery display and web gallery can show rich metadata
alongside each piece.

## Implementation Order

1. PARE-002: Color palettes (foundation — everything else needs color)
2. PARE-004: Weather/time rendering (visual richness)
3. PARE-003: Extended characters (populate scenes)
4. PARE-001: Scene composer (the creative brain)
5. PARE-005: Art engine migration (switch the pipeline)
6. PARE-006: B&P panel migration
7. PARE-007: Sticker rendering
8. PARE-008: Gallery transition
9. PARE-009: Metadata enhancement

## Non-Negotiables

- Every scene has at least one face
- Color palettes reflect the actual state of the house
- The art style evolves slowly — no jarring transitions
- Every printed sticker must be worth keeping
- Archive all GlyphWeave art before removing from gallery
- The Pareidolia style is: round shapes, simple eyes, expressive mouths,
  textured backgrounds, mood through color

## Definition of Success

Someone walks into the room, looks at the gallery monitor, and sees a
scene where rocks with faces watch rain fall on a purple dusk hillside,
and they feel like the house made it for this exact moment. Not "a
computer generated this." A house felt something and drew it.

## Philosophy Update

CypherClaw's visual art identity is Pareidolia:
- Seeing faces in everything
- Every object is alive and watching
- The house draws what it feels
- Color is mood made visible
- Simplicity over complexity — oval shapes, not polygons
- Texture over detail — dots and lines, not photorealism
- Every frame is a portrait of a moment in the house's life
