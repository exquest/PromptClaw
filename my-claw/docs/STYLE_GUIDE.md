# CypherClaw Visual Style Guide

> The definitive reference for every visual element CypherClaw sends via Telegram.

---

## 1. Design Principles

### Identity

CypherClaw is a **friendly, technically-capable AI crab orchestrator**. It manages a team of AI agents (Claude, Codex, Gemini) through a Telegram interface, with each agent represented by a Tamagotchi-style pet that grows as it completes tasks.

### Aesthetic: "Cyberpunk Cozy"

The visual language blends **retro terminal** aesthetics with **modern emoji** expressiveness:

- ASCII art lives inside code blocks (monospace) -- the "terminal" layer
- Emoji provide color, personality, and quick scanning in proportional text
- The combination feels like a hacker's dashboard that also gives you a hug

### Personality First

Every message should have personality. Never send plain text when an emoji bullet or a pet portrait would make the interaction warmer. CypherClaw is not a sterile CLI tool -- it is a companion.

### Progressive Visual Evolution

The system grows visually as the user engages:

- **Egg/Baby stage**: Simple sprites, basic narration
- **Teen/Adult stage**: More detailed sprites, richer narration pools
- **Elite/Master stage**: Full portraits, celebratory milestones, dense emoji feedback
- Daily briefs become more insightful as data accumulates
- Completion messages get more celebratory at milestones

---

## 2. Telegram Rendering Constraints

These are hard technical constraints that every template must respect:

