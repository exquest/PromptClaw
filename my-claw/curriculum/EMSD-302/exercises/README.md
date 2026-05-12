# EMSD-302 Exercises

## ex01: Form Structure Builder

**Objective:** Define a multi-section composition form with valid transitions and at least three distinct sections.

**Verifier:** `structural`

**Template:**

```json
{
  "sections": true,
  "section_count": true,
  "transitions": true,
  "progressions": true,
  "total_duration": true,
  "form_label": true
}
```

**Expected features:**

- `sections`
- `section_count`
- `transitions`
- `progressions`
- `total_duration`
- `form_label`

## ex02: Counterpoint Relation Study

**Objective:** Write a two-voice section plan that names the counterpoint relation and verifies motion, consonance, and phrase-answer behavior.

**Verifier:** `constraint`

**Template:**

```json
{
  "counterpoint_relation": true,
  "primary_voice": true,
  "response_voice": true,
  "motion_profile": true,
  "consonance_policy": true
}
```

**Expected features:**

- `counterpoint_relation`
- `primary_voice`
- `response_voice`
- `motion_profile`
- `consonance_policy`

