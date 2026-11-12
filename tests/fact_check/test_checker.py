"""Tests for the number checker (Sacred Gate 2).

Ported from the old project's tests/agentic_core/test_verdict.py at 73ae58e: the 18 tests that
exercise validate_claims and scan_for_unreferenced_numbers. The 15 tests of the verdict logic
left behind (decide_status, the significance threshold, the mandatory caveats) were not ported.
The two NaN tests at the end are new.

Pure tests: no database, no network.
"""

import math
from dataclasses import dataclass, field
from typing import Any

from fact_check import (
    Claim,
    FalsificationCondition,
    scan_for_unreferenced_numbers,
    validate_claims,
)


@dataclass(frozen=True)
class _FakeTrace:
    id: int
    tool_name: str
    result: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False


# Real numbers from the old project's database: the walk-forward run of the
# LowVol_AAPL_ATR_MeanReversion hypothesis (study design a27b937b-8ab0-4b9e-abc1-0172b0dffb71),
# run against cached AAPL data on 2026-08-23. Window 0 is in-sample; windows 1-3 are the
# out-of-sample folds. Each window has a backtest trace and a significance trace.
# (window, backtest id, significance id, sharpe_ratio, num_trades, p_value)
_REAL_WINDOWS = [
    (0, 101, 102, 0.771, 73, 0.432),
    (1, 103, 104, -1.510, 4, 1.000),
    (2, 105, 106, 0.545, 6, 0.794),
    (3, 107, 108, 0.941, 7, 0.312),
]


def _real_traces() -> list[_FakeTrace]:
    out = []
    for _, bt_id, sig_id, sharpe, trades, p in _REAL_WINDOWS:
        out.append(
            _FakeTrace(bt_id, "run_backtest", {"sharpe_ratio": sharpe, "num_trades": trades})
        )
        out.append(
            _FakeTrace(sig_id, "test_significance", {"p_value": p, "observed_sharpe": sharpe})
        )
    return out


_NAME_52W = "52W_High_Proximity_Momentum_NVDA_MSFT"


def _sharpe_claim() -> list[Claim]:
    return [
        Claim(
            statement="sharpe was -0.13", tool_call_trace_id=15, metric="sharpe_ratio", value=-0.13
        )
    ]


# ---------------------------------------------------------------------------
# validate_claims: five ways to try to fabricate
# ---------------------------------------------------------------------------


def test_a_claim_matching_its_trace_validates():
    claims = [
        Claim(
            statement="in-sample sharpe was 0.771",
            tool_call_trace_id=101,
            metric="sharpe_ratio",
            value=0.771,
        )
    ]
    assert validate_claims(claims, _real_traces()) == []


def test_a_claim_with_a_dangling_reference_is_rejected():
    claims = [
        Claim(
            statement="sharpe was 0.771", tool_call_trace_id=999, metric="sharpe_ratio", value=0.771
        )
    ]
    errors = validate_claims(claims, _real_traces())
    assert errors and "does not exist" in errors[0]


def test_a_claim_whose_value_does_not_match_its_trace_is_rejected():
    """The core fabrication case: a real reference, a real metric, an invented number."""
    claims = [
        Claim(statement="sharpe was 2.5", tool_call_trace_id=101, metric="sharpe_ratio", value=2.5)
    ]
    errors = validate_claims(claims, _real_traces())
    assert errors and "recorded" in errors[0]


def test_a_claim_citing_a_metric_absent_from_its_trace_is_rejected():
    """Why Claim carries `metric`: without it, a sharpe claim could validate against a p_value
    that happened to be close."""
    claims = [Claim(statement="p was 0.771", tool_call_trace_id=101, metric="p_value", value=0.771)]
    errors = validate_claims(claims, _real_traces())
    assert errors and "absent from trace" in errors[0]


