# PromptClaw PRD Authoring Rules for SDP

Use this guide when writing or revising PromptClaw PRDs that will be loaded through `sdp-cli`.

The goal is simple:

- one PRD row should become one queue task
- one queue task should usually complete in one lead/verify cycle
- broad architectural intent belongs in section prose, not inside one task row

## Default Shape

Every queueable requirement should target:

1. one primary surface
2. one primary verb
3. one measurable outcome
4. one to three acceptance bullets

Good primary surfaces for PromptClaw:

- one package or module
- one service or daemon path
- one schema or manifest
- one device plugin
- one display path
- one CLI/status surface

Good primary verbs:

- define
- add
- publish
- map
- mount
- record
- replay
- announce
- approve

Avoid rows that chain verbs like:

- build + wire + verify
- install + configure + restart
- publish + announce + replicate
- map + render + calibrate

## PromptClaw-Specific Splitting Rules

### Home / Clone / Install

Split these apart:

- release snapshot format
- installer payload contents
- unattended bootstrap
- clone seeding
- post-install verification
- standalone-to-federated promotion

Do not put all of home creation into one row.

### Identity / Federation

Split these apart:

- identity record schema
- naming and rename history
- lineage metadata
- read announcement payloads
- read trust / revocation
- proposal inbox/outbox
- approval execution

Do not combine read visibility and mutation approval in one row.

### Publication

Split these apart:

- gallery page generation
- private-by-default network exposure
- explicit publish controls
- read-only public mode
- public artifact schemas

Do not mix artifact schema definition with publish transport.

### Bundles

Split these apart:

- bundle manifest types
- offer/discovery flow
- approval flow
- mounted-first import
- adoption / detach
- provenance / update offers

Do not mix risky plugin import with safe style-pack behavior in one row.

### Embodiment

Split these apart:

- shared state schema
- sensor contract
- event bus
- confidence fusion
- dual-display render contract
- face compositor
- text-weave behavior
- replay / rehearsal
- calibration / latency tools

Do not put face, gallery, audio, and replay into one requirement.

### Hardware / Interaction Loops

Split these apart:

- device input normalization
- state mapping
- output generation
- live-device failure handling
- replay harnesses

For example:

- normalize MIDI input
- map MIDI into face state
- map MIDI into gallery state
- emit Theramini output

not:

- wire MIDI into the whole organism

## Acceptance Criteria Rules

Acceptance criteria should prove one slice of behavior.

Good:

- one schema exists
- one event appears in the normalized stream
- one display reflects one mapped state
- one approval gate blocks unapproved mutation

Bad:

- end-to-end feature family works
- all services restart cleanly
- docs, tests, and monitoring updated

Documentation and broad operational follow-through can be tracked separately when they are materially large.

## Vague Language Is Forbidden

Agents time out and escalate when they cannot tell whether they are done. The #1 cause of this in PromptClaw's pipeline is subjective adjectives in task briefs. Replace them with measurable criteria.

### Banned Words

Do not use any of these in task descriptions or acceptance criteria:

| Banned | Why | Replace With |
|--------|-----|--------------|
| **clean** | unmeasurable | "passes ruff/mypy/pyflakes with zero warnings" or "removes named dead code `foo()` from line 42" |
| **proper** | unmeasurable | a named spec, RFC, or existing pattern to match |
| **robust** | unmeasurable | a list of failure modes that must be handled: "handles FileNotFoundError, permission denied, and partial writes" |
| **good** | unmeasurable | measurable property: "response under 100ms" or "passes test_foo.py::test_bar" |
| **correct** | unmeasurable | the exact output, exit code, or invariant |
| **appropriate** | unmeasurable | a named criterion or example |
| **nice** | unmeasurable | remove it or replace with a rendered example |
| **intuitive** | unmeasurable | a usability test with pass/fail criteria |
| **idiomatic** | unmeasurable | link to a style guide or an existing file to mirror |
| **well-structured** | unmeasurable | describe the structure: "one class per file, public methods in alphabetical order" |
| **comprehensive** | unmeasurable | enumerate the items: "covers all 6 status codes, all 4 verbs, the error path" |
| **optimized** | unmeasurable | a target metric: "reduces P50 latency below 50ms" |
| **elegant** | unmeasurable | either remove or describe the structural property you want |
| **reasonable** | unmeasurable | a specific value or range |

### The Disagreement Test

Before loading a task, ask: **"Could two reasonable LLMs complete this task and verify it differently?"**

If yes, the task is underspecified. Rewrite it until the answer is no.

**Example of a failing task (real pattern that timed out 6 times in production):**

> Implement the API endpoint cleanly with proper error handling.

Two different agents will:
- Disagree on what "cleanly" means (minimal? extensively commented? type-hinted?)
- Disagree on what "proper" means (exceptions? Result types? error codes?)
- Burn 30+ minutes each trying to meet an undefined bar
- Escalate when they can't tell if they succeeded

**The same task rewritten to pass the disagreement test:**

> Add endpoint `POST /api/v1/tickets` to `backend/api/tickets.py`.
> - Request body matches `TicketCreate` Pydantic model
> - Response is `Ticket` on success (201), `ErrorResponse` on failure (400/404/500)
> - Raises `HTTPException` 400 on invalid body, 404 if linked user missing, 500 on DB error
> - Adds test `test_tickets.py::test_create_ticket_success`
> - `ruff check` passes with zero warnings

Every sentence is testable. No reasonable agents will disagree on whether it's done.

### Subjective Words Test

Read your task brief out loud. Count the adjectives. If any of them could be answered with "it depends," that adjective does not belong in a task brief. It belongs in the section prose above the task table as context, not in the queueable row.

## Required Validation Loop

Before loading a PromptClaw PRD:

1. run `sdp-cli analyze --prd <path> --validate-only`
2. check `Queue-fit broad requirements`
3. split every warned row until the warning count is zero or intentionally justified
4. only then load the PRD into the queue

## Smell List

Rewrite a row if it contains:

- more than one major noun surface
- more than one major verb
- a long list separated by commas
- acceptance bullets proving different subsystems
- phrases like `and the gallery`, `and the daemon`, `and the dashboard`

## Practical Test

If you cannot point to the main file, service, schema, or display path that owns the row, the row is probably too broad.
