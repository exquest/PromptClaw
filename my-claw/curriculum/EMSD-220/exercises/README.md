# EMSD-220 Exercises

## ex01: Groove Grid Template

**Objective:** Create a bar-level groove grid with meter, subdivision, swing, accent, and density metadata for tracker scheduling.

**Verifier:** `temporal`

**Template:**

```json
{
  "groove_grid": [
    1,
    0,
    0.5,
    0,
    1,
    0,
    0.75,
    0
  ],
  "meter": "4/4",
  "subdivision": "eighth",
  "swing_ratio": 0.58,
  "accent_pattern": [
    0,
    4,
    6
  ],
  "density_profile": "medium"
}
```

**Expected features:**

- `groove_grid`
- `meter`
- `subdivision`
- `swing_ratio`
- `accent_pattern`
- `density_profile`