def test_a_claim_referencing_another_studys_trace_is_rejected():
    """Only the given run's traces count, so a real trace id from another run resolves to
    nothing."""
    other_study = [_FakeTrace(777, "run_backtest", {"sharpe_ratio": 3.0, "num_trades": 400})]
    claims = [
        Claim(statement="sharpe was 3.0", tool_call_trace_id=777, metric="sharpe_ratio", value=3.0)
    ]
    assert validate_claims(claims, other_study) == []  # valid in its own run
    errors = validate_claims(claims, _real_traces())  # not in this one
    assert errors and "does not exist" in errors[0]


def test_a_claim_referencing_an_errored_trace_is_rejected():
    traces = [_FakeTrace(200, "run_backtest", {"error": "boom"}, is_error=True)]
    claims = [
        Claim(statement="sharpe was 1.0", tool_call_trace_id=200, metric="sharpe_ratio", value=1.0)
    ]
    errors = validate_claims(claims, traces)
    assert errors and "recorded an error" in errors[0]


# ---------------------------------------------------------------------------
# scan_for_unreferenced_numbers: the hole validate_claims alone leaves open
# ---------------------------------------------------------------------------


def test_a_fabricated_number_in_the_prose_is_caught_despite_clean_claims():
    claims = [
        Claim(
            statement="sharpe was 0.771", tool_call_trace_id=101, metric="sharpe_ratio", value=0.771
        )
    ]
    narrative = "In-sample sharpe was 0.771, and the strategy returned 42.7% annually."
    orphans = scan_for_unreferenced_numbers(narrative, claims, allowed=set())
    assert any("42.7" in o for o in orphans)


def test_claimed_numbers_pass_the_scan():
    claims = [
        Claim(
            statement="sharpe was 0.771", tool_call_trace_id=101, metric="sharpe_ratio", value=0.771
        )
    ]
    assert scan_for_unreferenced_numbers("Sharpe was 0.771.", claims, allowed=set()) == []


def test_structural_numbers_pass_the_scan():
    assert (
        scan_for_unreferenced_numbers("This is hypothesis 1 of 4 windows.", [], allowed={1.0, 4.0})
        == []
    )


def test_rounding_is_tolerated_but_a_different_number_is_not():
    claims = [
        Claim(statement="sharpe", tool_call_trace_id=101, metric="sharpe_ratio", value=0.6519)
    ]
    assert scan_for_unreferenced_numbers("Sharpe was 0.65.", claims, allowed=set()) == []
    assert scan_for_unreferenced_numbers("Sharpe was 0.85.", claims, allowed=set()) != []


def test_narrative_echoing_the_hypothesis_name_is_not_flagged():
    """Found live in the old project: "52" in "the 52-week-high strategy" echoes the name
    52W_High_..., not a new number needing a source."""
    narrative = "The 52-week-high proximity momentum strategy failed, with a Sharpe of -0.13."
    orphans = scan_for_unreferenced_numbers(
        narrative, _sharpe_claim(), allowed=set(), hypothesis_name=_NAME_52W
    )
    assert orphans == []


def test_a_fabricated_number_sharing_the_hypothesis_name_digit_is_still_caught():
    """The self-reference exemption is per occurrence: a fabricated "52%" elsewhere is flagged."""
    narrative = "The 52-week-high proximity strategy failed, despite a fabricated 52% win rate."
    orphans = scan_for_unreferenced_numbers(
        narrative, _sharpe_claim(), allowed=set(), hypothesis_name=_NAME_52W
    )
    assert any("52" in o for o in orphans)


def test_a_same_first_letter_word_does_not_count_as_a_self_reference():
    """ "winning" starts with the same "w" as "52W" but isn't a time-unit word."""
    narrative = "The strategy closed 52 winning trades, with a Sharpe of -0.13."
    orphans = scan_for_unreferenced_numbers(
        narrative, _sharpe_claim(), allowed=set(), hypothesis_name=_NAME_52W
    )
    assert any("52" in o for o in orphans)


