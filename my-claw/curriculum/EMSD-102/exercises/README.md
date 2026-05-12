# EMSD-102 Exercises

## ex01: Tracker Scene Schema

**Objective:** Define a valid tracker scene structure with required fields for scheduling and playback.

**Verifier:** `structural`

**Template:**

```json
{
  "scene_id": true,
  "bpm": true,
  "steps": true,
  "voices": true,
  "duration_bars": true
}
```

**Expected features:**

- `scene_id`
- `bpm`
- `steps`
- `voices`
- `duration_bars`