| Constraint | Limit |
|---|---|
| Max message length | 4000 characters |
| Code blocks (` ``` `) | Monospace rendering -- use for ALL ASCII art |
| Regular text | Proportional font -- NO alignment-dependent layout |
| Mobile width | Max ~25 chars wide for ASCII art |
| Emoji in code blocks | 2 cells wide -- use sparingly inside art |
| Regular text messages | Under 20 lines preferred |
| Long content | Split into file attachments |
| Box-drawing chars | ONLY inside code blocks |

---

## 3. Color / Emoji Language

Consistent semantic meaning for every emoji used in the system:

### Agent Colors (NEVER mix these)

| Emoji | Meaning |
|---|---|
| `🟣` | Claude -- always purple |
| `🟢` | Codex -- always green |
| `🔵` | Gemini -- always blue |
| `🦀` | CypherClaw / system identity |

### Status Indicators

| Emoji | Meaning |
|---|---|
| `✅` | Success / complete |
| `❌` | Failure / error |
| `⚠️` | Warning / confirmation needed |
| `🔧` | Auto-healing / fix applied |
| `⏳` | Processing / waiting |

### Activity Types

| Emoji | Meaning |
|---|---|
| `📋` | Plan / task list |
| `🔬` | Research |
| `🎨` | Art / image generation |
| `🧠` | Thinking / routing |
| `🔀` | Parallel execution / agent sync |
| `🛠️` | Building / dev task |

### State / Mood

| Emoji | Meaning |
|---|---|
| `💤` | Idle / sleeping |
| `✨` | Special / evolution / success sparkle |
| `📊` | Stats / data / metrics |
| `🐾` | Pets / Tamagotchi system |
| `🌙` | Sleeping state |
| `🍖` | Hunger |
| `⚡` | Energy |

---

## 4. Message Templates

Every message type the bot sends, with exact formatting.

### 4.1 Startup Banner

```
```
 /\_/\
( o.o )  CypherClaw v2
 > ^ <
```
🦀 Systems online | 🧠 Memory loaded
🤖 Agents ready | 📡 Listening...
```

When a CypherClaw pet exists, replace the default crab with the pet's portrait.
When pets are loaded, append a pet lineup section.

### 4.2 Shutdown Banner

```
```
 /\_/\
( -.- )  going offline
 > ^ <
```
💤 Saving state...
🔒 Connections closed
👋 See you soon!
```

### 4.3 Greeting (random from pool)

```
```
 /\_/\
( ^.^ )
 > ^ <
```
🦀 Hey! What are we building?
```

Greeting pool should have 5+ variations. Each combines a face expression with a tagline.

### 4.4 Thinking / Routing

```
```
 /\_/\
( o.o )  thinking...
 > ^ <
```
🧠 analyzing your request...
```

### 4.5 Agent Working (contextual spinner updates)

```
```
{pet_sprite}
```
🟣 ░▒▓██▓▒░
→ contemplating the design...
```

The narration line is contextual -- drawn from `pet_animations.py` based on task category.
The agent icon matches the working agent.

### 4.6 Task Complete

```
```
{pet_sprite}
```
✅ {agent} → {label}
```

No separator lines. Keep it clean and compact.

### 4.7 Task Failed

```
```
{pet_sprite}
```
❌ {agent} failed: {error}
```

### 4.8 Shell Result

```
⚙️ running: {command}
```
{output}
```
```

### 4.9 Status (/status)

```
```
{cypherclaw_pet}
```
🧠 {n} msgs | 📋 {n} tasks | 🕐 {n} sched | 📁 {n} files
```

One compact line of vitals. If pets are loaded, append pet lineup below.

### 4.10 Help (/help)

NO box drawing. Emoji bullets only:

```
🦀 CypherClaw Commands

📋 /status  → system vitals
📊 /stats   → agent performance
🐾 /pets    → your Tamagotchi pets
📊 /brief   → today's daily brief
📋 /retro   → weekly retrospective
🔬 /research → deep research
🎨 /art     → generate ASCII art

⚡ Shortcuts:
ping, status, $ <cmd>
@claude, @codex, @gemini
```

### 4.11 Pet Status (/pets)

Vertical layout, one pet per section:

```
🐾 PET STATUS 🐾

🟣 CLAUDE — Master 🌙
```
{portrait}
```
XP [▓▓▓▓▓▓▓▓▓▓] 1033/MAX
😊 100  🍖 0  ⚡ 99  ✓47 ✗2

🟢 CODEX — Baby 💤
```
{portrait}
```
XP [▓░░░░░░░░░] 12/50
😊 100  🍖 0  ⚡ 100  ✓1 ✗0
```

### 4.12 Research Result (quick)

```
🔬 Quick Research

{answer}

📎 Sources:
• [HIGH] {url1}
• [MED] {url2}
```

### 4.13 Research Result (deep)

```
🔬 Deep Research: {topic}

{summary}

📊 Confidence: 🟢 {n} high | 🟡 {n} medium | 🔴 {n} low
✅ Cross-verified by {agent}
📄 Full report attached
```

### 4.14 Dev Task Progress

```
🛠️ Building: {label}

📋 Planning...
🔨 Implementing...  ← current
✅ Verifying...
```

### 4.15 Daily Brief

```
📊 Daily Brief — {date}

✅ {n} tasks | ❌ {n} failed
🏆 Top: {agent} ({pct}%)
🔧 {n} auto-healed
💰 ~${cost}

🐾 Pet XP: {agent} +{xp}, {agent} +{xp}
```

### 4.16 Evolution Announcement

```
✨🎉 EVOLUTION! 🎉✨

{agent}'s pet evolved!
Stage {n} → {stage_name}

```
{new_portrait}
```

Total XP: {xp}
```

### 4.17 Error / Auto-Healing

```
🔧 Auto-healed: {what}
{action taken}
```

### 4.18 Image Generation

```
🎨 Generating: {prompt}...
```

Then send the image file directly (no text wrapping).

### 4.19 Parallel Dispatch

```
🔀 Parallel: 🟣 claude + 🟢 codex

→ claude: reviewing architecture...
→ codex: implementing changes...
```

### 4.20 Confirmation Prompt

```
⚠️ Confirmation needed:

{description}

Reply ✅ yes or ❌ no
```

### 4.21 Scheduled Task Result

```
🕐 {task_name}
```
{output}
```
```

### 4.22 Plan Preview

```
📜 Plan Preview

1. 🤖 {step_label}
2. ⚙️ {step_label}
3. 🔀 {step_label}
```

Numbered list with step-type icons. No box drawing.

### 4.23 Step Progress

```
🛠️ Step {current}/{total}
{filled_dots}{empty_dots}
→ {label}
```

### 4.24 Pet XP Summary (for /brief and /retro)

```
🐾 Pet Status
  🟣 claude · Master · XP 1033 · 😊100 🌙
  🟢 codex · Baby · XP 12 · 😊100 💤
```

### 4.25 Pet Interaction Scene

```
🔀 Agent Sync
{agent portraits side by side or stacked}
{agent labels}
```

For mobile safety, prefer vertical stacking over horizontal layout.

---

## 5. Evolution Visual Rules

### Stage Progression

| Stage | Name | XP Threshold | Visual Complexity |
|---|---|---|---|
| 0 | Egg | 0 | Simple circle with agent color |
| 1 | Baby | 0 | Basic face in box |
| 2 | Teen | 50 | Face with body elements |
| 3 | Adult | 200 | Full body with accessories |
| 4 | Elite | 500 | Decorated body with sparkles |
| 5 | Master | 1000 | Maximum detail, auras |

### Progressive Enhancements

- **Narration pools expand** at higher stages -- more varied lines
- **Completion messages** become more celebratory at milestones (every 100 XP)
- **Daily briefs** get more insightful as more data accumulates
- **Emoji density** increases subtly with usage (e.g., sparkles on Master-stage completions)

---

## 6. Implementation Notes

### File Responsibilities

| File | Purpose |
|---|---|
| `tools/glyphweave/scenes.py` | All message rendering -- implements every template above |
| `tools/glyphweave/pet_sprites.py` | ASCII portrait data per agent per stage |
| `tools/glyphweave/pet_animations.py` | Narration lines, activity decorations, frame builders |
| `tools/tamagotchi.py` | Pet state management, XP, evolution logic |

### Key Rules for `scenes.py`

1. Every public method returns a `str` ready for `bot.send_message()`
2. All ASCII art is wrapped in triple-backtick code blocks
3. No box-drawing characters (`─│┌┐└┘╔╗╚╝║═`) outside code blocks
4. The help menu uses ONLY emoji bullets, never boxes
5. Status display uses pipe-separated compact format
6. Pet status is ALWAYS vertical (one pet per section), never side-by-side
7. Agent icons are looked up from the canonical `_AGENT_ICONS` dict
8. Every method accepts optional `pet_portrait` or `pets` for evolved visuals

---

## 7. Anti-Patterns (Do NOT Do)

- **No box-drawing in proportional text**: `╔═══╗` renders broken on mobile
- **No alignment-dependent layout in regular text**: columns won't align
- **No wide ASCII art**: keep under 25 chars for mobile code blocks
- **No emoji in ASCII art**: they are 2 cells wide and break alignment
- **No separator lines** (`━━━━━━━━━━`): use whitespace instead
- **No generic spinners**: always use contextual narration from `pet_animations.py`
- **No plain text responses**: every message gets at least one emoji for personality
