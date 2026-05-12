# CypherClaw Score-Tree Composition Spec

## Purpose

This document turns the songwriting decisions for CypherClaw into an
implementation spec.

The current tracker stack can render and schedule music, but it still composes
too close to playback time and therefore overproduces short, formulaic pieces.
The fix is not to throw away the tracker. The fix is to move composition up one
layer:

- narrative engine creates a concrete `piece brief`
- commission layer chooses form class and composition mode
- recursive composer builds a complete `score tree`
- composition gate rejects underbuilt sketches
- tracker compiler turns the approved tree into live tracker scenes
- performance layer renders the piece with bounded variation

The score tree is the composition truth. The tracker is the performance
surface.

## Design Goals

- produce pieces that are complete before playback
- support real song forms, not only scene rotations
- let pieces run from `0:30` to `10:00+`
- preserve hook-driven songs as the default identity
- allow longer hybrid and through-composed works when the narrative earns them
- keep recurrence and transformation legible
- store reusable structural memory, not only titles and audio traces

## Resolved Artistic Defaults

These are the default priors the system should implement.

### Piece Classes

- `micro`: `0:30-1:15`
- `song`: `2:00-4:30`
- `extended`: `4:00-7:00`
- `suite`: `7:00-12:00+`

### Composition Modes

- `hook_led`: default for most pieces
- `hybrid`: recurring anchor plus stronger sectional transformation
- `through_composed`: rare, mostly for ritual or suite work

### Mode Distribution Targets

- `60-70%` hook-led songs
- `20-30%` hybrids
- `10-20%` through-composed works

### Form Priors

- `70%` recognizable form families
- `20%` hybrid/deformed song forms
- `10%` custom asymmetrical forms

### Section-Function Minimums

- `micro`: at least `2-3` section functions
- `song`: at least `3-5`
- `extended`: at least `4-7`
- `suite`: at least `5-9` or multiple movement blocks

### Return Policy

- `20-30%` literal or near-literal repeats
- `50-60%` moderately transformed returns
- `15-25%` strongly transformed returns

### Hook Policy

- main hook appears in the first `20-40%` of most hook-led pieces
- some pieces foreshadow the hook before the full reveal
- longer pieces may contain instrumental chambers with no explicit hook statement

### Duration Growth

- longer pieces should grow mostly by deepening and transforming existing
  material
- new sections are added only when the narrative needs a new function

### Ending Families

- `hard_cadence`
- `lifted`
- `afterglow`
- `fade`
- `abrupt_cut`
- `dissolve`
- `loop_exit`
- `reprise_coda`

Endings must be chosen before performance begins.

## Target Runtime Pipeline

```text
piece_commission
  -> piece_brief
  -> form_grammar
  -> score_tree
  -> recursive_composer
  -> composition_gate
  -> tracker_compiler
  -> tracker runtime / performance layer
  -> ear metrics / critique
  -> repertoire score-tree memory
```

This replaces the current direct path:

```text
mood -> score_from_mood() -> tracker scenes -> playback
```

with:

```text
narrative + cadence + repertoire + time-of-day
  -> commissioned complete piece
  -> approved score tree
  -> compiled tracker song
  -> bounded live rendering
```

## Existing Seams To Preserve

These existing modules remain useful and should not be replaced blindly.

- `duet_composer.py`
  - remains the top-level live conductor
  - should stop inventing whole pieces ad hoc inside `tracker_solo_song()`
- `generative_scores.py`
  - remains useful for cell, phrase, and local note-shape generation
  - should be demoted from whole-song author to phrase/material supplier
- `music_tracker.py`
  - remains the tracker scene builder and lane quantizer
- `music_tracker_runtime.py`
  - remains the timing owner during playback
- `repertoire_memory.py`
  - remains long-term song memory, but must expand to store structural memory
- `hook_engine.py`
  - remains the hook/title/text engine and should become one of the seed-cell
    generators
- `harmonic_planner.py`, `reharmonizer.py`, `arrangement_engine.py`,
  `prosody_engine.py`, `ear_engine.py`
  - remain supporting systems used by the new composer

## New Modules And Contracts

### 1. `piece_commission.py`

Purpose:
- decide what kind of piece CypherClaw is about to write before composition
  begins

Inputs:
- narrative pressure from the narrative engine
- cadence state
- day phase / weekly phase
- attention score
- repertoire balance and recent-form fatigue
- room state / occupancy state

Primary types:

```python
@dataclass(frozen=True)
class PieceCommission:
    form_class: Literal["micro", "song", "extended", "suite"]
    composition_mode: Literal["hook_led", "hybrid", "through_composed"]
    duration_target_s: float
    sonic_world_count: int
    hook_pressure: float
    narrative_scale: Literal["single_image", "scene", "journey", "ritual"]
    ending_family: str
    groove_identity: str
    reason_tags: tuple[str, ...]
```

Rules:
- pick one explicit form class
- pick one explicit composition mode
- choose duration target before section planning starts
- bias by time of day, but allow narrative overrides

