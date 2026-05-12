# PRD: CypherClaw Web Platform — Mission Control

## Overview

Build a full-featured web platform for CypherClaw accessible via Tailscale VPN, replacing Telegram as the primary interaction interface. The platform provides a NASA-style mission control dashboard, IDE-like chat with live workspace, animated virtual pet room, integrated art gallery, and real-time pipeline monitoring. Telegram remains as a notification-only channel for alerts and heartbeats.

**Stack:** FastAPI (Python backend) + Vue.js 3 (SPA frontend) + WebSockets (real-time updates)
**Access:** Tailscale-only via Tailscale auth headers (no login flow)
**Mobile:** PWA — installable, push notifications, responsive mission control

**Depends on:** `prd-home-resilience.md` (durable services and reboot-safe state), `prd-restructure.md` (stable package layout), `prd-agent-runtime-substrate.md` (real-time execution stream), `prd-context-engine.md` (session briefs and compacted context), `prd-verification-system.md` (safe action routing), `prd-model-awareness.md` (provider/model telemetry), `prd-glyphweave-art-studio.md` (gallery absorbed into platform), `prd-pet-system-v2.md` (pet data for virtual room), `prd-server-optimization.md` (status dashboard data), `prd-local-llm-integration.md` (local model status)

## Execution Role

This is a late-stage surface, not an early foundation.

