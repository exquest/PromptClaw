# Master Plan — 2026-04-09

Four systems need work in the right order: **CypherClaw** (art organism), **PromptClaw** (toolkit/dev), **sdp-cli** (core pipeline), **R750** (work deployment). This document sequences all of them to avoid thrashing, blocked dependencies, or duplicated effort.

## Systems At A Glance

| System | Role | Current state | Who works on it |
|--------|------|--------------|-----------------|
| **CypherClaw** | Home art installation | 457/542 SDP tasks (84%), runner healthy, 85 remaining | CypherClaw's own SDP pipeline + manual fixes from here |
| **PromptClaw** | Dev toolkit (this MacBook) | R750 code built, synced from CypherClaw Day 1-4 work | Local SDP pipeline + manual work here |
| **sdp-cli** | Core pipeline infrastructure | 1 bug fixed (98da2b4), 4 more identified | Separate sdp-cli agent |
| **R750** | Work deployment (Dell PowerEdge) | Not started yet, docs + installer ready | Manual on-site install |

## Guiding Principles

1. **Don't create new work for a thrashing pipeline.** If CypherClaw is struggling, adding tasks makes it worse.
2. **Fix infrastructure bugs before features.** sdp-cli retry cascade costs 15-20% throughput on every project.
3. **Sequence parallel work by blocking dependencies, not by urgency.** The R750 bare-metal install is a hard prerequisite for everything R750-related.
4. **Let CypherClaw finish current queue before adding.** The artist plan completion PRD is loaded. Don't add another until it's drained.
5. **Use the local MacBook pipeline for pure-code work.** It has no quota pressure overnight (fresh morning creds) and no hardware dependencies.

---

## Phase 0: Stabilize (Today, Immediate)

**Goal:** Stop losing dev time. Everything should be autonomous.

| Task | Where | Status | Time |
|------|-------|--------|------|
| Restart CypherClaw SDP runner with sdp-cli fix | CypherClaw | ✅ Done | — |
| Commit CypherClaw Day 1-4 work | cypherclaw-private | ✅ Done | — |
| Sync Day 1-4 work to PromptClaw repo | PromptClaw | ✅ Done | — |
| Deliver sdp-cli bug report | sdp-cli agent | ✅ Done (this session) | — |
| Write R750 fast-path installer | PromptClaw | ✅ Done | — |

**All done.** Phase 0 complete as of this session.

---

## Phase 1: Let CypherClaw Drain (Today → Tonight)

**Goal:** Finish the current SDP queue without adding work.

**What's in the queue (85 remaining):**
- 14 tasks in `20260408T221920Z` — artist-plan-completion (visitor ID, printer, exhibition, room IR, B&P covers) — **these are the high-value ones**
- ~40 tasks in various `20260402T17550*Z` batches — embodiment, federation, bundle exchange, publication
- ~10 legacy tasks from earlier batches — stale, safe to skip

**Actions:**
1. **Do nothing to CypherClaw.** Let the runner work.
2. **Monitor from a distance.** Check `sdp-cli tasks list` every few hours. Don't restart, don't reload, don't load new PRDs.
3. **If it stalls again:** Pull sdp-cli updates, reset breaker, resume. The fix is in.

**Expected outcome:** By morning of 2026-04-10, CypherClaw should be at ~520/542 (95%+) with the APC batch largely complete.

**DO NOT:**
- ❌ Queue the 5-6 self-improvement candidates from the nightly report
- ❌ Load additional PRDs
- ❌ Manually fix individual failing tasks
- ❌ Restart services unless genuinely broken

---

## Phase 2: Deploy R750 (Date TBD — Depends On Work Access)

**Goal:** Bring the work server online as a PromptClaw peer.

### Phase 2a: Bare Metal (1-2 work days, requires physical access)
1. Open iDRAC, tune BIOS (HT off, SNC off, Performance profile, C1-only)
2. Boot Ubuntu 24.04 LTS via iDRAC virtual media
3. Install OS to BOSS M.2 (not the PERC array)
4. Configure networking + hostname
5. Install Tailscale, authorize via browser
6. Create regular sudo user (not root)

**Reference:** `docs/r750-bare-metal-runbook.md`

### Phase 2b: Automated Install (~15 min + 30-60 min for model pulls)
```bash
scp deploy/r750/install.sh user@r750:~/
ssh user@r750
GITHUB_TOKEN=ghp_... ./install.sh
```

