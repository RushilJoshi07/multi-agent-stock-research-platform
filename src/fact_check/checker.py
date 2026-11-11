"""The number checker: Sacred Gate 2 (no invented numbers), in code.

Extracted from the old project's src/agentic_core/verdict.py at 73ae58e: `validate_claims`,
`scan_for_unreferenced_numbers` and their helpers, with the same logic and tolerances. The
verdict flow around them (status decision, prompts, caveats, database writes) was left behind.

Two checks, because each alone leaves a hole:

1. `validate_claims`: every claim cites a stored tool call, and its number must match what that
   call recorded.
2. `scan_for_unreferenced_numbers`: every number in the prose must match a claim or a value the
   caller allows. Without this, a model could keep its claims list clean and still write an
   invented number into the text.

Both return a list of human-readable errors; an empty list means everything checked out.
"""

from __future__ import annotations

import math
import numbers
import re
from collections.abc import Iterable, Mapping
from typing import Any, Protocol

from fact_check.models import Claim, FalsificationCondition

# Tolerance for matching a claimed number against its source. Generous enough that a model
# rounding 0.6519 to 0.65 still validates, tight enough that a different number does not.
# NaN never matches anything (every comparison with NaN is False), so it fails closed.
_REL_TOLERANCE = 0.01
_ABS_TOLERANCE = 0.01

# A number in prose. The integer part is either comma-grouped thousands ("1,234,567", only
# when every group has exactly three digits and no digit follows) or plain digits; ".65" with
# no integer part is also a number. A comma that isn't a valid grouping ("1,2,3", "1,2345")
# splits the text into separate numbers, as before.
_NUMBER_RE = re.compile(
    r"[-+]?"
    r"(?:(?:\d{1,3}(?:,\d{3})+(?!\d)|\d+)(?:\.\d+)?|\.\d+)"
    r"(?:[eE][-+]?\d+)?"
)


def _to_float(token: str) -> float:
    return float(token.replace(",", ""))


# Characters a writer (or model) may use as a minus sign. _NUMBER_RE only knows ASCII "-", so
# "−0.941" (U+2212) would be read as 0.941 and match a claim of +0.941: a flipped sign passing.
# Each is mapped one-for-one to "-" before parsing, so match positions don't shift. Fails closed:
# an en dash used as a range ("2019–2021") now reads as -2021, as an ASCII hyphen always did.
_MINUS_LIKE = str.maketrans(
    {
        "−": "-",  # minus sign
        "‒": "-",  # figure dash
        "–": "-",  # en dash
        "—": "-",  # em dash
        "﹣": "-",  # small hyphen-minus
        "－": "-",  # fullwidth hyphen-minus
    }
)

# A hypothesis name often embeds a digit as a unit abbreviation ("52W_High_Proximity_Momentum"),
# and the model naturally echoes it in prose ("the 52-week-high strategy"). That "52" refers to
# the name, not a new number, and must not be flagged; a fabricated "52% win rate" must be.
_NAME_DIGIT_LETTER_RE = re.compile(r"(\d+(?:\.\d+)?)([A-Za-z])")
_SELF_REFERENCE_GAP_RE = re.compile(r"^[\s-]{0,2}")

# Matching the first letter alone is not enough: "52 winning trades" also starts with "w". The
# word after the number must be one of these time-unit words. Extend only when a real hypothesis
# name uses a period word not listed here.
_TIME_UNIT_WORDS = {
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "quarter",
    "quarters",
    "year",
    "years",
}
_WORD_RE = re.compile(r"[a-z]+")


class SourceRecord(Protocol):
    """A stored tool call a claim can cite. Any object with these attributes works, so the
    checker never imports the database layer."""

    @property
    def id(self) -> int: ...
    @property
    def tool_name(self) -> str: ...
    @property
    def is_error(self) -> bool: ...
    @property
    def result(self) -> Mapping[str, Any]: ...


def _self_reference_digit_letters(hypothesis_name: str) -> dict[float, str]:
    """Map each digit run in the name that is directly followed by a letter to that letter,
    lowercased: {52.0: 'w'} for "52W_High...".

    The letter is not expanded into a word ("w" -> "week"); an abbreviation table would miss any
    unit nobody anticipated. `_is_self_reference` does the matching instead.
    """
    return {
        float(m.group(1)): m.group(2).lower()
        for m in _NAME_DIGIT_LETTER_RE.finditer(hypothesis_name)
    }


def _is_self_reference(narrative: str, position: int, letter: str) -> bool:
    """True if the text right after a number (skipping up to two spaces or hyphens: "52-week",
    "52 week") is a time-unit word starting with the same letter that follows the number in
    the hypothesis name ("52W" -> "w").

    Both conditions are required: "52%" and "52 million" fail on the letter; "52 winning
    trades" fails because "winning" isn't a time-unit word.

    It is a whole-word match: `_WORD_RE` is greedy, so it captures "weekend" or "weeklong"
    whole, and neither is in `_TIME_UNIT_WORDS`. The tail is lowercased first, so "52-Week"
    still matches.
    """
    tail = narrative[position : position + 16].lower()
    gap = _SELF_REFERENCE_GAP_RE.match(tail)
    rest = tail[gap.end() :] if gap else tail
    word_match = _WORD_RE.match(rest)
    word = word_match.group(0) if word_match else ""
    return word in _TIME_UNIT_WORDS and word.startswith(letter)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(_ABS_TOLERANCE, _REL_TOLERANCE * abs(b))


