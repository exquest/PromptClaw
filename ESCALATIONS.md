# Escalations

Items requiring human review. Append-only per task.

## T-001 (2026-04-01T18:55:24.984659+00:00)

- **Reason:** Agent timeout
- **Details:** T-001 timed out twice. Run sdp-cli tasks split T-001 to break it down.

## T-001 (2026-04-01T18:56:11.434931+00:00)

- **Reason:** Agent timeout
- **Details:** T-001 timed out twice. Run sdp-cli tasks split T-001 to break it down.

## T-001 (2026-04-01T18:56:41.692113+00:00)

- **Reason:** Agent timeout
- **Details:** T-001 timed out twice. Run sdp-cli tasks split T-001 to break it down.

## T-009@20260408T220341Z (2026-04-08T22:12:54.185469+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=85.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=85.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=85.0%

## T-001@20260408T223256Z (2026-04-08T22:33:10.555043+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=84.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%

## T-001@20260408T223256Z (2026-04-08T23:10:00+00:00)

- **Reason:** Validation blocked by pre-existing repo issues
- **Details:** `pytest tests/ -x` stopped during collection in `tests/test_first_boot.py` because `cypherclaw` is not importable from this checkout. `ruff check src/ tests/` and `mypy src/` also fail because the repo has no `src/` directory. `pip install -e '.[dev]'` completed but warned that `promptclaw 3.0.0` does not define a `dev` extra.

## T-004@20260408T223256Z (2026-04-08T23:05:05.007269+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=84.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=84.0%

## T-004@20260408T223256Z (2026-04-09T00:14:00+00:00)

- **Reason:** Scope constraint on orchestration docs
- **Details:** `AGENTS.md` asks for architecture/command/startup/changelog updates on orchestration changes, but this task also constrained edits to the bug-fix scope and those doc files already had unrelated local modifications. I limited the change set to the Ollama routing fix plus regression coverage and did not modify the product docs in this task.

## T-007@20260408T223256Z (2026-04-08T23:29:49.940049+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=83.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%

## T-007@20260408T223256Z (2026-04-08T23:37:23Z)

- **Reason:** Shared local-provider health granularity
- **Details:** The selector now excludes `ollama` when every configured Ollama route port is unhealthy and re-admits it when any configured port recovers. Health is tracked at the shared local-provider level, so a single-socket outage can still leave `ollama` eligible for categories routed to the down socket if another configured socket remains healthy.

## T-010@20260408T223256Za (2026-04-09T00:02:48.014232+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=83.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=83.0%

## T-010@20260408T223256Za (2026-04-09T00:24:00+00:00)

- **Reason:** Scope and latency assumptions
- **Details:** This split task only adds the daemon-side `ollama_health()` helper for dual sockets `11434` and `11435`; `/status` integration and Telegram `/local` formatting remain assigned to sibling subtasks `T-010@20260408T223256Zb` and `T-010@20260408T223256Zc`. Response latency is treated as daemon-side wall-clock time for the health probe; unreachable instances should return an unhealthy status, an empty model list, and `latency_ms` of `None` instead of raising.

## T-010@20260408T223256Zc (2026-04-09T00:34:30+00:00)

- **Reason:** Missing `/local` surface and status-endpoint assumption
- **Details:** The current tree has no Telegram `/local` built-in and no separate daemon `/status` JSON endpoint. This task will add a shared in-process status snapshot consumed by both `/status` and the new `/local` command so `/local` can format Ollama health without duplicating probes. Scope is limited to the base `/local` status view; `/local bench` and `/local stats` remain out of scope for T-010c. No new dependencies are planned.

## T-011@20260408T223256Z (2026-04-09T00:41:41.054077+00:00)

- **Reason:** Ordered degradation policy
- **Details:** step-1: reason=verify-first tier cascade: promoted verify-tier model as lead; original_pair=claude->codex; degraded_pair=codex->claude; remaining_headroom=82.0%
step-2: reason=effort-first lead-tier downgrade applied (codex effort xhigh -> high) before family/version fallback; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=82.0%
step-3: reason=same-provider verify fallback attempted but no same-provider verify candidate was available; original_pair=codex->claude; degraded_pair=codex->claude; remaining_headroom=82.0%

## T-011@20260408T223256Z (2026-04-09T01:05:00+00:00)

- **Reason:** LOCAL_ONLY scope assumption
- **Details:** This task treats `LOCAL_ONLY` as a daemon-level LLM routing guard. When enabled, all daemon agent-execution paths that would otherwise target `claude`, `codex`, or `gemini` are coerced to `ollama`, including router fallback and explicit step payloads. Non-agent operational commands (for example Telegram delivery, shell built-ins, or health probes) remain unchanged. No new dependencies are planned.

## T-012@20260408T223256Z (2026-04-09T01:30:00+00:00)

- **Reason:** Transport and dependency scope assumptions
- **Details:** This task uses stdlib-only HTTP probing (`urllib.request`) and `subprocess` for `tailscale status --json` — no new external dependencies. The identity endpoint is probed over plain HTTP on port 8443 (matching the federation PRD convention); TLS/signing verification is deferred to a future federation identity task (FD-001/FD-005). The module lives in `promptclaw/federation/discovery.py` following the PRD architecture layout. Peers are identified by `instance_id` for merge deduplication. Offline Tailscale peers are excluded from probing.
