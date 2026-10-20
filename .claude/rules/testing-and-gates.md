# Testing and gates

Applies to: all tests, phase gates, CI.

## Real data, not mocks, on data paths
- Database code is tested against real Postgres (`fathom_test`), not mocks or SQLite.
- External sources are tested with stored real responses (fixtures captured from the real API),
  plus a `live` test that hits the real API, run only when asked.
- "Done" means it ran against real data and the output was checked, not just that tests pass.

## Markers
- `live`: calls a real external API (Bedrock, Finnhub, Alpaca, EDGAR, yfinance, LangSmith).
  Never in CI. Ask before running any that cost money.
- `gate`: a phase gate test in `tests/gates/`. Run with `make gate PHASE=N`.
- The default `make test` excludes both.

## No network in CI
CI has no secrets and runs pytest with pytest-socket (`--disable-socket`, localhost only).
An accidental outbound call fails the test instead of spending money.

## Phase gates
- Each phase's "Done when" becomes a test in `tests/gates/` wherever possible, plus a written
  walkthrough for what can't be automated.
- A gate test must be able to fail: include at least one check that proves the thing isn't
  hard-coded to pass (e.g. stop Redis and the health check goes red).
- The next phase starts only after the gate passes and the result, date and evidence (raw
  output) are recorded in `docs/STATUS.md`.

## Golden set
After any agent or prompt change, re-run the golden set (the fixed known cases) and compare
scores with the last recorded run.

## Bug fixes
Write the failing test first, show it failing, then fix.