def test_a_number_followed_by_a_longer_word_starting_with_a_unit_word_is_not_a_self_reference():
    """ "weekend" and "weeklong" start with "week"; the match is on the whole word."""
    narrative = (
        "The strategy gained 52 weekend momentum and a fabricated 52weeklong "
        "rally, with a real Sharpe of -0.13."
    )
    orphans = scan_for_unreferenced_numbers(
        narrative, _sharpe_claim(), allowed=set(), hypothesis_name=_NAME_52W
    )
    assert any("52" in o for o in orphans)


def test_a_capitalized_self_reference_is_still_recognized():
    narrative = "52-Week-high proximity failed early. Sharpe was -0.13."
    orphans = scan_for_unreferenced_numbers(
        narrative, _sharpe_claim(), allowed=set(), hypothesis_name=_NAME_52W
    )
    assert orphans == []


def test_a_number_echoing_the_prediction_as_the_bar_gets_a_diagnostic_hint():
    """Found live in the old project: the model called the prediction's informal "> 0.5" the
    required threshold when the real bar was sharpe_ratio less_than 0.0. Still rejected; the
    message names the real bar."""
    claims = [
        Claim(statement="oos sharpe", tool_call_trace_id=9, metric="sharpe_ratio", value=0.1527)
    ]
    narrative = (
        "The out-of-sample Sharpe collapsed to 0.1527, well below the required threshold of 0.5."
    )
    condition = FalsificationCondition(metric="sharpe_ratio", comparison="less_than", threshold=0.0)
    errors = scan_for_unreferenced_numbers(
        narrative,
        claims,
        allowed={0.0},
        prediction="will produce a positive Sharpe ratio (> 0.5) out-of-sample",
        condition=condition,
    )
    assert len(errors) == 1
    assert "0.5" in errors[0]
    assert "pre-testing prediction" in errors[0]
    assert "sharpe_ratio less_than 0.0" in errors[0]


def test_the_hint_is_omitted_when_no_condition_is_given():
    claims: list[Claim] = []
    narrative = "The strategy returned a Sharpe of 0.5, matching nothing on file."
    errors = scan_for_unreferenced_numbers(
        narrative, claims, allowed=set(), prediction="will beat a Sharpe of 0.5"
    )
    assert errors == ["narrative contains '0.5', which matches no validated claim"]


def test_the_hint_does_not_attach_to_a_number_absent_from_the_prediction():
    claims: list[Claim] = []
    condition = FalsificationCondition(metric="sharpe_ratio", comparison="less_than", threshold=0.0)
    narrative = "The strategy posted a fabricated 42.7% annual return."
    errors = scan_for_unreferenced_numbers(
        narrative,
        claims,
        allowed=set(),
        prediction="will produce a positive Sharpe ratio (> 0.5) out-of-sample",
        condition=condition,
    )
    assert len(errors) == 1
    assert "42.7" in errors[0]
    assert "pre-testing prediction" not in errors[0]


# ---------------------------------------------------------------------------
# New: NaN fails closed (the old _fails_bar treated NaN as "not falsified"; not carried over)
# ---------------------------------------------------------------------------


def test_a_nan_claim_value_is_rejected():
    claims = [
        Claim(statement="sharpe", tool_call_trace_id=101, metric="sharpe_ratio", value=math.nan)
    ]
    errors = validate_claims(claims, _real_traces())
    assert len(errors) == 1 and "recorded 0.771" in errors[0]


def test_a_trace_that_recorded_nan_rejects_any_claim_on_it():
    traces = [_FakeTrace(300, "run_backtest", {"sharpe_ratio": math.nan})]
    for value in (0.0, 1.0, math.nan):
        claims = [
            Claim(statement="sharpe", tool_call_trace_id=300, metric="sharpe_ratio", value=value)
        ]
        errors = validate_claims(claims, traces)
        assert len(errors) == 1 and "recorded nan" in errors[0]


# ---------------------------------------------------------------------------
# Sign: a non-ASCII minus or dash must not be dropped (that would flip the sign)
# ---------------------------------------------------------------------------

