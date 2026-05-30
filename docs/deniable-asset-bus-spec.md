# Deniable Asset Bus — Integration Spec v0.1

Status: **draft, ready to implement against**
Owners: CypherClaw side (PromptClaw / Anthony) = *producer*; Deniable game = *requester*
Date: 2026-05-29

## Purpose

The Deniable game needs generated assets — **images, music, voiceover, sfx** — produced
by CypherClaw. This spec defines a **stable, lightweight interface** the Deniable agent can
code against *today*, without knowing anything about how CypherClaw produces the assets.

The contract is a **filesystem artifact exchange**: the requester writes a request file, the
producer writes a deliverable + manifest. Both sides do plain file I/O — no network client,
no daemon API, no auth handshake. This deliberately hides the producer's internals (which may
start as a hand-brokered ssh/rsync step and later become the CypherClaw daemon inbox or the
federation `task_delegate` protocol). **None of those changes affect the requester.**

## The bus directory

A single root directory, agreed by both agents. Set via env var, with a default:

```
DENIABLE_ASSET_BUS   default: ~/deniable-asset-bus
```

Layout:

```
$DENIABLE_ASSET_BUS/
  requests/        # requester writes <request_id>.json here
  deliverables/    # producer writes assets + <request_id>.result.json here
    <request_id>/  # one folder per fulfilled request, holds the asset files
  status/          # optional: producer writes <request_id>.status.json (progress)
```

Both agents are local to the same laptop, so this is a local path for the requester.
**How files cross to/from CypherClaw is the producer's job and out of scope here.**

## Request format

Requester writes `requests/<request_id>.json` (atomic write: write to `*.tmp`, then rename).

```json
{
  "request_id": "8f3c... (UUIDv4, requester-generated, unique)",
  "schema": "deniable-asset-bus/v0.1",
  "created_at": "2026-05-29T18:00:00Z",
  "requester": "deniable",
  "asset_type": "image | music | voiceover | sfx",
  "title": "short human label, e.g. 'main-menu-bg'",
  "format": "png | wav | ogg | mp3",
  "target_path": "assets/ui/main-menu-bg.png   (hint: where it lands in the game repo)",
  "priority": "low | normal | high",
  "acceptance": "free-text acceptance criteria the producer should satisfy",
  "spec": { "...type-specific, see below..." }
}
```

### `spec` by asset_type

**image**
```json
{
  "prompt": "weathered cold-war dossier on a steel desk, dim lamp, noir",
  "negative_prompt": "text, watermark, blurry",
  "width": 768, "height": 512,
  "count": 1,
  "seed": null,
  "style_refs": ["optional/path/to/reference.png"]
}
```

**music**
```json
{
  "scene": "tense stakeout, low pulse",
  "mood": ["tense", "cold", "patient"],
  "duration_seconds": 90,
  "loopable": true,
  "key_hint": "D minor",
  "tempo_hint_bpm": null,
  "reference": "free-text or path",
  "stems": false
}
```

**voiceover**
```json
{
  "script": "exact line(s) to speak",
  "character": "handler",
  "language": "en",
  "direction": "flat, bureaucratic, faint menace"
}
```

**sfx**
```json
{
  "description": "heavy steel door latch, single",
  "duration_seconds": 2,
  "count": 1
}
```

## Response / manifest format

When done (or failed), producer writes `deliverables/<request_id>.result.json` (atomic):

```json
{
  "request_id": "8f3c...",
  "schema": "deniable-asset-bus/v0.1",
  "status": "done | error | partial | deferred",
  "produced_at": "2026-05-29T18:04:12Z",
  "producer": "cypherclaw",
  "assets": [
    {
      "path": "deliverables/8f3c.../main-menu-bg.png",
      "type": "image",
      "bytes": 482113,
      "sha256": "…",
      "meta": { "width": 768, "height": 512, "seed": 12345, "model": "dreamshaper-8" }
    }
  ],
  "notes": "any caveats or substitutions",
  "error": null
}
```

- `path` is relative to `$DENIABLE_ASSET_BUS`.
- `done` = all assets present and acceptable. `partial` = some produced. `error` = none; see `error`.
- `deferred` = accepted but not yet producible (see capability matrix); `notes` explains and the producer will fulfill later under the **same** `request_id`.

## Lifecycle & polling

1. Requester writes `requests/<request_id>.json`.
2. Requester watches for `deliverables/<request_id>.result.json` to appear (poll every few
   seconds, or watch the dir). Optionally read `status/<request_id>.status.json` for progress.