def validate_claims(claims: Iterable[Claim], traces: Iterable[SourceRecord]) -> list[str]:
    """Check every claim against the stored tool call it cites.

    Pass only the traces of the run being checked. The lookup is built from those alone, so a
    claim citing a real trace id from a different run resolves to nothing and is rejected.
    Without that scoping, a model could support a claim with another run's evidence.
    """
    by_id = {t.id: t for t in traces}
    errors = []
    for i, claim in enumerate(claims):
        trace = by_id.get(claim.tool_call_trace_id)
        if trace is None:
            errors.append(
                f"claim {i} references tool_call_trace_id={claim.tool_call_trace_id}, "
                "which does not exist in this study run"
            )
            continue
        if trace.is_error:
            errors.append(f"claim {i} references trace {trace.id}, which recorded an error")
            continue
        if not isinstance(trace.result, Mapping):
            errors.append(
                f"claim {i} references trace {trace.id}, which has no result to check against"
            )
            continue
        if claim.metric not in trace.result:
            errors.append(
                f"claim {i} cites metric {claim.metric!r}, absent from trace {trace.id} "
                f"({trace.tool_name})"
            )
            continue
        actual = trace.result[claim.metric]
        if actual is None:
            errors.append(
                f"claim {i} cites metric {claim.metric!r}, but trace {trace.id} recorded "
                "no value (null) for it"
            )
            continue
        # bool is a subclass of int in Python, so True would otherwise count as 1.0.
        if isinstance(actual, bool) or not isinstance(actual, numbers.Real):
            errors.append(
                f"claim {i} cites metric {claim.metric!r}, but trace {trace.id} recorded "
                f"{actual!r} ({type(actual).__name__}), which is not a number"
            )
            continue
        if not math.isfinite(actual):
            errors.append(
                f"claim {i} cites metric {claim.metric!r}, but trace {trace.id} recorded "
                f"{actual}, which is not a finite number"
            )
            continue
        if not _close(claim.value, float(actual)):
            errors.append(
                f"claim {i} states {claim.metric}={claim.value}, but trace {trace.id} "
                f"recorded {actual}"
            )
    return errors


def scan_for_unreferenced_numbers(
    narrative: str,
    claims: Iterable[Claim],
    allowed: set[float],
    hypothesis_name: str = "",
    prediction: str = "",
    condition: FalsificationCondition | None = None,
) -> list[str]:
    """Flag every number in the narrative that matches nothing it is allowed to match.

    A number passes if it matches (within tolerance) a claim's value, a value in `allowed`
    (structural numbers the caller chooses: window count, the threshold, and so on), or is a
    self-reference to a digit in the hypothesis's own name (see `_is_self_reference`). The
    self-reference check is per occurrence, so a legitimate "52-week" never clears a fabricated
    "52%" elsewhere in the same text.

    Scan only text the model wrote. Text the code generates itself would just be checking the
    code's own output against itself.

    `prediction` and `condition` only change the message. If an orphaned number also appears in
    the hypothesis's pre-testing prediction, and a condition is given, the error names the real
    pre-registered bar. A real run in the old project cited the prediction's informal "> 0.5"
    as the threshold when the bar was 0.0. The number is rejected either way.
    """
    narrative = narrative.translate(_MINUS_LIKE)
    prediction = prediction.translate(_MINUS_LIKE)
    claimed = [c.value for c in claims]
    self_ref_letters = _self_reference_digit_letters(hypothesis_name)
    prediction_numbers = {_to_float(m.group(0)) for m in _NUMBER_RE.finditer(prediction)}
    orphan_from_prediction: dict[str, bool] = {}
    for match in _NUMBER_RE.finditer(narrative):
        token = match.group(0)
        value = _to_float(token)
        if any(_close(value, c) for c in claimed):
            continue
        if any(_close(value, a) for a in allowed):
            continue
        letter = self_ref_letters.get(value)
        if letter is not None and _is_self_reference(narrative, match.end(), letter):
            continue
        orphan_from_prediction[token] = orphan_from_prediction.get(token, False) or any(
            _close(value, p) for p in prediction_numbers
        )

    errors = []
    for token in sorted(orphan_from_prediction):
        msg = f"narrative contains {token!r}, which matches no validated claim"
        if orphan_from_prediction[token] and condition is not None:
            msg += (
                f" -- note: this number appears in the hypothesis's own pre-testing "
                f"prediction, not the pre-registered falsification bar ({condition.metric} "
                f"{condition.comparison} {condition.threshold}); do not cite it as the "
                "'required threshold' or 'the bar'"
            )
        errors.append(msg)
    return errors
