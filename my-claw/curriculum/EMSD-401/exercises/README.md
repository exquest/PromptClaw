# EMSD-401 Exercises

## ex01: DSP Chain Designer

**Objective:** Design a DSP processing chain with valid connectivity between nodes and all parameters within safe operational bounds.

**Verifier:** `constraint`

**Template:**

```json
{
  "chain_nodes": true,
  "connectivity_valid": true,
  "param_bounds_safe": true,
  "input_node": true,
  "output_node": true
}
```

**Expected features:**

- `chain_nodes`
- `connectivity_valid`
- `param_bounds_safe`
- `input_node`
- `output_node`

