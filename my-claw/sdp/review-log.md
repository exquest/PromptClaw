# Weekly Listener Review Log

Structured log of listener review sessions. Each entry records a piece that
was reviewed, what sounded wrong, which rule is suspected, the ablation
result, and the action taken.

Ablation is performed using the `senseweave-render-debugger` CLI (CCH-010).
See `my-claw/docs/listener-review.md` for the full workflow guide.

## Log

| piece | date | felt_wrong | suspected_rule | ablation_result | action |
|-------|------|------------|----------------|-----------------|--------|
| 2026-04-14_dusk-piece-03.wav | 2026-04-17 | Dynamics felt flat in development section; symbolic novelty peaks present but audio contrast absent | R6 | R6 single_impact=4.20, combination_impact=0.00; disabling R6 restored dynamic contrast in phrases 2-4 | tune |
