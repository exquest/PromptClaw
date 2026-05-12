# SDP Self-Improvement PRD — Wrapper-Service Verification Gaps

**Date:** 2026-05-03
**Trigger:** narrative_api wrapper shipped 16 PASSed tasks but failed every endpoint at deploy
**Full context:** `sdp/postmortem-narrative-api-engine-mismatch.md`

## Short report (what happened, what to learn)

The narrative_api SDP plan completed all 16 tasks (T-001..T-015) with green
verifications. On deploy to cypherclaw the service started cleanly but every
endpoint except `/health` returned 503/500: the wrapper imported a fictional
`cypherclaw.narrative.events.NarrativeEventStore` class and called
`NarrativeMemory()` with no args (the real signature is
`NarrativeMemory(world, ollama_url=...)`).

The unit tests passed because they mocked the engine. The *risk register*
even flagged this exact failure mode (PRD line 131) and prescribed
*"each endpoint test includes a real engine call; signature mismatch caught
at test time"* — but the verifier accepted mock-only tests as compliant.
Three other gaps reinforced the failure:

1. CN-001 migration was marked PASS without anyone running
   `PRAGMA table_info` on the live DB.
2. Lazy `importlib.import_module` calls hid the broken engine references —
   the service start-up looked healthy; failure only surfaced at first
   request.
3. The PRD did not capture the engine's actual surface (class names, method
   signatures) — so there was no spec-time check that the wrapper's calls
   matched what existed.

The SDP runner is doing many things well — the test deepening campaign
(frac-0080..0121) is solid. But the wrapper / service-integration task class
needs three guardrails it doesn't yet have.

## Handoff prompt for sdp-cli

Paste the section below as a new PRD. Suggested filename:
`prd-sdp-wrapper-verification-guardrails.md`. Run via the standard SDP
ingestion path (`sdp-cli analyze --load`). Total estimated effort:
~10 atomic requirements, ~12-18 hours.

```
# SDP Wrapper-Service Verification Guardrails (self-improvement PRD)

**Goal:** prevent another wrapper-service plan from shipping with a fictional
target API and mock-only verification, of the kind that cost a full afternoon
on 2026-05-03 (narrative_api ↔ cypherclaw.narrative engine surface drift).

**Scope:** changes to the SDP fractal/template generator, verifier checklist,
and PRD ingestion phase. Affects future SDP work — does not retroactively
re-run completed PRDs.

**Reference:** `sdp/postmortem-narrative-api-engine-mismatch.md` for the full
incident. Read first.

## Atomic Requirements

| ID | Requirement | Priority | Tier | Acceptance |
|---|---|---|---|---|
| SI-001 | New PRD-ingestion step "engine surface capture": for any task whose spec mentions wrapping/calling/exposing an existing module, the analyzer runs `python -c "import inspect; from <module> import <Class>; print(inspect.signature(...))"` against each cited class and embeds the captured signatures into the spec doc as a `## Engine Surface Snapshot` section. Skip silently if module isn't importable from the analyzer's environment, but emit a `risk:` note. | MUST | T2 | Running `sdp-cli analyze` on a PRD that names `cypherclaw.narrative.NarrativeEngine` produces a spec doc containing the live `__init__` signature; if the module isn't importable, the spec contains `risk: engine surface unverifiable from analyzer environment`. |
| SI-002 | Verifier rule: if a task's verification report contains the word "mock" or "Mock" applied to a target the wrapper is supposed to wrap (heuristic: target name appears in the spec's `## Engine Surface Snapshot`), the verdict downgrades from PASS to PASS WITH NOTES and emits a `notes` block citing the mock-vs-real-call gap. | MUST | T1 | A test file with `def test_x(): mock_engine = Mock(); ...` against a name in the engine snapshot causes the verifier to flag PASS WITH NOTES; a test calling the real symbol passes cleanly. |
| SI-003 | Verifier rule for migration tasks: any task whose spec mentions `ALTER TABLE`, `CREATE TABLE`, `migration`, or `schema change` cannot reach PASS until its verification report includes evidence of running the migration against a real database — minimally a `PRAGMA table_info(<table>)` snapshot after the migration with the new column visible. | MUST | T1 | T-007 in the original narrative-api plan would have failed verification under this rule until someone ran the SQL and pasted the post-migration schema; passes once that evidence is present. |
| SI-004 | Add to fractal/template for "wrapper service" PRDs a mandatory atomic requirement (call it CN-VERIFY): "Smoke test against deployed instance — at minimum one request per endpoint returning the expected status code, with credentials, against the running service (not a TestClient)." This requirement cannot be satisfied by an in-process Pydantic-only test. | MUST | T2 | Generated wrapper-service PRDs from `sdp-cli plan` contain a CN-VERIFY-equivalent task. Existing wrapper PRDs in the queue get a follow-up gap-filler task added. |
| SI-005 | Lazy-import startup self-check: linter rule that flags any wrapper module containing `importlib.import_module(...)` inside a `build_default_*()` factory unless the same module also has a `selftest()` function called at app startup that exercises the factory and logs a warning on failure. | SHOULD | T1 | `narrative_api/events.py` (pre-rewrite) would have triggered the linter for the lazy import without a selftest; post-rewrite it does not (the engine_container builds eagerly on first call from `app` startup logging). |
| SI-006 | Post-mortem template: add `sdp/postmortem-template.md` — a 4-section template (what happened / why every gate passed / what we changed / lessons-as-action-items). The runner's self-repair flow should auto-create one for any verified-PASS task that subsequently fails in production. | SHOULD | T1 | The 2026-05-03 postmortem matches the template structure when retrofitted; new ones written from the template need only the incident-specific facts. |
| SI-007 | Documentation: cross-link `sdp/fractal-reports/` and `docs/` index to the postmortem corpus so future SDP runs surface relevant prior incidents during the analyze phase. | SHOULD | T1 | `sdp-cli analyze` on a new PRD touching `narrative_api/` includes a "related postmortems" footnote pointing at the 2026-05-03 doc. |
| SI-008 | Risk-register enforcement: when a PRD's `## Risks` section lists a mitigation (e.g. "real engine call in tests"), that mitigation must appear as either an explicit acceptance criterion on at least one MUST task, or as a verifier rule. PRDs that list mitigations without binding them to a verification step fail PRD-ingest validation. | MUST | T1 | The original narrative_api PRD line 131 mitigation ("each endpoint test includes a real engine call; signature mismatch caught at test time") would have failed PRD-ingest until tied to CN-014 acceptance criteria. |
| SI-009 | Add "deploy-time first-request gate" to the SDP runner's deploy-task verifier: any task whose ExecStart involves `systemctl start ... && systemctl is-active` must additionally do a single authenticated request against the service's primary endpoint and confirm a 2xx response before recording PASS. | MUST | T2 | A task that starts `cypherclaw-narrative-api.service` and confirms `is-active` returns "active" but receives 503 on first POST records FAIL with the response body in the verification log. |
| SI-010 | Self-improvement candidate ledger: append a 1-line summary of this incident to `sdp/self-improvement/candidates-2026-05-03.md` — `[narrative_api] mock-only verifier accepted 16 PASS tasks → see SI-001..SI-009`. | MUST | T1 | The candidate ledger contains the line; a future analyzer that scans the ledger for "mock" surfaces the incident as related context. |

