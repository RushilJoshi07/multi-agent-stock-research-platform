# Agent honesty

Applies to: LangGraph orchestration, every LLM call, analyst/debate/trader outputs, the fact check.
Adapted from the old project's `agent-honesty.md`.

## Sacred Gate 2: no invented numbers
Every number in a report references a stored source (a table row or a recorded tool call).
The fact check is code: it walks every number and rejects any that doesn't match its source.
A planted wrong number must be caught; this is tested, not hoped for in a prompt.

## Sacred Gate 3: code acts
Agents read and argue; code decides, sizes and places trades. No LLM output places, sizes or
approves a trade. The trader's output is a proposal; the risk rules and the portfolio manager
(plain code) accept, resize or reject it.

## LLMs never compute
An agent never calculates a ratio, return or statistic itself. Numbers come from tools
(deterministic code) and stored rows. If an agent is making a quantitative call "by judgment",
that is a bug.

## Every structured output is validated
Pydantic validates every structured output. On failure, retry with the validation error fed
back (the old project's retry-with-feedback pattern), up to a fixed limit, then fail visibly.
Nothing unvalidated reaches the next step.

## No lookahead, structurally
Agents get tools bound to the decision time. They cannot query past it. Don't ask the model
not to peek; make peeking impossible.

## Missing data
When a source is unavailable, the agent is told so explicitly and the report says
"unavailable". The agent never guesses to fill the gap.

## Guardrails
- Analysts have read-only tools; they can only call tools that exist.
- Each run has a step, time and cost budget (Phase 3 measures the real numbers).
- Everything an agent saw is stored in the decision log.
- LLMs are agreeable. The bull/bear debate exists to counter that, and the final accept/reject
  is mechanical, not a model's opinion of its own work.
