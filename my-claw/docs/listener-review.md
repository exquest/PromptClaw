# Listener Review Workflow

Weekly review of rendered pieces to catch expressive problems early, trace them
to specific render rules via ablation, and log decisions for the team.

## Cadence

Review all rendered pieces from the past 7 days every week. Pick a consistent
day (e.g. Monday morning) and block 30–60 minutes. Listen to each piece,
note anything that feels wrong, and record findings in the review log.

### What to listen for

- Dynamics that feel flat or overly compressed.
- Timbre shifts that don't match the intended mood arc.
- Rhythmic patterns that feel mechanical or rushed.
- Sections that sound identical when the score intends contrast.
- Audio novelty gaps where the symbolic novelty peaks suggest transitions.

## How to Ablate a Rule

When a piece sounds wrong, use the rule-stack provenance to identify which
rules were active, then ablate suspect rules one at a time to localize the
problem.

### Step 1: Find the rule stack

Each rendered piece has a `.meta.json` sidecar (written by `render.export`)
containing the full rule stack and quantities:

```json
{
  "rule_stack": ["R1", "R2", "R6"],
  "rule_quantities": {"R1": 1.0, "R2": 1.0, "R6": 0.7}
}
```

The same provenance is embedded in the WAV iXML chunk.

### Step 2: Run the ablation debugger

Use the `senseweave-render-debugger` CLI (CCH-010) to re-render the piece
with a suspect rule disabled:

```bash
senseweave-render-debugger \
  --score path/to/score.json \
  --renderer my_package.module:render_function \
  --rules R1,R2,R6 \
  --format text
```

To disable a specific rule (e.g. R6) and see the impact:

```bash
senseweave-render-debugger \
  --score path/to/score.json \
  --renderer my_package.module:render_function \
  --rules R1,R2,R6 \
  --format json \
  --output ablation-report.json
```

The debugger runs single-rule and combinatorial ablations, then ranks each
rule by expressive impact. Look for the rule with the highest `impact_score`
in the problem region.

### Step 3: Interpret the report

The JSON report includes:

- `ranked_rules`: rules sorted by expressive impact (highest first).
- `ablation_runs`: each combination tested, with `impact_score` and `summary`.
- `problem_region`: the region you scoped (or "all" if unbounded).

A high `single_impact` means that rule alone is responsible. A high
`combination_impact` with low `single_impact` means the rule only causes
problems in combination with others.

### CLI flags reference

| Flag                     | Description                                       |
|--------------------------|---------------------------------------------------|
| `--score PATH`           | Path to the score JSON file.                      |
| `--renderer DOTTED_PATH` | Import path for the renderer callable.             |
| `--rules IDS`            | Comma-separated rule IDs to include in ablation.   |
| `--seed NAME=INT`        | Seed values (repeatable).                          |
| `--phrase INDEX`          | Restrict analysis to specific phrase indices.       |
| `--note P:N`             | Restrict analysis to specific note (phrase:note).  |
| `--exclude-global`       | Exclude global-level changes from impact scoring.  |
| `--max-combination-size` | Max rules to disable simultaneously (default: 2).  |
| `--format json\|text`    | Output format (default: json).                     |
| `--output PATH`          | Write report to file instead of stdout.            |

## How to Attach a Review Note

After investigating a piece, record your findings in the weekly review log
at `my-claw/sdp/review-log.md`.

### Required fields

Each entry must include:

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| `piece`            | Filename or piece ID of the rendered audio.              |
| `date`             | Date of review (YYYY-MM-DD).                             |
| `felt_wrong`       | Free-text description of what sounded off.               |
| `suspected_rule`   | Rule ID from the provenance sidecar, or "unknown".       |
| `ablation_result`  | Summary of the debugger output, or "N/A" if not run.     |
| `action`           | One of: keep, disable, tune, escalate.                   |

### Example entry

```markdown
| 2026-04-14_dusk-piece-03.wav | 2026-04-17 | Dynamics felt flat in development section | R6 | R6 single_impact=4.20; disabling restored dynamic contrast | tune |
```

Copy the template row from the review log and fill in each field. Add notes
below the table row if the situation needs more context.
