# Coherence API — the integration contract

`promptclaw.coherence` exposes a small, import-light, never-raises facade so an external host
(e.g. `sdp-cli`) can let the coherence engine govern a run without reaching into engine internals.

## Entry point

```python
from promptclaw.coherence import open_session

session = open_session(project_root, run_id=None, config=None)
```

- `project_root` — the project whose `.promptclaw/coherence.db` holds decisions, tensions, trust,
  graduation, and the event log. `constitution.yaml` (if present at the root) supplies the rules.
- `run_id` — the host's task id (a UUID is generated if omitted).
- `config` — a `CoherenceConfig`, a plain `dict`, or `None` (defaults). If `enabled` is false,
  or initialization fails, a `NullCoherenceSession` with identical signatures is returned.

## Methods

| Method | Returns | Purpose |
|---|---|---|
| `before_lead(task_text, agent="lead")` | `str` | Context to prepend to the lead prompt (active decisions, held tensions, constitution rules) |
| `after_lead(agent, output_text)` | `Verdict` | Capture ```decision```/```tension``` blocks, evaluate the constitution, update trust |
| `shared_shadow(**fields)` | `str` | Render the SHARED SHADOW lead→verify handoff (purpose / deliverable / …) |
| `before_verify(lead_output, agent="verify")` | `str` | Context to prepend to the verify prompt |
| `after_verify(agent, verdict_text)` | `Verdict` | Evaluate the verifier output; SEC-001 etc. surface here |
| `assess_triangulation(verdicts)` | `dict` | Independence-of-angle scoring of multiple verifier verdicts |
| `record_observation(was_true_positive)` | `None` | Feed graduation with an operator-confirmed signal (the high-quality one) |
| `note_override_outcome(violations, retry_output, agent="")` | `None` | Feed graduation from an override→retry outcome |
| `finish()` | `dict` | Finalize: graduation tick + write the re-entry digest. `{mode, reentry_path}` |
| `active_decisions()` / `open_tensions()` / `reentry_text()` / `trust_summary()` | reads | Inspect current state |

`Verdict` is a plain dataclass: `{approved: bool, violations: [{rule_id, severity, message}], trust_delta: float, mode: str}`.

## Guarantees

1. **Import-light** — `import promptclaw.coherence` pulls no orchestrator / CLI / music libs (enforced by `tests/test_import_isolation.py`).
2. **Never raises into the host** — every method is guarded; failures degrade to a safe default. A disabled/failed session is a `NullCoherenceSession`.
3. **JSON-friendly** — `Verdict` and the read helpers are dicts / dataclasses with string enums.
4. **Shared-DB safe** — concurrent hosts share `coherence.db` (SQLite WAL + busy_timeout).

## How `sdp-cli` consumes it (Phase 6)

At its task lifecycle (`src/sdp/_orchestrator/_task_loop.py`):

```python
session = open_session(project_root, run_id=task.id, config=settings.coherence)

# pre_lead seam (_task_loop.py:~452)
lead_prompt = session.before_lead(task_text) + "\n\n" + lead_prompt

# post_lead seam (~593)
v = session.after_lead(lead_name, lead_result.stdout)
if not v.approved:                       # a hard SEC-001 etc.
    emit_review_finding(v.violations)    # rides sdp-cli's existing operator-gated review

handoff = session.shared_shadow(purpose=task.description, deliverable=task.id, current_phase="verify")

# verify seams (~1309 / ~1741)
verify_prompt = session.before_verify(lead_result.stdout) + "\n\n" + verify_prompt
vv = session.after_verify(verify_name, verify_result.stdout)   # SEC-001 can block in the verdict chain

# review loop (pipeline/review_verify.py:133) — independence-of-angle
score = session.assess_triangulation(panel_verdicts)

# operator approves/rejects a finding -> the high-quality graduation signal
session.record_observation(was_true_positive=approved)

session.finish()                          # writes .promptclaw/reentry.md
```

The constitution (SEC-001) plugs into the same verdict post-processor chain as SI-003
(`_task_loop.py:1871-1913`), so a fabricated-evidence verdict is caught on the real path.