The web platform becomes dramatically easier once the home is durable, the runtime is streamable, and the context layer can produce clean handoffs and session summaries. Schedule the web surface after the execution spine and continuity layers rather than using it to paper over instability underneath.

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                     CypherClaw Web Platform                        │
│                                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────────┐│
│  │  Vue.js SPA  │  │  FastAPI     │  │  WebSocket Hub            ││
│  │              │  │  Backend     │  │                           ││
│  │ - Mission    │  │ - REST API   │  │ - Chat stream             ││
│  │   Control    │◄─┤ - Auth       │◄─┤ - Agent output stream     ││
│  │ - Chat/IDE   │  │ - File serve │  │ - Server vitals stream    ││
│  │ - Pet Room   │  │ - Pet API    │  │ - Pipeline progress       ││
│  │ - Gallery    │  │ - Gallery API│  │ - Pet state changes       ││
│  │ - Pipeline   │  │ - Pipeline   │  │ - Art generation events   ││
│  │              │  │   API        │  │                           ││
│  └──────────────┘  └──────┬───────┘  └───────────┬───────────────┘│
│                           │                       │                │
│  ┌────────────────────────┴───────────────────────┴───────────────┐│
│  │                    Integration Layer                           ││
│  │  - CypherClaw Daemon (agent dispatch, routing)                ││
│  │  - Observatory (event store, analytics)                       ││
│  │  - Pet System (Tamagotchi state, class XP)                    ││
│  │  - sdp-cli (pipeline status, task queue)                      ││
│  │  - Redis (metrics cache, session state)                       ││
│  │  - PostgreSQL (persistent data)                               ││
│  │  - I/O Watchdog (server health)                               ││
│  └────────────────────────────────────────────────────────────────┘│
│                                                                    │
│  Nginx reverse proxy → :443 (Tailscale cert) or :80               │
│  Tailscale auth headers → identity                                 │
└─────────────────────────────────────────────────────────────────────┘
```

## Requirements

| ID | Description | Priority | Tier | Acceptance Criteria |
|---|---|---|---|---|
| WEB-001 | Set up the FastAPI backend at `tools/web/backend/`. Serve Vue.js SPA as static files. WebSocket endpoint at `/ws` for real-time updates. REST API at `/api/`. Use uvicorn with auto-reload in dev, gunicorn in production. Create systemd service `cypherclaw-web.service` on port 3000. Nginx proxies from port 80/443 to 3000. | MUST | T2 | - FastAPI server starts and serves SPA<br/>- WebSocket connects at /ws<br/>- REST API responds at /api/health<br/>- systemd service created and enabled<br/>- Nginx proxy configured<br/>- Accessible via Tailscale at cypherclaw.tail*.ts.net |
| WEB-002 | Implement Tailscale identity authentication. Read Tailscale auth headers (`Tailscale-User-Login`, `Tailscale-User-Name`) from Nginx proxy to identify the user. No login page needed — if the header is present, the user is authenticated. Store the identity in the WebSocket session. Reject connections without Tailscale headers (direct port access bypass). | MUST | T1 | - Tailscale headers read and parsed<br/>- User identity available in all API endpoints<br/>- WebSocket sessions carry identity<br/>- Direct port access without headers returns 403<br/>- Works on all Tailscale devices |
| WEB-003 | Build the Vue.js 3 SPA scaffold at `tools/web/frontend/`. Use Vite for build tooling. Component library: use a lightweight UI kit (PrimeVue or Naive UI) for consistent styling. Dark theme matching the "cyberpunk cozy" aesthetic — dark background, neon accents (purple for Claude, green for Codex, blue for Gemini, coral for CypherClaw). WebSocket client with auto-reconnect. Vue Router for navigation. Pinia for state management. | MUST | T2 | - Vue 3 + Vite project scaffolded<br/>- Dark cyberpunk theme implemented<br/>- WebSocket client connects with auto-reconnect<br/>- Router navigates between views<br/>- Pinia stores for chat, pets, pipeline, vitals<br/>- Builds to static files served by FastAPI |
| WEB-004 | Build the Mission Control home page. Multi-panel layout showing simultaneously: (a) Server vitals — CPU, RAM, I/O, load as live gauges/sparklines updated via WebSocket every 5s, (b) Pipeline progress — task count, current task, ETA, progress bar, (c) Pet cards — all 4 pets with class, level, stats, current state, (d) Recent activity — last 10 events from Observatory as a live feed, (e) Active agents — which agents are running, what they're doing, elapsed time, (f) Quick actions — feed all pets, run health check, trigger art generation. All panels draggable/resizable for customization. | MUST | T3 | - All 6 panels render with live data<br/>- WebSocket updates vitals every 5s<br/>- Pipeline progress reflects real sdp-cli status<br/>- Pet cards show current state from pet system<br/>- Events stream in real-time<br/>- Quick actions trigger daemon commands<br/>- Panels are draggable/resizable<br/>- Layout persists in localStorage |
| WEB-005 | Build the IDE-like chat interface. Split pane: left side is chat with CypherClaw (message input, history, markdown rendering, code blocks with syntax highlighting, inline images), right side is live workspace showing: active agent output streaming in real-time as the agent generates it, file tree of workspace artifacts, git diff viewer showing changes as agents make them. Chat messages route through the same daemon routing system. Agent output streams via WebSocket as it generates (not after completion). | MUST | T3 | - Chat sends messages through daemon routing<br/>- Agent output streams token-by-token via WebSocket<br/>- Code blocks render with syntax highlighting (Shiki or Prism)<br/>- Markdown renders correctly (marked or markdown-it)<br/>- File tree shows workspace artifacts<br/>- Git diff viewer shows agent changes<br/>- Split pane resizable<br/>- Chat history persists across sessions |
| WEB-006 | Build the virtual pet room. A persistent animated scene where all 4 pets exist together. Pets are rendered using GlyphWeave ASCII art in a monospace canvas. Behaviors: (a) idle — pets wander, blink, shift position, (b) working — pet shows thinking animation when its agent is active, (c) success — celebration sparkles on task completion, (d) interaction — pets interact with each other based on sociability trait, (e) time-of-day — room lighting changes (dawn/day/dusk/night), (f) server state — room reflects server health (storm clouds when I/O high, sunshine when healthy). Click a pet to feed/play/inspect. Pet class accessories visible. Use requestAnimationFrame for smooth animation at 10-15 FPS. | SHOULD | T3 | - Pet room renders all 4 pets as ASCII art<br/>- Pets animate (idle, working, success states)<br/>- Click interaction (feed/play/inspect popup)<br/>- Time-of-day lighting changes<br/>- Server state visual indicators<br/>- Smooth animation at 10+ FPS<br/>- Pet class accessories visible<br/>- Room state persists via WebSocket |
| WEB-007 | Build the integrated art gallery. Absorb the GlyphWeave gallery (from GW-008) into the web platform. Pages: (a) Gallery grid — artwork thumbnails with scores, filterable/sortable, (b) Artwork detail — full render, text version, AEAF animation player, generation stats, assessment scores, (c) Live canvas — generate art on demand with model/parameter selection, (d) Remix — modify parameters and regenerate from existing piece, (e) Experiment dashboard — model leaderboard, score distributions, calibration progress. All data from PostgreSQL art repository. | SHOULD | T3 | - Gallery grid loads artwork thumbnails<br/>- Detail view shows full render + stats<br/>- AEAF animations play in browser<br/>- Live canvas generates on demand<br/>- Remix works from existing pieces<br/>- Experiment dashboard shows calibration data<br/>- Filters and sorting work |
| WEB-008 | Build the pipeline monitor. Real-time view of sdp-cli pipeline: (a) Task queue — all tasks with status icons, expandable to show description and acceptance criteria, (b) Current task detail — which agent is leading, which is verifying, elapsed time, live output stream, (c) Task history — completed tasks with verdicts, duration, agents used, (d) Verification reports — view verify.md files inline, (e) Git log — recent commits from the pipeline with diffs. Data from sdp-cli SQLite DB and git log. | MUST | T2 | - Task queue renders all tasks with status<br/>- Current task shows live agent output<br/>- Completed tasks show verdicts<br/>- Verification reports viewable inline<br/>- Git log with expandable diffs<br/>- Updates via WebSocket when tasks complete |
| WEB-009 | Implement the WebSocket hub. Central event bus that broadcasts to all connected clients: (a) `vitals` — server metrics every 5s from I/O watchdog/Redis, (b) `chat` — new messages and agent responses, (c) `agent` — agent start/stop/output stream events, (d) `pipeline` — task status changes, (e) `pet` — state changes, XP gains, level-ups, (f) `art` — new artwork generated, (g) `alert` — warnings, I/O guard triggers, errors. Clients subscribe to channels. Server-side fan-out. Handle reconnection gracefully with missed-event replay from Redis. | MUST | T2 | - WebSocket hub broadcasts 7 event types<br/>- Clients receive events in real-time<br/>- Reconnection replays missed events from Redis<br/>- Multiple simultaneous clients supported<br/>- Events logged with timestamps<br/>- Backpressure handling for slow clients |
| WEB-010 | Build the REST API layer. Endpoints: `GET /api/health` (server status), `GET /api/vitals` (current metrics), `GET /api/pets` (all pets), `GET /api/pets/:name` (pet detail), `POST /api/pets/:name/feed` (feed), `POST /api/pets/:name/play` (play), `GET /api/pipeline/status` (sdp-cli status), `GET /api/pipeline/tasks` (task list), `GET /api/chat/history` (recent messages), `POST /api/chat/send` (send message), `GET /api/gallery` (artwork list), `GET /api/gallery/:id` (artwork detail), `POST /api/gallery/generate` (generate art), `GET /api/events` (Observatory events). All endpoints return JSON. | MUST | T2 | - All endpoints respond with correct JSON<br/>- Pet feed/play actually modify pet state<br/>- Chat send routes through daemon<br/>- Gallery endpoints query PostgreSQL<br/>- Pipeline status queries sdp-cli<br/>- Authentication required on all endpoints |
| WEB-011 | Implement PWA support. Add a web manifest (`manifest.json`) with CypherClaw icon, theme color (dark), display mode (standalone). Add a service worker for: offline caching of static assets, background sync for chat messages sent while offline, push notification registration. Push notifications for: I/O guard alerts, task completions, pet evolution events, art generation complete. Use Web Push API with VAPID keys. | SHOULD | T2 | - Manifest allows "Add to Home Screen" on mobile<br/>- App opens in standalone mode (no browser chrome)<br/>- Static assets cached for offline access<br/>- Push notifications delivered for key events<br/>- Works on iOS Safari and Android Chrome |
| WEB-012 | Make the frontend fully responsive. Mission control on mobile: panels stack vertically, swipeable between sections (vitals → chat → pets → gallery). Bottom navigation bar with 5 tabs: Home (mission control), Chat, Pets, Gallery, Pipeline. Touch-friendly interaction targets (44px minimum). Chat input with mobile keyboard handling. Pet room simplified to single-pet view on small screens. | MUST | T2 | - Usable on 375px wide screens (iPhone SE)<br/>- Bottom nav with 5 tabs<br/>- Swipeable panels on mission control<br/>- Chat works with mobile keyboard<br/>- Pet room adapts to screen size<br/>- No horizontal scrolling |
| WEB-013 | Implement real-time agent output streaming. When an agent (Claude/Codex/Gemini) is working, stream its stdout token-by-token to the WebSocket. Modify the daemon's `run_agent()` to read stdout line-by-line (or chunk-by-chunk) and broadcast each chunk via the WebSocket hub. The chat UI and pipeline monitor both consume this stream. Include agent name, task label, and elapsed time with each chunk. | MUST | T2 | - Agent stdout streams to WebSocket in real-time<br/>- Chat UI displays streaming output<br/>- Pipeline monitor displays streaming output<br/>- Agent name and elapsed time shown<br/>- Stream ends cleanly on agent completion/failure<br/>- Multiple clients receive the same stream |
| WEB-014 | Implement file browser and git diff viewer for the IDE workspace pane. File tree: list files in `tools/workspace/` with click-to-view. Git diff: show `git diff` output for uncommitted changes and `git show` for recent commits, rendered with diff syntax highlighting (red/green). Auto-refresh when agent makes changes (detected via WebSocket agent events). | SHOULD | T2 | - File tree lists workspace artifacts<br/>- Click opens file content in viewer<br/>- Git diff renders with syntax highlighting<br/>- Auto-refreshes on agent changes<br/>- Recent commits expandable with diffs |
| WEB-015 | Configure Nginx as reverse proxy with Tailscale. Set up Nginx to: proxy `/` to FastAPI on :3000, proxy `/ws` to WebSocket on :3000, add Tailscale identity headers (`Tailscale-User-Login`), serve HTTPS with Tailscale MagicDNS cert (auto-provisioned), or HTTP if cert not available. Block non-Tailscale access. Enable gzip compression for static assets. | MUST | T1 | - Nginx proxies to FastAPI<br/>- WebSocket proxied correctly (upgrade headers)<br/>- Tailscale headers added<br/>- HTTPS with Tailscale cert or HTTP fallback<br/>- Non-Tailscale IPs blocked<br/>- Gzip enabled |
| WEB-016 | Integrate with existing daemon for chat routing. The web platform's chat shares the same routing pipeline as Telegram. Messages sent via `/api/chat/send` are injected into the daemon's `route_message()` → `execute_steps()` flow. Responses are broadcast via WebSocket instead of (or in addition to) Telegram. The daemon needs a new output mode: when a web client is connected, send responses to WebSocket; when no web client, send to Telegram. Both can be active simultaneously. | MUST | T3 | - Web chat messages route through daemon<br/>- Agent responses appear in web chat via WebSocket<br/>- Telegram still receives responses when web is disconnected<br/>- Both channels active simultaneously<br/>- No duplicate processing of messages |
| WEB-017 | Build the server vitals visualization. Real-time gauges and charts: (a) CPU load — gauge (0-100%) + 10-min sparkline, (b) RAM usage — gauge + sparkline, (c) Disk I/O — gauge with color zones (green/yellow/red) + sparkline, (d) Network — bytes in/out sparkline, (e) Temperature — if available, (f) Agent count — live counter, (g) Uptime — human-readable. Data from Redis metrics (I/O watchdog stores every 30s). Use a lightweight chart library (Chart.js or uPlot). | MUST | T2 | - All vitals render as gauges + sparklines<br/>- I/O gauge shows color zones matching guard thresholds<br/>- Data from Redis, updated every 5s via WebSocket<br/>- 10-minute history in sparklines<br/>- Renders smoothly without jank |

## Design Guidelines

### Cyberpunk Cozy Aesthetic
- **Background:** Dark (#0a0a0f) with subtle grid pattern
- **Accents:** Neon purple (#a855f7) for Claude, green (#22c55e) for Codex, blue (#3b82f6) for Gemini, coral (#f97316) for CypherClaw
- **Text:** Light gray (#e2e8f0) on dark, monospace for code/data
- **Cards:** Semi-transparent dark (#1a1a2e) with subtle border glow matching agent color
- **Animations:** Subtle glow pulses, smooth transitions, no jarring movements
- **Typography:** Inter for UI, JetBrains Mono for code/data/ASCII art

### Pet Room Visual Style
- Monospace ASCII canvas rendered in a `<pre>` element or canvas
- Pet sprites from `pet_sprites.py` rendered at 2x scale
- Background changes with time: dark blue (night), amber (dawn), white (day), orange (dusk)
- Particle effects for events (sparkles on level-up, rain when server stressed)

## Implementation Notes

- FastAPI backend shares Python modules with daemon (import Observatory, PetManager, etc.)
- Vue frontend built with `vite build`, output to `tools/web/frontend/dist/`, served by FastAPI as static files
- Node.js required on server for Vue build tooling — install via nvm
- WebSocket messages use JSON with `{type: string, data: object, timestamp: number}` format
- Redis pub/sub for daemon → web server event forwarding (daemon publishes, web server subscribes and fans out to WebSocket clients)

## Success Metrics

| Metric | Target |
|--------|--------|
| Page load time | <2s on Tailscale |
| WebSocket latency | <100ms for event delivery |
| Agent stream delay | <500ms from agent stdout to browser |
| Mobile usability | Fully functional on iPhone SE width |
| Concurrent clients | Support 5+ simultaneous connections |
| PWA install | Works on iOS and Android |
| Uptime | >99% (systemd auto-restart) |
