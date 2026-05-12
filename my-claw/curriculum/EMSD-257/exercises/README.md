# EMSD-257 Exercises

## ex01: SenseWeave Mapping Contract

**Objective:** Map audio analysis features to GlyphWeave visual targets with stable names, ranges, and coherence checks.

**Verifier:** `constraint`

**Template:**

```json
{
  "senseweave_mapping": {
    "brightness": "color_luma",
    "density": "stroke_count"
  },
  "audio_features": [
    "brightness",
    "motion",
    "texture",
    "density"
  ],
  "visual_targets": [
    "color_luma",
    "particle_speed",
    "edge_noise",
    "stroke_count"
  ],
  "range_policy": {
    "input": "0.0-1.0",
    "output": "normalized"
  },
  "coherence_checks": [
    "monotonic_density",
    "bounded_motion"
  ]
}
```

**Expected features:**

- `senseweave_mapping`
- `audio_features`
- `visual_targets`
- `range_policy`
- `coherence_checks`