_MINUS_LIKE = {
    "minus sign U+2212": "−",
    "en dash U+2013": "–",
    "em dash U+2014": "—",
    "figure dash U+2012": "‒",
    "small hyphen-minus U+FE63": "﹣",
    "fullwidth hyphen-minus U+FF0D": "－",
}


def test_a_non_ascii_minus_does_not_flip_the_sign():
    claims = [
        Claim(statement="oos sharpe", tool_call_trace_id=107, metric="sharpe_ratio", value=0.941)
    ]
    for name, dash in _MINUS_LIKE.items():
        orphans = scan_for_unreferenced_numbers(f"Sharpe of {dash}0.941.", claims, allowed=set())
        assert orphans == ["narrative contains '-0.941', which matches no validated claim"], name


def test_a_non_ascii_minus_on_a_negative_claim_matches_it():
    claims = [
        Claim(statement="oos sharpe", tool_call_trace_id=103, metric="sharpe_ratio", value=-1.51)
    ]
    for name, dash in _MINUS_LIKE.items():
        assert scan_for_unreferenced_numbers(f"Sharpe of {dash}1.51.", claims, set()) == [], name


# ---------------------------------------------------------------------------
# Unusual stored values: rejected with a correct message, never a crash or a silent 1.0
# ---------------------------------------------------------------------------


def _claim_on(value: float = 1.0) -> list[Claim]:
    return [Claim(statement="x", tool_call_trace_id=400, metric="sharpe_ratio", value=value)]


def _errors_for_stored(stored: Any) -> list[str]:
    return validate_claims(_claim_on(), [_FakeTrace(400, "run_backtest", {"sharpe_ratio": stored})])


def test_a_stored_string_is_rejected_not_a_crash():
    for stored in ("abc", "1.0"):
        errors = _errors_for_stored(stored)
        assert errors == [
            f"claim 0 cites metric 'sharpe_ratio', but trace 400 recorded {stored!r} "
            "(str), which is not a number"
        ]


def test_a_stored_boolean_is_rejected_not_counted_as_one():
    errors = _errors_for_stored(True)
    assert errors == [
        "claim 0 cites metric 'sharpe_ratio', but trace 400 recorded True (bool), "
        "which is not a number"
    ]


def test_a_stored_list_or_dict_is_rejected_not_a_crash():
    for stored in ([1.0], {"v": 1.0}):
        errors = _errors_for_stored(stored)
        assert len(errors) == 1 and "which is not a number" in errors[0]


def test_a_stored_null_says_null_not_absent():
    """A no-trades backtest stores sharpe_ratio=None (Phase 1 step 6b). The metric is present
    with no value, which is different from a metric the trace never had."""
    errors = _errors_for_stored(None)
    assert errors == [
        "claim 0 cites metric 'sharpe_ratio', but trace 400 recorded no value (null) for it"
    ]


def test_a_stored_infinity_is_rejected():
    for stored in (math.inf, -math.inf):
        errors = validate_claims(
            _claim_on(stored), [_FakeTrace(400, "run_backtest", {"sharpe_ratio": stored})]
        )
        assert len(errors) == 1 and "not a finite number" in errors[0]


def test_a_trace_with_no_result_is_rejected_not_a_crash():
    trace = _FakeTrace(400, "run_backtest", None)  # type: ignore[arg-type]
    errors = validate_claims(_claim_on(), [trace])
    assert errors == ["claim 0 references trace 400, which has no result to check against"]


def test_a_stored_integer_still_validates():
    assert _errors_for_stored(1) == []


# ---------------------------------------------------------------------------
# Number parsing: ".65" is 0.65, "1,234" is one number
# ---------------------------------------------------------------------------


def test_a_leading_decimal_point_reads_as_a_fraction():
    claims = [
        Claim(statement="sharpe", tool_call_trace_id=101, metric="sharpe_ratio", value=0.6519)
    ]
    assert scan_for_unreferenced_numbers("Sharpe was .65.", claims, allowed=set()) == []
    assert scan_for_unreferenced_numbers("Sharpe was .85.", claims, allowed=set()) == [
        "narrative contains '.85', which matches no validated claim"
    ]
    assert scan_for_unreferenced_numbers("Sharpe was -.65.", claims, allowed=set()) == [
        "narrative contains '-.65', which matches no validated claim"
    ]


