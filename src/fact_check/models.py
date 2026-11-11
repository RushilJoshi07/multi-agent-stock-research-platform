"""The two small models the number checker uses.

Plain copies of `Claim` and `FalsificationCondition` from the old project's
src/agentic_core/schemas.py at 73ae58e. Copied rather than imported so nothing here pulls in the
old schemas module, which imports StrategyRule and through it pandas-ta.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, model_validator


class FalsificationCondition(BaseModel):
    """A hypothesis's pre-registered bar, written before any testing. Single-clause on purpose:
    a compound condition is the kind of thing that can quietly grow wiggle room later.

    The metric names are the old backtest and significance result field names, so the condition
    can be checked mechanically against a stored result with no name mismatch.
    """

    metric: Literal[
        "sharpe_ratio",
        "annual_return_pct",
        "total_return_pct",
        "max_drawdown_pct",
        "win_rate_pct",
        "p_value",
    ]
    comparison: Literal["less_than", "greater_than"]
    threshold: float

    @model_validator(mode="after")
    def _check_p_value_range(self) -> FalsificationCondition:
        if self.metric == "p_value" and not (0.0 <= self.threshold <= 1.0):
            raise ValueError(f"p_value threshold must be in [0, 1], got {self.threshold}")
        return self


class Claim(BaseModel):
    """One quantitative statement, bound to the tool call that produced it.

    `metric` is what makes the check exact. Without it, checking `value` would mean matching
    against any numeric field in the referenced trace, so a claim about sharpe_ratio could
    validate against a p_value that happened to be numerically close.
    """

    statement: str
    tool_call_trace_id: int
    metric: str
    value: float
