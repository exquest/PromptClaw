# CypherClaw Curriculum

This tree holds formal study tracks for CypherClaw.

Current tracks:

- `EMSD` — Electronic Music Production and Sound Design

Each course directory is scaffolded with:

- `README.md` for course framing and runtime mapping
- `reference/` for knowledge notes
- `prompts/` for composition and analysis prompt templates
- `exercises/` for verifiable tasks
- `COMPLETION.md` for progress tracking

Exercise specs are machine-verifiable JSON records with an `objective`, runnable
`template`, declared `verifier`, and `expected_features`. The legacy `expected`
key remains present for older tooling.

The catalog and scaffold generator live in:

- `curriculum/catalog.py`
- `curriculum/bootstrap.py`