## Out of scope

- Retroactively re-running PRDs that already shipped. Adding the new
  guardrails to the runner is enough; the active PRDs already in flight
  use the existing rules.
- Changing the test-deepening fractal pattern (frac-0080..frac-0121).
  That campaign is working well and isn't the failure mode.
- Touching the production cypherclaw deployment. The fix already landed
  in commit `fb85b2d`. This PRD is purely about preventing recurrence.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| SI-001's signature-capture step fails when analyzer runs in an environment without the target module installed | High | Low | Already mitigated in spec — emit `risk:` note rather than failing. |
| SI-002 produces false positives on legitimate test files that mention "Mock" in unrelated context | Medium | Low | Heuristic ties detection to names in the snapshot, not free-text "Mock" mentions. |
| SI-009 deploy-time gate slows down deploy tasks by ~3-5s per task | Low | Low | Acceptable cost; smoke is one HTTP request. |

## Assumptions

1. The current SDP fractal/template generator is editable from a known location
   (likely `sdp/fractal.py` or a config file); SI-001 / SI-004 patches go there.
2. The verifier has access to filesystem reads of the test report — not just
   pass/fail bits — so SI-002 can grep for "mock".
3. There is a known "self-improvement candidates" ledger at
   `sdp/self-improvement/candidates-*.md` that accepts append-only entries.

## Spec quality scorecard

- **Engine surface snapshot in this PRD:** N/A — this PRD targets the SDP
  runner itself, which is the authority on its own internals.
- **Real-engine integration test required:** yes (SI-009 enforces it).
- **Risk register binds to acceptance criteria:** yes (SI-008 enforces it).
```

## Operator handoff steps

1. Save this file's PRD section as `prd-sdp-wrapper-verification-guardrails.md`
   at the repo root.
2. `sdp-cli analyze --prd prd-sdp-wrapper-verification-guardrails.md --load`
3. `sdp-cli run-loop` (or whatever your normal loop is) — the work is sized
   for 12-18 hours and produces ~10-20 atomic tasks.
4. After completion: re-run any wrapper-service PRD currently in the queue
   to confirm the new guardrails fire without false positives. The
   narrative_api commit `fb85b2d` is a useful regression target — it should
   pass the new verifier rules cleanly.