Tests:
- form class distribution by hour and cadence state
- fatigue avoidance after repeated recent form choices
- override behavior when narrative pressure is unusually high

### 2. `piece_brief.py`

Purpose:
- formal narrative-to-music handoff

Inputs:
- narrative engine state
- `WorldModel`
- sensory journal / presence context
- repertoire recall hints

Primary types:

```python
@dataclass(frozen=True)
class PieceBrief:
    image_field: tuple[str, ...]
    dramatic_premise: str
    conflict: str
    desired_payoff: str
    residue: str
    ending_feeling: str
    motion_character: str
    hook_pressure: float
    through_composed_pressure: float
    section_beats: tuple[str, ...]
    narrative_scale: str
```

Rules:
- the brief must be concrete enough to write from
- it should describe dramatic beats, not bar counts or chord names
- it should be storable alongside the final score tree

Tests:
- missing narrative fields degrade to valid defaults
- output always includes a section-beat skeleton
- brief text is concrete rather than only scalar metadata

### 3. `form_grammar.py`

Purpose:
- define section-function grammar, form families, ending families, and section
  duration priors

Primary types:

```python
SectionFunction = Literal[
    "invocation",
    "statement",
    "lift",
    "arrival",
    "refrain",
    "turn",
    "development",
    "breakdown",
    "instrumental_response",
    "recap",
    "coda",
    "residue",
]

@dataclass(frozen=True)
class FormPlan:
    form_family: str
    form_class: str
    composition_mode: str
    section_functions: tuple[SectionFunction, ...]
    section_duration_budgets_s: tuple[tuple[float, float], ...]
    return_plan: tuple[str, ...]
    ending_family: str
```

Responsibilities:
- choose recognizable form families by default
- deform templates through section-function grammar rather than inventing
  arbitrary shapes every time
- enforce minimum functional complexity for each form class
- attach elastic duration budgets to each section

Tests:
- generated plans satisfy the minimum functional complexity for each class
- `hook_led` plans expose earlier arrival functions than `through_composed`
  plans
- ending family is always present

### 4. `score_tree.py`

Purpose:
- define the canonical composition object stored before playback

Primary types:

```python
@dataclass
class MotifNode:
    motif_id: str
    hook_type: str
    contour: tuple[int, ...]
    rhythm_cell: tuple[float, ...]
    anchor_degrees: tuple[int, ...]
    answer_degrees: tuple[int, ...]
    text_hook: str

@dataclass
class PhraseNode:
    phrase_id: str
    function: str
    motif_refs: tuple[str, ...]
    target_duration_s: float
    transform_ops: tuple[str, ...]

@dataclass
class SectionNode:
    section_id: str
    function: str
    target_duration_s: float
    phrases: list[PhraseNode]
    harmony_role: str
    groove_state: str
    return_from: str | None = None

@dataclass
class ScoreTree:
    piece_id: str
    title: str
    commission: PieceCommission
    brief: PieceBrief
    form: FormPlan
    motifs: list[MotifNode]
    sections: list[SectionNode]
    harmonic_plan: dict[str, object]
    arrangement_plan: dict[str, object]
    ending_family: str
    narrative_map: dict[str, str]
    metadata: dict[str, str]
```

Rules:
- a score tree is complete enough to survive process restart
- the whole-piece architecture exists before playback begins
- the score tree is what repertoire memory stores and transforms later

Tests:
- serialization round-trip for complete score trees
- every section references valid motif or return sources
- total planned duration matches the commission budget within tolerance

### 5. `recursive_composer.py`

Purpose:
- build a score tree recursively from commission + brief + grammar

Responsibilities:
- create seed cells first
- map seed cells into phrase families
- map phrase families into section bodies
- map sections into a complete piece
- allow one controlled mode reclassification if the material strongly resists
  the initial plan

Composition order:

```text
seed cell
  -> phrase family
  -> section body
  -> piece architecture
  -> transitions
  -> arrangement/detail pass
```

Rules:
- motif/hook-first by default
- harmony-first only when harmonic color is the actual driver
- groove identity chosen early, groove realization chosen later
- longer pieces deepen existing material before adding new sections

Integration points:
- uses `hook_engine.py` for title/hook families
- uses `harmonic_planner.py` and `reharmonizer.py` for harmonic trajectories
- uses `generative_scores.py` for local phrase-note generation
- uses `arrangement_engine.py` for section-level orchestration plans

Tests:
- hook-led pieces contain a real recurring anchor
- through-composed pieces can still satisfy structural richness without chorus
  repetition
- transformed returns differ materially from the original section

### 6. `composition_gate.py`

Purpose:
- refuse to perform incomplete pieces

Primary type:

```python
@dataclass(frozen=True)
class GateReport:
    approved: bool
    failures: tuple[str, ...]
    warnings: tuple[str, ...]
    metrics: Mapping[str, float]
```

Required checks:
- duration target satisfied
- minimum functional complexity satisfied
- deliberate ending present
- recurrence plus transformation present
- narrative map contains opening, turn, payoff, and residue equivalents
- arrangement contrast and density motion exceed a minimum threshold

