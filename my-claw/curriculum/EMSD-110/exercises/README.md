# EMSD-110 Exercises

## ex01: Interval and Scale Matrix

**Objective:** Build an interval matrix and modal scale table that can seed production-course mode_scale decisions.

**Verifier:** `constraint`

**Template:**

```json
{
  "intervals": [
    "P1",
    "m2",
    "M2",
    "m3",
    "M3",
    "P4",
    "P5"
  ],
  "scale_degrees": [
    0,
    2,
    4,
    5,
    7,
    9,
    11
  ],
  "mode_scale": "ionian",
  "root_pitch": "C4",
  "valid_step_pattern": true
}
```

**Expected features:**

- `intervals`
- `scale_degrees`
- `mode_scale`
- `root_pitch`
- `valid_step_pattern`