The installer does all 13 phases automatically:
- System packages, Docker, PostgreSQL, Redis
- Ollama with dual NUMA-pinned systemd units
- Pulls `qwen3:30b-a3b`, `qwen3-coder:30b`, `nomic-embed-text`
- Clones PromptClaw, installs sdp-cli, sets up observatory DB
- Installs all systemd services, starts everything, verifies

**Reference:** `deploy/r750/README.md`

### Phase 2c: Federation (~10 min)
Once both CypherClaw and R750 are on the same Tailscale network:
- R750 daemon discovers CypherClaw peer via `federation/discovery.py`
- R750 mints its own identity (first_boot.py)
- No manual config needed — it's automatic

### Phase 2d: Initial Workload (~1 day)
- Load LG SoT PRDs or relevant work PRDs into the R750 SDP
- Run one smoke task through the Ollama path to verify `_invoke_ollama()` works
- Confirm `LOCAL_ONLY=true` mode prevents any cloud API calls
- Monitor agent_skills EMA scores as Ollama processes real tasks

**Expected outcome:** R750 running as standalone federated peer, handling its own work, zero cloud API dependence.

---

## Phase 3: sdp-cli Upstream Fixes (2-5 days, parallel with R750)

**Goal:** Fix the 4 remaining sdp-cli bugs so all projects benefit.

This work happens in the sdp-cli repo, not in CypherClaw or PromptClaw. Report already delivered at `docs/sdp-cli-findings-report.md`.

### Priority order (from the report):
1. **Process fix: Default launcher template** (30 min) — prevents new installs from hitting Bug 1
2. **Bug 2: Rotation cycle on provider outage** (~1 day) — saves ~4 hours per outage
3. **Bug 4: Retry cascade** (~1 day) — 15-20% throughput gain
4. **Bug 5: Integrity verdict split** (~4 hours) — cleaner failure signal
5. **Bug 3: Self-improvement temporal analysis** (~2 hours) — better nightly reports

### How we consume fixes

When the sdp-cli agent lands a fix, update CypherClaw and the MacBook:
```bash
# On CypherClaw
ssh cypherclaw 'cd /home/user/sdp-cli && git pull && sudo systemctl restart cypherclaw-sdp-runner'

# On MacBook
cd /Users/anthony/Programming/sdp-cli 2>/dev/null || git clone https://github.com/exquest/sdp-cli.git
cd sdp-cli && git pull && pip install -e .
```

---

## Phase 4: CypherClaw Finishing Work (After Phase 1 Drains)

**Goal:** Close remaining gaps the pipeline can't do autonomously.

### 4a: PRD Authoring Rules Update (1 hour, me)
Add to `my-claw/sdp/prd-authoring-rules.md`:
- Ban vague adjectives in task briefs: "clean", "proper", "robust", "good"
- Require each acceptance criterion to be measurable (file exists, test passes, function returns)
- Add checklist: "If an LLM could reasonably disagree on whether this criterion is met, rewrite it"

This fixes the "T1:general clean implementation timeout" pattern without queueing anything.

### 4b: Hardware-dependent tasks (manual, when I'm at CypherClaw)
These can't run in the SDP pipeline because they need physical access:
- **APC-006** Debug NS8360 thermal printer (need to see paper output)
- **APC-012** Measure room impulse response (need empty house + swept sine through SuperCollider)
- **APC-009** Welcome sticker printing (depends on APC-006)

Schedule: next time I'm home alone for a few hours.

### 4c: Deferred PRD cleanup
The federation/clone/bundle PRDs are loaded in CypherClaw's queue but shouldn't run yet per the execution roadmap. Options:
- **Leave them** — they'll process slowly and the code gets written, just not deployed
- **Skip them** — mark as blocked with reason "deferred per roadmap stage 10-14"
- **Remove them** — clear the tasks entirely

**Decision:** Leave them. The code doesn't hurt if it's written but not enabled, and having it ready means federation is just a config flag away when you want it.

---

## Phase 5: R750 Production Workloads (After Phase 2 Complete)

**Goal:** Move real work onto the R750.

### 5a: LG SoT Deployment
The LG SoT firewall migration bot was one of the primary reasons for the R750. Once PromptClaw is running there:
1. Clone LG SoT onto R750
2. Configure LG SoT to use local Ollama via PromptClaw's `_invoke_ollama()`
3. Run a migration test against a staging firewall
4. Monitor agent_skills for the `netops` category — Ollama seeded at 0.80, should climb with real workload

