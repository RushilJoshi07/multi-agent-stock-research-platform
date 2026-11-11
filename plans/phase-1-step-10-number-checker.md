# Phase 1 step 10 (worktree C): number checker, extracted from old verdict.py @ 73ae58e

## Context
Sacred Gate 2 (no invented numbers) needs a code fact check. The old project has one inside
`src/agentic_core/verdict.py` (73ae58e, 789 lines), tangled with DB models, the LLM client and
the hypothesis/verdict flow. `plans/phase-1-import-foundations.md` step 10 + "Changes from
review" item 4: extract only the checker into `src/fact_check/`, pure, no DB, no new deps,
in worktree C. Branch `worktree-number-checker` is at `23be043` = `origin/main`.

## Files (only these)
- `src/fact_check/__init__.py`: re-exports the public names.
- `src/fact_check/models.py`: plain copies of `Claim` (statement, tool_call_trace_id, metric,
  value) and `FalsificationCondition` (metric Literal of the 6 names, comparison Literal,
  threshold, the p_value-in-[0,1] validator). Pydantic only (already pinned, 2.13.4). No
  `StrategyRule` / pandas-ta import.
- `src/fact_check/checker.py`: `_REL_TOLERANCE`/`_ABS_TOLERANCE` (0.01), `_NUMBER_RE`,
  `_NAME_DIGIT_LETTER_RE`, `_SELF_REFERENCE_GAP_RE`, `_TIME_UNIT_WORDS`, `_WORD_RE`,
  `_self_reference_digit_letters`, `_is_self_reference`, `_close`, `validate_claims`,
  `scan_for_unreferenced_numbers`. Logic identical; ruff-formatted to 100 cols.
- `tests/fact_check/test_checker.py`: the 18 ported tests + 2 new NaN tests.

## The one real adaptation: what `validate_claims` takes
Old signature takes `list[ToolCallTraceRow]` (SQLAlchemy model). Fathom has no such table yet.
Replace with a `typing.Protocol` `SourceRecord` (`id: int`, `tool_name: str`, `is_error: bool`,
`result: Mapping[str, Any]`) in `checker.py`. Any future stored-source row (Phase 3) satisfies it
without the checker importing the DB. Tests keep the old `_FakeTrace` as a frozen dataclass.

## Docstrings
Keep the reasoning (scoping by run = cross-study check; per-occurrence self-reference;
whole-word unit match; prediction hint is message-only). Drop references to things left behind
(`render_verdict`, mandatory caveats, Stage numbers, `TIER_SEARCH_BURDEN`), and say where it came
from (old file + hash) in the module docstring.

## Left behind (as the plan lists)
`render_verdict`, `_verdict_prompt`, `_structural_allowlist`, `mandatory_caveats`,
`decide_status`, `evaluate_windows`, `_metric_from`, `_fails_bar`, `corrected_threshold`,
`TIER_SEARCH_BURDEN`, `MIN_TRADES_FOR_CONFIRMATION`, `BASE_ALPHA`, `MAX_VERDICT_ATTEMPTS`,
`VerdictValidationError`, `WindowEvaluation`, `GateResult`.

## NaN
`_fails_bar` isn't ported at all, so its NaN-as-not-falsified bug can't come over. In what does
come over, `_close` fails closed on NaN (`abs(nan - x) <= tol` is False). Two new tests lock
that in: a claim with value NaN is rejected; a trace that recorded NaN rejects any claim on it.
(`_NUMBER_RE` can't match "nan"/"inf" in prose, so the scan is unaffected.)

## Test mapping (33 in old `test_verdict.py`)
- Ported, 6 `validate_claims`: matching_validates, dangling_reference, value_does_not_match,
  metric_absent, another_studys_trace, errored_trace.
- Ported, 12 scan: fabricated_number_in_prose, claimed_numbers_pass, structural_numbers_pass,
  rounding_tolerated, echoing_hypothesis_name, fabricated_number_sharing_name_digit,
  same_first_letter_word, longer_word_starting_with_unit_word, capitalized_self_reference,
  prediction_hint, hint_omitted_without_condition, hint_not_on_number_absent_from_prediction.
- Left behind, 15: 10 `decide_status`/scope (real_walk_forward_rejected, narrowing_gate1,
  scope_alone, mean_aggregate, in_sample_never_decisive, thin_downgrades, thin_never_rescues,
  deep_sample_confirms, failing_control_rejects, missing_oos_inconclusive), 3 threshold/burden,
  2 caveats.
- `_real_traces()` was built from `_REAL_WALK_FORWARD` (`WindowEvaluation`, left behind). It
  becomes a literal list of the same 8 traces (ids 101–108, same values), with the provenance
  comment kept.
- This mapping goes in the commit message, with `73ae58e`.

## Steps after approval
1. `uv sync` in the worktree (not run yet: plan mode blocks writes; `.venv` doesn't exist).
2. Write `tests/fact_check/test_checker.py` first, run it, show it failing on import.
3. Write `src/fact_check/`, run `uv run pytest tests/fact_check -v`, then `make lint`.
4. Run the code-reviewer agent on the diff; show files and results; stop. No commit until told.

## Verification
- `uv run pytest tests/fact_check -v`: 20 passed, no DB fixture used (unverified until run:
  whether the root conftest's import of `api.main`/`core.config` needs `.env` in a fresh worktree).
- `make lint` clean (it also runs web lint/typecheck; needs `web/node_modules`. If missing,
  report and run the ruff half only).
- `grep -rn "sqlalchemy\|core\.db\|agentic_core" src/fact_check` returns nothing.
