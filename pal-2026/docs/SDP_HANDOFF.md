# SDP Handoff

Operator handoff from the PAL 2026 PRD to the `sdp-cli` task pipeline. Every
command below is local-only; none of them contact the live PAL router or write
to remote hosts.

## Analyze the PRD

Validate the PRD without loading it into the SDP queue:

```bash
sdp-cli analyze --prd sdp/prd-pal-2026-agentic-ops-platform.md --validate-only
```

Load the PRD into the SDP queue when ready, appending to any existing tasks:

```bash
sdp-cli analyze --prd sdp/prd-pal-2026-agentic-ops-platform.md --load --merge append
```

## Inspect the Task Queue

```bash
sdp-cli status
sdp-cli tasks list
```

## Run the SDP Loop

Drive the lead/verify pipeline through queued tasks:

```bash
sdp-cli run-loop
```

## Stage and Deploy

After implementation tasks finish, stage and deploy through the SDP path:

```bash
sdp-cli stage
sdp-cli deploy
```

Do not run mutating PAL deploy or cloud-spend actions unless Anthony has
explicitly approved them after reading the generated dry-run plan.
