# Assumption Log

**Source:** PAL 2026 Agentic Operations Platform PRD
**Extracted:** 2026-05-15T21:42:33.417472+00:00
**Status:** Non-blocking assumptions for review.

---

| ID | Assumption | Rationale | Risk If Wrong |
|---|---|---|---|
| ASM-001 | PromptClaw remains the local control plane. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-002 | PAL router remains reachable over Tailscale at `http://pal-cloud-a6000:8000`. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-003 | The current Vast instance may be recreated in the future, so host, port, instance id, and SSH key path must be metadata/config, not hardcoded into source. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-004 | `sdp-cli` frontier agents can make better implementation choices than PAL's local 70B model; PAL should not self-modify this codebase. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-005 | Anthony prefers minimal involvement but still wants explicit approval for cost-bearing and mutating operations. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |
| ASM-006 | Phase 1 remains the active hardware target until Anthony explicitly authorizes Phase 2. | Derived from PRD assumptions bullet. | Risk if wrong not specified in PRD. |

**Total assumptions: 6**