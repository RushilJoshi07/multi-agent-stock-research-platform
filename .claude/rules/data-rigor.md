# Data rigor

Applies to: price pipeline, EDGAR, Finnhub, Alpaca clients, the database, "as of" queries.
Adapted from the old project's `data-pipeline.md`.

## Agents read the database, never the network
Only ingestion jobs and the source clients talk to yfinance, EDGAR, Finnhub or Alpaca.
Agents read stored rows through read-only tools. Reasons: reproducibility (the same run
twice sees the same data), speed, and an audit trail for every number (Sacred Gate 2).
Live Alpaca quotes are the one exception, and they are stored with a fetch time before use.

## Every row records when it became known
- Every stored row has `fetched_at`.
- Rows from a source with its own availability time keep it too: EDGAR filing date (not the
  fiscal period end), Finnhub publish time.
- "As of" queries filter on the availability time, so a decision at time T never sees a
  filing filed after T, even if it describes an earlier quarter. This is Sacred Gate 1 for data.

## Corporate actions
Splits and dividends change adjusted prices retroactively. Store both raw and adjusted
prices, re-fetch affected tickers when an action appears, and log every change.

## Missing is missing
If a source fails, times out, or has no data, store and report that. Never fill, interpolate
or carry forward a value unless a rule file explicitly says so for that field.

## External sources
- Each client has rate limiting, caching and retries with backoff.
- SEC EDGAR requests send `SEC_EDGAR_USER_AGENT` (a contact email is required by the SEC).
- Free tiers have limits (e.g. Finnhub news covers about a year). Record the gap; don't hide it.

## Known data limits (disclose, don't hide)
- Survivorship bias: the S&P 500 list is today's members. Results that use it say so.
- Ticker identity: a renamed or merged company can carry a predecessor's history under the
  current ticker (seen with PSKY in the old project). Disclose; investigate only when a result
  looks anomalous.
- Universe selection is point-in-time: never pick stocks using data from after the decision time.
- Thresholds are relative (e.g. lowest volatility quintile in the sector), never hand-picked numbers.
