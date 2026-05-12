# Task frac-0045 Specification: composer_quote_verify depth 2

## Problem Statement

`my-claw/tools/composer_quote_verify.py` is the hardware-free smoke verifier
for the sampler self-quotation loop. It synthesizes the known room tone from
`sample_capture_verify`, drives three composer self-quote captures through a
fake JACK self bus, and confirms that at least one `samples/self/` descriptor
shares arc phase and acoustic-tag overlap with the known room descriptor.

The end-to-end smoke path already works, but the fractal classifier reports
depth 1 (`13/18 trivial, 5 real`) because most of the file is fake-JACK adapter
plumbing and direct getters/setters. Operators can only inspect the CLI's
printed key/value lines; there is no typed report object that other checks can
reuse without parsing stdout.

This task deepens the module to a simple depth-2 implementation by adding one
typed report path around the existing behavior. The original CLI output and
self-quote capture semantics remain the same.

## Technical Approach

- Add a frozen `QuoteVerificationReport` dataclass that records the known room
  descriptor identity/tags, requested piece count, captured self-quote count,
  captured song ids, the best `QuoteMatch | None`, an overlap score, and an
  operator status string.
- Add small typed helpers for the report path:
  - normalize acoustic tags into stable, de-duplicated tuples;
  - compute descriptor/candidate overlap and overlap score;
  - parse a self-quote SQLite row into a `QuoteMatch`;
  - choose the first matching quote using the same one-path arc-phase/tag
    criteria as the current `find_motif_tag_match`;
  - build a full report by running known-room capture, composer piece capture,
    and motif/tag matching end-to-end;
  - summarize/render the report into JSON-safe values and the existing CLI
    key/value lines;
  - map the report to the same exit codes (`0`, `1`, `2`) the CLI uses today.
- Keep `trigger_composer_pieces`, `find_motif_tag_match`, and `main` public
  signatures stable. `main` may delegate to the new report/render helpers but
  must print the existing success lines so current tests and operator docs stay
  valid.
- Use only the standard library plus the module's existing numpy/sample-capture
  imports. No new dependencies, migrations, provider secrets, database columns,
  or runtime state files are required.

## Edge Cases

- If no self-quotes are captured, the report status is `no_self_quotes` and the
  CLI returns `1` with the existing `NO_SELF_QUOTES` stderr message.
- If self-quotes exist but none share arc phase and acoustic-tag overlap with
  the descriptor, the report status is `no_motif_tag_match` and the CLI returns
  `2` with the existing `NO_MOTIF_TAG_MATCH` stderr message.
- Acoustic tag normalization preserves first-seen order and drops empty or
  duplicate values.
- Empty candidate tags produce an overlap score of `0.0`.
- Existing startup identity hardening is outside this module but remains a
  required regression anchor: the tree already calls `bootstrap_identity()`
  before `FirstBootAnnouncer` in both daemon entrypoints and persists identity
  across standalone/federated boots.

## Acceptance Criteria

1. Existing composer quote verifier behavior remains unchanged.
   VERIFY: `pytest tests/test_composer_quote_verify.py -q`

2. The report path runs the known-room capture, three composer pieces, and
   motif/tag matching end-to-end with meaningful typed output.
   VERIFY: `pytest tests/test_composer_quote_verify_depth.py::test_build_quote_verification_report_runs_end_to_end -q`

3. Report summaries are JSON-safe and expose descriptor, capture, match, score,
   and status fields for operator/diagnostic callers.
   VERIFY: `pytest tests/test_composer_quote_verify_depth.py::test_summarize_quote_verification_report_is_json_safe -q`

4. Rendered report lines preserve the CLI success keys and the report exit code
   remains `0` for a successful match.
   VERIFY: `pytest tests/test_composer_quote_verify_depth.py::test_rendered_report_lines_preserve_cli_success_shape -q`

5. Reports without captures or without motif/tag matches map to the existing
   non-zero exit codes and failure statuses.
   VERIFY: `pytest tests/test_composer_quote_verify_depth.py::test_report_exit_codes_cover_failure_statuses -q`

6. Fractal depth for `my-claw/tools/composer_quote_verify.py` reaches at least
   depth 2.
   VERIFY: `pytest tests/test_composer_quote_verify_depth.py::test_composer_quote_verify_module_reaches_depth_two -q`

7. Startup identity hardening remains covered for standalone/federated
   persistence and daemon startup ordering.
   VERIFY: `pytest tests/test_first_boot.py::TestStartupIdentityPersistence tests/test_governor_integration.py::TestStartupIdentityWiring -q`

8. Full project validation remains clean.
   VERIFY: `pip install -e '.[dev]' && pytest tests/ -x && ruff check src/ tests/ && mypy src/`
