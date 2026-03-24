# Routing Rules

## Core routing posture
- Route by content need, not fixed sequence.
- Prioritize these task families first: code changes, architecture planning, research, docs
- Typical output shape: plans, code + tests, and docs with citations
- Verification style: always verify technical work; lightweight verification for docs

## Agent lanes
- codex: implementation, tests, and refactors
- claude: architecture, specs, and verification
- gemini: research, synthesis, and documentation

## Lead selection
route code to codex, architecture to claude, and research/docs to gemini

## Ambiguity handling
ask when goal, format, or constraints are unclear

## Autonomy
fully autonomous except ambiguity

## Approval gates
production deploys and destructive file changes

## Red lines
never invent sources or make destructive changes without approval