Rules:
- micro pieces may be short, but still must be complete
- intentional fragment/interlude forms must be explicitly flagged, not inferred

Tests:
- rejects underbuilt sketches
- accepts short but complete micro pieces
- rejects pieces with no transformed returns where transformation is expected

### 7. `tracker_compiler.py`

Purpose:
- compile approved score trees into tracker material

Responsibilities:
- convert sections into tracker scenes
- preserve section functions and return relationships in scene metadata
- compile motif recall, answer, and variation plans into lane material
- attach arrangement automation and master-bus scene intents

Integration points:
- calls `build_korsakov_tracker_song()` or its replacement helper inside
  `music_tracker.py`
- should preserve section metadata needed by:
  - `music_tracker_runtime.py`
  - `sample_dsp_activity.py`
  - `face_display.py`
  - `master_bus.py`

Rules:
- tracker scenes are execution artifacts, not the composition authority
- section boundaries should usually stay legible
- transition weaving happens after section bodies exist

Tests:
- scene count and section ordering match the source score tree
- section metadata survives compilation
- compiled pieces expose valid runtime durations for the commissioned form class

### 8. `repertoire_memory.py` extension

Purpose:
- store score trees as structural memory

New responsibilities:
- store `score_tree` or `score_tree_ref`
- store form class, composition mode, ending family, narrative beat mapping,
  and transformation map
- support transformation-oriented recall:
  - sequel
  - reprise
  - bridge expansion
  - harmonic re-lighting

Rules:
- surface memory and structural memory are both required
- most new pieces should be mostly new
- a minority should deliberately transform earlier work

Tests:
- round-trip storage of structural memory
- recall bias can pull a prior score-tree shape without exact self-copying

### 9. `duet_composer.py` rewrite seam

Purpose:
- become queue owner and live conductor, not the whole-song inventor

Target flow inside `tracker_solo_song()`:

```text
if no ready piece:
    compose next piece in background

active_piece = dequeue approved score tree
tracker_song = compile active_piece
schedule tracker_song
store critique and repertoire memory
compose next piece while active_piece performs
```

Rules:
- maintain one active piece and one next piece
- optional third slot is a distant sketch only
- performance may vary the living surface, not the macroform

Tests:
- queue always preserves one committed active piece
- piece handoff does not produce empty air or half-composed playback

## Data Persistence

### New files

- `/home/user/cypherclaw-data/state/piece_queue.json`
- `/home/user/cypherclaw-data/state/score_tree_memory.json`
- `/tmp/current_score_tree.json`

### Repertoire additions

Each stored piece should include:

- `piece_id`
- `title`
- `form_class`
- `composition_mode`
- `duration_s`
- `section_function_sequence`
- `motif_ids`
- `ending_family`
- `narrative_beats`
- `audio_render_path`
- `ear_metrics`
- `gate_report`

## Implementation Phases

### Phase ST1: Narrative And Commission

Files:
- `piece_commission.py`
- `piece_brief.py`
- `duet_composer.py`
- tests for commission and brief generation

Goal:
- stop going directly from mood to score

### Phase ST2: Form Grammar And Score Tree

Files:
- `form_grammar.py`
- `score_tree.py`
- `recursive_composer.py`
- tests for form richness and score-tree serialization

Goal:
- create a complete composition object before tracker compilation

### Phase ST3: Composition Gate

Files:
- `composition_gate.py`
- `recursive_composer.py`
- tests for approved vs rejected pieces

Goal:
- reject underbuilt pieces before playback

### Phase ST4: Tracker Compilation

Files:
- `tracker_compiler.py`
- `music_tracker.py`
- `music_tracker_runtime.py`
- `duet_composer.py`

Goal:
- make the tracker a renderer of approved pieces

### Phase ST5: Repertoire Score Trees

Files:
- `repertoire_memory.py`
- `continuous_learner.py`
- tests for score-tree recall and transformation

Goal:
- give CypherClaw structural memory

### Phase ST6: Live Queue And Performance Windows

Files:
- `duet_composer.py`
- optional `piece_queue.py`
- tests for active/next/sketch queue discipline

Goal:
- background composition with committed playback

## Acceptance Criteria

CypherClaw should be considered successful on this spec when:

- it can generate valid `micro`, `song`, `extended`, and `suite` score trees
- most pieces are no longer a single short generic form
- the average completed `song` form exceeds the current short-form plateau
- later sections answer or transform earlier sections instead of merely
  rotating scenes
- repertoire memory can explicitly recall a past form or motif structure
- the tracker can render a committed long-form piece without becoming the
  composing authority again

## Immediate First Build

The first implementation pass should be:

1. `piece_brief.py`
2. `piece_commission.py`
3. `form_grammar.py`
4. `score_tree.py`
5. thin `recursive_composer.py` that builds one valid `song`-class piece
6. `composition_gate.py`
7. minimal `tracker_compiler.py` bridge into the existing tracker

That gets CypherClaw out of mood-to-score improvisation and into authored
piece-making as quickly as possible.
