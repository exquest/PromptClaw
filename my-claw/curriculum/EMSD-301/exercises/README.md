# EMSD-301 Exercises

## ex01: Frequency Band Allocator

**Objective:** Allocate frequency bands to mix roles ensuring no critical masking overlaps between competing elements.

**Verifier:** `constraint`

**Template:**

```json
{
  "bass_range": true,
  "low_mid_range": true,
  "mid_range": true,
  "presence_range": true,
  "master_chain": true,
  "no_masking_overlap": true
}
```

**Expected features:**

- `bass_range`
- `low_mid_range`
- `mid_range`
- `presence_range`
- `master_chain`
- `no_masking_overlap`

