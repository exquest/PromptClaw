# EMSD-201 Exercises

## ex01: Synthesis Patch Validator

**Objective:** Define a synthesis patch with parameters constrained to safe ranges across subtractive, FM, and additive architectures.

**Verifier:** `constraint`

**Template:**

```json
{
  "architecture": true,
  "oscillator_freq": true,
  "filter_cutoff": true,
  "envelope_attack": true,
  "output_level": true
}
```

**Expected features:**

- `architecture`
- `oscillator_freq`
- `filter_cutoff`
- `envelope_attack`
- `output_level`