def test_a_thousands_separator_reads_as_one_number():
    claims = [Claim(statement="trades", tool_call_trace_id=101, metric="num_trades", value=1234)]
    assert scan_for_unreferenced_numbers("It made 1,234 trades.", claims, allowed=set()) == []
    assert scan_for_unreferenced_numbers("It made 1,234 trades.", [], allowed=set()) == [
        "narrative contains '1,234', which matches no validated claim"
    ]
    assert scan_for_unreferenced_numbers("Equity hit 1,234,567.5 dollars.", [], {1234567.5}) == []


def test_commas_that_are_not_thousands_groups_still_split():
    """ "1,2,3" is a list, and "1,2345" is not a valid grouping, so neither becomes one number."""
    assert scan_for_unreferenced_numbers("Windows 1,2,3 failed.", [], {1.0, 2.0, 3.0}) == []
    assert scan_for_unreferenced_numbers("Values 1,2345.", [], {1.0, 2345.0}) == []


# ---------------------------------------------------------------------------
# A structured claim must equal its stored value exactly (float noise only, rel 1e-9)
# ---------------------------------------------------------------------------


def _claim_vs_stored(metric: str, claimed: float, stored: float) -> list[str]:
    claims = [Claim(statement="x", tool_call_trace_id=500, metric=metric, value=claimed)]
    return validate_claims(claims, [_FakeTrace(500, "test_significance", {metric: stored})])


def test_a_rounded_claim_is_rejected():
    assert _claim_vs_stored("sharpe_ratio", 0.77, 0.771) != []
    assert _claim_vs_stored("sharpe_ratio", 0.65, 0.6519) != []


def test_a_p_value_cannot_cross_the_line_within_the_old_tolerance():
    """Under the old flat 0.01 tolerance both of these passed."""
    assert _claim_vs_stored("p_value", 0.045, 0.054) != []
    assert _claim_vs_stored("p_value", 0.001, 0.009) != []


def test_float_noise_is_not_a_mismatch():
    assert _claim_vs_stored("total_return_pct", 0.3, 0.1 + 0.2) == []
    assert _claim_vs_stored("total_return_pct", 0.0, 0.0) == []
    assert _claim_vs_stored("sharpe_ratio", 1.0, 1.0 + 1e-12) == []
    assert _claim_vs_stored("sharpe_ratio", 1.0, 1.0 + 1e-6) != []


# ---------------------------------------------------------------------------
# A minus followed by one space: a sign, unless it's subtraction or a list bullet
# ---------------------------------------------------------------------------


def _sharpe(value: float) -> list[Claim]:
    return [Claim(statement="x", tool_call_trace_id=107, metric="sharpe_ratio", value=value)]


def test_a_spaced_minus_does_not_flip_the_sign():
    for dash in ("-", "−", "–"):
        orphans = scan_for_unreferenced_numbers(f"Sharpe of {dash} 0.941.", _sharpe(0.941), set())
        assert orphans == ["narrative contains '-0.941', which matches no validated claim"], dash


def test_a_spaced_minus_on_a_negative_claim_matches_it():
    assert scan_for_unreferenced_numbers("Sharpe of - 1.51.", _sharpe(-1.51), set()) == []


def test_a_list_bullet_is_not_a_minus_sign():
    trades = [Claim(statement="x", tool_call_trace_id=101, metric="num_trades", value=52)]
    for narrative in ("- 52 trades", "Summary:\n  - 52 trades\n- 52 trades again"):
        assert scan_for_unreferenced_numbers(narrative, trades, set()) == [], narrative


def test_subtraction_is_not_a_negative_number():
    assert scan_for_unreferenced_numbers("3 - 0.941", _sharpe(0.941), {3.0}) == []
