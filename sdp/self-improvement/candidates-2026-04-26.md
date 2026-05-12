# Self-Improvement Candidates (2026-04-26)

Generated from recurring SDP gap evidence.
SAFETY-003: Operator approval required before queueing.
Auto-queue: disabled.

Total candidates: 4

## Candidate 1
- Gap ID: GAP-ffbk-6daeeb44
- Description: Address recurring verification failures in 'T1:general': Repeated FAIL feedback for 'T1:general' with shared keywords: add, all, appears, asserts, blocking
- Tier: T2
- Justification: Detected by 'repeated_fail_feedback' rule: 2 occurrences from 2026-04-16T18:20:59.868746+00:00 to 2026-04-16T18:21:16.584866+00:00. Repeated FAIL feedback for 'T1:general' with shared keywords: add, all, appears, asserts, blocking.
- Confidence: 0.50
- Expected Impact: med
- Evidence: 2 occurrences of repeated_fail_feedback in category 'T1:general'
- Source Rule: repeated_fail_feedback

## Candidate 2
- Gap ID: GAP-intv-30e5bde4
- Description: Automate resolution for recurring escalation: 'agent timeout'
- Tier: T2
- Justification: Detected by 'repeated_intervention' rule: 2 occurrences from 2026-04-16T18:54:48.048819+00:00 to 2026-04-17T02:52:12.828073+00:00. Repeated escalation: 'agent timeout' (2 occurrences).
- Confidence: 0.50
- Expected Impact: med
- Evidence: 2 occurrences of repeated_intervention in category 'escalation:agent timeout'
- Source Rule: repeated_intervention

## Candidate 3
- Gap ID: GAP-intv-fb4c2a05
- Description: Automate resolution for recurring escalation: 'lead provider unavailable'
- Tier: T2
- Justification: Detected by 'repeated_intervention' rule: 2 occurrences from 2026-04-16T18:20:59.864442+00:00 to 2026-04-16T18:21:16.577357+00:00. Repeated escalation: 'lead provider unavailable' (2 occurrences).
- Confidence: 0.50
- Expected Impact: med
- Evidence: 2 occurrences of repeated_intervention in category 'escalation:lead provider unavailable'
- Source Rule: repeated_intervention

## Candidate 4
- Gap ID: GAP-tout-ed9a17db
- Description: Reduce timeout rate for 'T1:general' tasks (5 timeouts detected)
- Tier: T1
- Justification: Detected by 'repeated_timeout' rule: 5 occurrences from 2026-04-16T18:54:15.196247+00:00 to 2026-04-25T19:04:24.023712+00:00. Task type 'T1:general' timed out 5 times.
- Confidence: 0.83
- Expected Impact: high
- Evidence: 5 occurrences of repeated_timeout in category 'T1:general'
- Source Rule: repeated_timeout
