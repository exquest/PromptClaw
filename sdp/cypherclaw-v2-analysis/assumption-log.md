# Assumption Log

**Source:** CypherClaw v2 — Performance, Tuning, Space, and Public Presence PRD
**Extracted:** 2026-05-22T23:57:10.804549+00:00
**Status:** Non-blocking assumptions for review.

---

| ID | Assumption | Rationale | Risk If Wrong |
|---|---|---|---|
| ASM-001 | The cypherclaw box stays online and reachable via Tailscale SSH for the duration of the build. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-002 | The existing composer continues to be the correct entry point — no other composer process gets introduced. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-003 | Anthony has Cloudflare account access for the holdenu.com zone and can issue scoped API tokens, or grants tokens to the engineering agent ahead of Sprint 1. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-004 | Worker free-tier limits are sufficient (verified roughly above; quantify in Sprint 1 task). | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-005 | The local Ollama on cypherclaw is available for the rare design-question consultations during the build (only needed if a feature triggers a re-consultation of CypherClaw). | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-006 | The 12-day-running composer's existing scene database, music_tracker state, and `/tmp` state files persist; this build adds capabilities, doesn't reset the composer's memory. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |

**Total assumptions: 6**