### 5b: PromptClaw SDP on R750
Load the PromptClaw SDP queue onto R750:
1. `sdp-cli init` in the R750 clone
2. Load only the work-relevant PRDs (skip CypherClaw art ones)
3. Let the R750 SDP pipeline handle its own development cycles
4. Observatory scores will diverge from CypherClaw as each system learns its own workload patterns

### 5c: Inter-home federation (optional, later)
Once both systems are stable, optionally:
- Enable `FEDERATION_MODE=federated` in R750's `.env`
- R750 announces identity to CypherClaw
- Read-visible status cross-sharing via `federation/discovery.py`
- No write sharing — that's a separate PRD (federation-proposal-writes)

---

## Phase 6: Art Organism Deep Work (Ongoing)

**Goal:** Phases 6-7 of the Artist's Plan.

This is the long-tail artistic evolution — it runs forever. Key work:
- **Leitmotif system** (SO-011) — music memory that grows over months
- **Coprime rhythm** (SO-007) — Lewis-style entrained timing
- **Harmonic navigation** (SO-006) — Grimoire-complete scale/chord vocabulary
- **Physical models** (SO-004) — Karplus-Strong, waveguide, etc.
- **Room convolution reverb** (APC-012, APC-013) — from measured room IR
- **Practice mode** (SO-015) — autonomous musical exploration

None of this is on a deadline. It happens as CypherClaw keeps running and the SDP pipeline keeps chewing through the synthesis-and-orchestration PRD.

---

## Decision Matrix: What to Do When Something Breaks

| If... | Then... | Don't... |
|-------|---------|----------|
| CypherClaw pipeline stalls | Check circuit breaker, reset if needed, check runner process | Load new PRDs, manually complete tasks |
| Agent quota exhausted | Wait for reset (24h) OR wait for R750 deployment | Swap providers manually |
| Task keeps failing | Let retry logic handle it (after sdp-cli Bug 4 fix) | Manually force status changes |
| New feature needed | Write a PRD, validate with `sdp-cli analyze --validate-only`, load in correct project | Write code in both CypherClaw and PromptClaw |
| sdp-cli behaves wrong | Check sdp-cli findings report, consider if it's a known bug | Patch locally without filing upstream |
| R750 install fails partway | Re-run `./install.sh` (idempotent) | Delete and start over |
| Federation misbehaves | Disable it (`FEDERATION_MODE=standalone`), debug | Let it block core work |

---

## What to Watch

### Short-term (next 24 hours)
- CypherClaw SDP runner stays active (`systemctl is-active cypherclaw-sdp-runner`)
- Circuit breaker stays closed (`sdp-cli circuit status`)
- Task count decreases toward zero (pending + needs_split)
- No "max work retries exceeded" patterns in new task_runs

### Medium-term (next week)
- sdp-cli fixes land in a release
- R750 bare metal install scheduled
- Artist plan completion PRD (APC) tasks largely done
- Face display + keyboard chat stable through multiple reboots

### Long-term (next month)
- R750 deployed and running LG SoT
- CypherClaw's synthesis-and-orchestration PRD (15 tasks) making progress
- First real leitmotifs stored and recalled in music
- B&P stories with color cover art

---

## Open Questions

1. **When can you get physical access to the R750?** This gates everything R750-related.
2. **Do we want federation enabled between CypherClaw and R750?** Not required but nice.
3. **Should CypherClaw's SDP skip the federation/clone PRDs entirely?** My recommendation is no — let them process.
4. **Is the LG SoT PRD ready to load on R750 once deployed?** Need to confirm what PRDs exist for that workload.
5. **Who owns the sdp-cli fixes?** You mentioned an sdp-cli agent — is that a separate Claude Code session?

---

## TL;DR

- **Now:** Let CypherClaw drain. Don't touch it. Report delivered to sdp-cli agent.
- **Today/Tomorrow:** CypherClaw finishes the artist plan completion work.
- **This week:** R750 bare metal install when you're on-site. sdp-cli fixes land upstream.
- **Next week:** R750 live with Ollama, LG SoT moved over, CypherClaw keeps evolving.
- **Always:** Don't add work to a thrashing pipeline. Fix the infrastructure first.
