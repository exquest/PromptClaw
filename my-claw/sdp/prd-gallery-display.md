# PRD: GlyphWeave Gallery Display — Physical Art Frame for CypherClaw Server

## Overview

Turn the CypherClaw server's physical monitor into a living art gallery. The attached 1280x1024 display (Intel UHD 630, `/dev/fb0`) auto-launches a gallery on boot that showcases GlyphWeave art — both ANSI terminal art on tty1 and full-color framebuffer pixel renders. New pieces from the Art Studio appear automatically as they're created. Rich keyboard controls let Anthony browse, filter, favorite, and trigger new art. An ambient info overlay (togglable) shows pet status, server health, pipeline progress, and piece attribution.

**Depends on:** `prd-glyphweave-art-studio.md` (art generation, gallery database, scoring)

**Reference:** Server hardware — Intel i5-10505, 64GB RAM, framebuffer at 1280x1024x32bpp, tty1 console, Fixed 8x16 font (~160x64 character grid)

## Design Principles

1. **Art first** — the display is a gallery, not a dashboard. Art fills the screen; info is secondary and togglable
2. **Dual rendering** — ANSI terminal art is the default workhorse; framebuffer renders are for showcase pieces and PNG art
3. **Living gallery** — new pieces appear automatically within seconds of creation; no manual refresh needed
4. **Non-intrusive** — must not interfere with SSH sessions, daemon operation, or server stability; zero CPU when idle between transitions
5. **Graceful degradation** — if no monitor detected, service does not start; if framebuffer unavailable, falls back to ANSI-only
6. **Keyboard is optional** — gallery runs fully autonomously; keyboard adds control but isn't required

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  GlyphWeave Gallery Display                      │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐  │
│  │ TTY Renderer  │  │  Framebuffer │  │   Overlay Engine      │  │
│  │ (ANSI art)    │  │  Renderer    │  │                       │  │
│  │               │  │  (pixel art) │  │ - attribution bar     │  │
│  │ - /dev/tty1   │  │              │  │ - pet status strip    │  │
│  │ - escape seqs │  │ - /dev/fb0   │  │ - server health       │  │
│  │ - 160x64 grid │  │ - 1280x1024  │  │ - pipeline progress   │  │
│  │ - AEAF player │  │ - Pillow     │  │ - toggle with 'i'     │  │
│  └──────┬────────┘  └──────┬───────┘  └───────────┬───────────┘  │
│         │                  │                       │              │
│  ┌──────┴──────────────────┴───────────────────────┴───────────┐  │
│  │                    Gallery Display (main loop)               │  │
│  │  - playlist manager (sorted by creation time, newest first) │  │
│  │  - auto-rotate timer (60s static, 3x loop animations)      │  │
│  │  - render dispatch (ANSI vs framebuffer by piece type)      │  │
│  │  - transition effects (clear/fade)                          │  │
│  └──────────────────────────┬──────────────────────────────────┘  │
│                              │                                    │
│  ┌──────────────┐  ┌────────┴───────┐  ┌───────────────────────┐  │
│  │ Art Watcher   │  │  Keybind       │  │  Systemd Service      │  │
│  │               │  │  Handler       │  │                       │  │
│  │ - inotify/    │  │               │  │ - ConditionPath=      │  │
│  │   poll gallery│  │ - raw tty1    │  │   /dev/fb0            │  │
│  │ - new piece   │  │   input       │  │ - After=cypherclaw    │  │
│  │   detection   │  │ - rich ctrl   │  │ - auto-restart        │  │
│  └──────────────┘  └───────────────┘  └───────────────────────┘  │
│                                                                   │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │         Data Sources (read-only)                              │ │
│  │  - Art Repository (PostgreSQL/gallery DB)                     │ │
│  │  - Redis (pet status, server metrics, conversation bus)       │ │
│  │  - Observatory (pipeline progress, agent activity)            │ │
│  └───────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────┘
```

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|----|-------------|----------|------|---------------------|
| GD-001 | Gallery main loop with auto-rotate timer | MUST | T1 | - Displays art pieces sequentially on tty1 - Static pieces show for 60 seconds - Animations loop 3 times then advance - Smooth transitions between pieces (clear screen, center art) |
| GD-002 | TTY ANSI renderer | MUST | T1 | - Opens `/dev/tty1` directly, writes ANSI escape sequences - Clears screen and centers art in 160x64 character grid - Renders GlyphWeave Canvas DSL output with full ANSI color - Handles AEAF animation frames with correct timing - No flickering or partial renders |
| GD-003 | Art watcher for new pieces | MUST | T1 | - Monitors gallery database/directory for new artwork - New pieces appear in playlist within 10 seconds of creation - Inserts new art at front of queue (newest first) - Loads piece metadata (title, model, score, theme, timestamp) |
| GD-004 | Framebuffer pixel renderer | MUST | T1 | - Opens `/dev/fb0`, writes raw RGBA pixels at 1280x1024x32bpp - Renders PNG art pieces scaled to fill screen with correct aspect ratio - Uses Pillow for image loading, scaling, and pixel conversion - Clean screen clear between pieces |
| GD-005 | Render dispatch logic | MUST | T1 | - Automatically selects ANSI renderer for text-based GlyphWeave art - Automatically selects framebuffer renderer for PNG/image art - Manual override with 'a' key to toggle between modes - Falls back to ANSI if framebuffer unavailable |
| GD-006 | Keyboard input handler (raw mode) | MUST | T2 | - Reads raw keypresses from `/dev/tty1` without blocking main loop - Non-blocking input using select/poll - Handles key combos without interfering with display - Gracefully handles no keyboard attached (no errors) |
| GD-007 | Basic keyboard controls | MUST | T2 | - `→` or `n`: next piece - `←` or `p`: previous piece - `Space`: pause/resume auto-rotation - `q`: quit gallery cleanly |
| GD-008 | Advanced keyboard controls | SHOULD | T2 | - `f`: favorite current piece (persisted to DB) - `t`: cycle theme filter (all → water → space → dragon → cute → all) - `/`: enter search mode (type to filter by keyword, Enter to apply, Esc to cancel) - `g`: trigger Art Studio to generate a new piece - `a`: toggle ANSI/framebuffer rendering mode |
| GD-009 | Ambient info overlay — attribution bar | SHOULD | T2 | - Bottom bar showing: piece title, generating model, composite score, creation timestamp - Rendered in ANSI mode as a colored status line at row 64 - Rendered in framebuffer mode as a semi-transparent bar at bottom - Toggled on/off with `i` key |
| GD-010 | Ambient info overlay — pet status | SHOULD | T2 | - Shows all 4 pet icons with stage, mood, XP in a compact strip - Reads live pet data from Redis/tamagotchi state - Updates every 30 seconds when visible - Part of the `i` toggle group |
| GD-011 | Ambient info overlay — server health | SHOULD | T2 | - Corner widget showing CPU load, I/O utilization, uptime - Reads from Redis (I/O watchdog metrics) and /proc - Highlights warnings (yellow >70% I/O, red >85%) - Part of the `i` toggle group |
| GD-012 | Ambient info overlay — pipeline progress | SHOULD | T2 | - Shows active pipeline: completed/total tasks, current agent, running time - Reads from sdp-cli database or observatory - Part of the `i` toggle group |
| GD-013 | Systemd service with monitor detection | MUST | T3 | - Service unit with `ConditionPathExists=/dev/fb0` - `After=cypherclaw.service` dependency - `TTYPath=/dev/tty1`, `StandardInput=tty` - `Restart=on-failure` with 10s delay - Does not start if no monitor/framebuffer detected |
| GD-014 | Playlist management | SHOULD | T2 | - Maintains ordered playlist sorted by creation time (newest first) - Supports filtered views (by theme, favorites only, score threshold) - Remembers position when switching filters - Wraps around at end of playlist |
| GD-015 | Framebuffer transition effects | COULD | T3 | - Fade-to-black between pieces (progressive pixel dimming) - Optional wipe transitions (left-to-right reveal) - Configurable transition duration (default 500ms) |
| GD-016 | Screen blanking prevention | MUST | T1 | - Disables console screen blanking (`setterm -blank 0 -powerdown 0`) - Disables DPMS power saving on tty1 - Resets on service stop to restore defaults |
| GD-017 | AEAF animation in framebuffer mode | COULD | T3 | - Renders AEAF animation frames as pixel art in framebuffer - Converts each Canvas frame to a Pillow image, writes to fb0 - Respects frame timing from AEAF header |
| GD-018 | Gallery statistics display | COULD | T3 | - Keyboard shortcut `s` shows gallery stats overlay - Total pieces, pieces today, top-scored piece, favorite count - Model distribution chart (text-based bar chart) - Dismisses with any key |

## Implementation Phases

**Phase 1: Core Display** (GD-001, GD-002, GD-003, GD-004, GD-005, GD-016)
Build the main loop, both renderers, and art watcher. Get art cycling on the physical monitor. This is the MVP — art appears on screen and auto-rotates.

**Phase 2: Interactivity** (GD-006, GD-007, GD-008, GD-009, GD-010, GD-011, GD-012, GD-014)
Add keyboard controls and ambient info overlays. The gallery becomes interactive and informative.

**Phase 3: Polish & Service** (GD-013, GD-015, GD-017, GD-018)
Systemd auto-launch, transition effects, framebuffer animations, and stats. Production-ready deployment.

## Dependencies

- **Pillow** (`pip install Pillow`) — framebuffer PNG rendering
- **inotify_simple** (`pip install inotify_simple`) — optional, for watching gallery directory (can fall back to polling)
- **GlyphWeave DSL** — already deployed at `tools/glyphweave/`
- **Art Studio gallery DB** — from `prd-glyphweave-art-studio.md`
- **Redis** — pet status, server metrics, conversation bus
- **Observatory** — pipeline progress, agent activity

## Success Metrics

| Metric | Target |
|--------|--------|
| Art visible on monitor within 60s of boot | 100% of boots with monitor attached |
| New art appears on display within 10s of creation | >95% of new pieces |
| No impact on server performance (CPU overhead) | <1% idle, <3% during transitions |
| Gallery runs continuously without crash | >7 days MTBF |
| Keyboard response latency | <200ms |
| Framebuffer render time per piece | <500ms |