3. On `done`/`partial`, requester copies asset files from `deliverables/<request_id>/` into the
   game repo at `target_path` (or wherever it decides) and verifies `sha256`.
4. **Idempotency:** `request_id` is the key. Re-writing the same request is a no-op for the
   producer if a result already exists. Never reuse an id for a different asset.
5. **Failure:** on `error`, read `error`, fix the spec, and submit a **new** `request_id`.

## Capability matrix (honest, v0.1)

| asset_type | status | notes |
|------------|--------|-------|
| **image**  | supported | DreamShaper 8 (SD 1.5 fp32), txt2img + img2img. PNG. ~512–768px native, upscalable. Strong. |
| **music**  | supported, style-constrained | CypherClaw is a *generative ambient* engine: atmospheric beds, drones, evolving textures rendered to fixed-length WAV/OGG. Tight rhythmic loops / stingers / chiptune / adaptive layers are **not** its strength — confirm per request; producer may return `partial` + `notes`. |
| **sfx**    | experimental | Possible via synthesis; lower confidence. Expect iteration. |
| **voiceover** | **not yet available** | No TTS stack on CypherClaw today. Requests are accepted but return `deferred` until a TTS path (likely external, e.g. a cloud TTS) is wired. Don't block the game on this. |

## What each side implements

- **Deniable (requester):** generate `request_id`, write request JSON atomically, poll for the
  result manifest, verify `sha256`, copy assets into the game. That's the whole integration.
- **CypherClaw (producer):** pick up requests, route image→DreamShaper, music→synthesis render,
  fulfill, write assets + manifest atomically. Transport to/from the box is the producer's concern.

## Producer (CypherClaw side)

The producer is implemented in `promptclaw.asset_bus` and driven through the
`promptclaw asset-bus` CLI. The requester never calls these — they're documented
here so operators on the CypherClaw box know what to run and so future renderers
plug into a known surface.

### CLI surface

```
promptclaw asset-bus validate <request.json>   # lint a request against v0.1
promptclaw asset-bus once                      # one pass over pending requests
promptclaw asset-bus run                       # poll loop (default 5s interval)
promptclaw asset-bus doctor                    # check bus root, renderers, perms
```

`once` and `run` share the same engine: snapshot pending request ids, process
each independently, and write a manifest. `run` adds a poll interval and an
optional bound (`--max-polls`) for smoke runs.

### Processing model

1. Snapshot `requests/*.json` into a list of pending ids.
2. For each id: read the request, dispatch on `asset_type` through the
   capability matrix to the registered renderer, write asset files into
   `deliverables/<request_id>/`, then atomically write
   `deliverables/<request_id>.result.json`.
3. Per-request errors never abort the batch. A renderer exception is converted
   into a v0.1 `error` manifest so the requester still gets a verdict on that
   `request_id`, and the loop continues.
4. Idempotency is enforced by the presence of `<request_id>.result.json` — a
   second pass over the same id is a no-op.

### Renderer registry and capability matrix

- The **capability matrix** (`RendererMatrix`) is the source of truth for which
  `asset_type` values are currently producible. It mirrors the table above and
  is what `doctor` reports against.
- The **renderer registry** maps an `asset_type` to a callable that produces the
  asset files and returns a manifest fragment (`assets`, `status`, `notes`,
  `error`). Today: `image` → DreamShaper 8 render, `music` → ambient synthesis
  render. `sfx` is experimental; `voiceover` returns `deferred`.
- Adding a new renderer is a registry entry plus a matrix update. Nothing in
  the request/manifest schema changes.

### Manifest guarantees

- Always written atomically (`*.tmp` then rename) so the requester never sees a
  partial JSON file.
- `schema` is always `deniable-asset-bus/v0.1`.
- `producer` is always `cypherclaw`.
- `status` is one of `done | partial | error | deferred`; `partial` carries
  whatever assets did land plus a `notes`/`error` explanation.

### Transport

Today the bus root lives on the CypherClaw box; the requester's laptop reaches
it via the producer's chosen path (ssh/rsync, mounted share, or eventual
federation `task_delegate` hop). The CLI does not care which — it operates on
whatever `DENIABLE_ASSET_BUS` resolves to locally. Swapping the transport never
touches this spec.

## Versioning

`schema: "deniable-asset-bus/v0.1"`. Additive changes bump the minor; breaking changes bump the
major and the producer will support both for a transition window. The requester should ignore
unknown fields in the manifest.
