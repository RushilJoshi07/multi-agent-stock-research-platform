# Phase 1 proposal: import the foundations

The "Changes from review" section overrides anything above it.

Approved 2026-10-28.

## Context
Phase 0 passed (gate 4c3aa31, handoff 46cd60c). Phase 1 brings in the old project's tested data
and math (price pipeline, S&P 500 universe, backtester, significance test, number checker),
restores the 506-ticker price history, catches it up, fixes the zero-trade crash and adds a nightly
price job. Everything else in Fathom builds on these. Nothing is written until this is approved;
after approval, one numbered step at a time, each shown and then stopped.

Stack at proposal time (`make ps`, 2026-10-28): postgres, redis, api, web all **Up 3 days
(healthy)** on 5433 / 6380 / 8001 / 5174. Not touched.

## Verified facts this proposal rests on
**Old database** (read-only sessions, `PGOPTIONS=-c default_transaction_read_only=on`,
`show default_transaction_read_only` = on):
- Homebrew `postgresql@16` 16.14, native (launchd), localhost:5432, db `strategy_research`, user
  `rushil`, 332 MB, extensions plpgsql + vector 0.8.6. Server `TimeZone` = **America/New_York**.
  Local `psql`/`pg_dump`/`pg_restore` are 16.14 too.
- Tables to restore (exact `count(*)`; sizes from `pg_total_relation_size`); 321 MB in total:

| Table | Rows | Size | Key facts |
| --- | --- | --- | --- |
| price_bars | 1,987,174 | 320 MB | PK (ticker, date); 506 tickers; 2010-01-04 → 2026-09-08; raw_/adj_ OHLC numeric(18,6), volumes bigint, fetched_at |
| corporate_actions_log | 7,686 | 832 kB | 7,404 dividends + 282 splits, 52 tickers, 1962-01-16 → 2026-08-14; serial id (`corporate_actions_log_id_seq`) |
| universe_snapshots | 503 | 120 kB | PK (snapshot_at, ticker); one snapshot, 2026-09-08 18:30:38 |
| ticker_metadata | 506 | 104 kB | PK ticker; all `listing_status = active` |
| ingestion_runs | 4 | 24 kB | 2026-07-26 → 2026-09-08, all success |
| ingestion_run_tickers | 557 | 136 kB | FK run_id → ingestion_runs; serial id; all success |

- 503 tickers end 2026-09-08. **SPY, BROS, CROX end 2026-08-17** and are not in the universe
  snapshot (leftovers from the old 54-ticker set; SPY is the benchmark).
- Left behind: corpus_papers, corpus_chunks (vector), charters, hypotheses, verdicts, study_designs,
  study_runs, tool_call_traces, scoreboard_entries, alembic_version (c9bbd7a458b1).

**Old repo** (`git status` clean, HEAD `49cc803`, 2026-09-08). Last commit per piece:
`src/data_pipeline` and `scripts/expand_universe_sp500.py` **49cc803**; `src/backtester`
**5f852d5**; `src/research_stats` **779d8bf**; `src/agentic_core/verdict.py` **73ae58e**.
Old venv: Python 3.13.7.

**Timestamp finding (affects the restore).** Old code writes UTC-aware datetimes
(`datetime.now(tz=timezone.utc)`) into `timestamp without time zone` columns on a server whose
TimeZone is America/New_York.
- Evidence that the stored values are **New York wall-clock time**: each ingestion run ends 15–35
  minutes before the related commit (run 13:28 → commit 14:02 EDT on 07-26; 20:26 → 20:41 on
  08-17; 18:44 → 19:02 on 09-08).
- The likely mechanism is that psycopg2 sends aware datetimes as `timestamptz`, which Postgres
  casts to the session zone. Unverified; step 1 tests it on `fathom_test`.
- Two consequences:
  1. The restored 2026-09-08 bars were fetched at 18:44 ET, after the close, so they are not
     partial bars.
  2. Fathom's Postgres runs in UTC, so new rows would be stored as UTC wall-clock in the same
     columns. That mix would make `fetched_at` ambiguous, which Sacred Gate 1 can't tolerate.
     The fix is in step 4.

## 1. Import order (one commit per piece, old hash in the message)

```
P1 guard ─┐
P2 log fix┤
          ├─ 1 deps ─ 2 schema+models ─ 3 restore ─ 4 timestamptz ─┬─ A: 5a pipeline ─ 6a universe ─ 7a calendar+partial-bar guard ─┐
          │                                                         └─ B: 5b backtester ─ 6b zero-trade fix ─ 7b significance ──────┤
          │                                                                                                                         ├─ 8 catch-up ─ 9 nightly ─ 10 number checker ─ 11 gate
```

| # | Piece | Depends on | Old hash | Where |
| --- | --- | --- | --- | --- |
| P1 | `DATABASE_URL` host+port guard (test first) | – | – | main |
| P2 | Commit log split into one file per commit (decision 0008) | – | – | main |
| 1 | Every Phase 1 dependency in one go (pyproject, uv.lock, cutoff moved) | – | – | main |
| 2 | Alembic, SQLAlchemy models for the 6 tables, migration 0001 reproducing the old schema exactly, shared test fixtures | 1 | 49cc803 (models.py, universe snapshot migration c9bbd7a458b1) | main |
| 3 | Restore the dump into `fathom`, compare with the old database | 2, P1 | – | main |
| 4 | Migration 0002: timestamp columns → `timestamptz`, converting via `AT TIME ZONE 'America/New_York'` (test first) | 3 | – | main |
| 5a | Price pipeline: fetch, raw/adjusted, splits/dividends, upsert, ingestion logs, CLI | 2, 4 | 49cc803 | worktree A |
| 6a | S&P 500 universe: `all_tickers()` and the snapshot CLI (Wikipedia + SSGA cross-check), as a module instead of a loose script | 5a | 49cc803 | worktree A |
| 7a | Market calendar (`src/core/market_calendar.py`) and the partial-bar guard: ingest never fetches past the last *completed* session (test first) | 5a | – | worktree A |
| 5b | Backtester (whole `src/backtester/` incl. `extended_indicators.py`, plus the two `scripts/` its tests import) | 2 (PriceBar model) | 5f852d5 | worktree B |
| 6b | **Zero-trade fix** (test first, below) | 5b | – | worktree B |
| 7b | Significance test, confidence, BH (`research_stats/`), plus `corrected_threshold` from verdict.py | 5b, 6b | 779d8bf, 73ae58e | worktree B |
| 8 | Catch-up ingest + corporate-actions check + fresh universe snapshot (a run, not code) | 3, 4, 7a | – | main |
| 9 | **Nightly price job** (section 7) | 7a | – | main |
| 10 | Number checker, extracted to `src/fact_check/` (below) | – | 73ae58e | main |
| 11 | Phase 1 gate test + run | all | – | main |

Notes on specific pieces:
- **Adaptations on import** (each named in its commit message):
  - Old `config.py` (requires `.env`, settings built at import time) and `db/session.py` (engine
    built at import time) are replaced by Fathom's `core.config` / `core.db.get_engine`.
  - `init_db.py` and its `agentic_core.db.models` import are dropped; Alembic owns the schema.
- **Zero-trade fix (6b)** comes right after the backtester import, before anything uses it.
  - Today `BacktestResult.from_stats` turns backtesting.py's empty win rate and Sharpe into
    `float('nan')` (`result.py:32-52`). JSON then turns NaN into `null`, the MCP client's schema
    check rejects that, and the run crashes.
  - Failing test first: an impossible rule (RSI < -100) on synthetic data;
    `model_validate_json(model_dump_json())` raises, or the win rate is NaN.
  - The fix:
    1. `num_trades == 0` gives `no_trades=True` with `win_rate_pct`/`sharpe_ratio` set to
       `None`.
    2. The model gets `allow_inf_nan=False`, so no NaN can slip through again. Any other NaN
       becomes `None` explicitly.
    3. `test_significance` returns a clean "no trades" result instead of raising `ValueError`,
       per the rule "too few occurrences is reported as exactly that".
- **Number checker (10)** is extracted, not copied:
  - What comes over, with only the tests that exercise these functions (the mapping from the 33
    tests in `test_verdict.py` goes in the commit message):
    - `validate_claims`, `scan_for_unreferenced_numbers` and their helpers (`_close`, the
      self-reference helpers, the regexes, the 0.01 tolerances);
    - plain copies of the two small models they use (`Claim`, `FalsificationCondition`), so
      nothing imports `agentic_core.schemas` → `StrategyRule` → pandas-ta.
  - Left behind: `render_verdict`, `_verdict_prompt`, `_structural_allowlist`,
    `mandatory_caveats`, `decide_status`/`evaluate_windows` (tied to the old hypothesis model).
  - Phase 3 note: the old `_fails_bar` treats NaN as "not falsified". That bug is not carried over.
- **`corrected_threshold` (in 7b)** comes over as `0.05 / max(1, n_tests)`. The old per-tier
  "search burden" multiplier belongs to literature grounding, which is left behind. This is a
  deliberate change and is stated in the commit message.
- **Left behind from these folders:** `data_pipeline/screener.py` (6 tests; the agent screener
  tool) and `src/mcp_tools/`. They are noted in `docs/ideas.md` for Discover / Phase 3. The
  retry-with-feedback pattern (`render_verdict`, `hypothesis.py` 0af263e) arrives in Phase 3 with
  the first LLM call.

## 2. The restore (step 3, main session only, nothing else running)
- **Old side stays read-only.**
  - pg_dump only reads, and it runs with `PGOPTIONS='-c default_transaction_read_only=on'`.
  - Nothing else connects to 5432 except the read-only `psql` comparison queries.
  - The Python guard (P1) makes it impossible for Fathom code to reach 5432 at all.
- **Dump** (data only; the schema comes from Fathom's migration 0001, so Alembic owns it):
  ```
  pg_dump -h localhost -p 5432 -d strategy_research --data-only -Fc \
    -t public.price_bars -t public.corporate_actions_log -t public.universe_snapshots \
    -t public.ticker_metadata -t public.ingestion_runs -t public.ingestion_run_tickers \
    -f data/dumps/strategy_research_price_universe_2026-10-DD.dump
  ```
  Then `pg_restore -l` on the file, which must list exactly 6 TABLE DATA entries plus the 2 owned
  SEQUENCE SET entries. Whether `-t` pulls in owned sequence values is unverified; if they're
  missing, I'll `setval` them to `max(id)` and say so. I'll also check that ingestion_runs comes
  before ingestion_run_tickers.
- **Where the dump lives:** `data/dumps/` in the main checkout. It's already ignored in
  `.gitignore` (`*.dump`, `data/dumps/`) and in `.dockerignore`, so it never enters a commit or an
  image build context. It stays out of git because:
  - its size (~320 MB of table data; compressed size unverified) exceeds GitHub's 100 MB per-file
    limit;
  - the repo is public, and this is Yahoo-sourced market data (redistribution terms unverified);
  - it's reproducible from the old database, which stays in place.

  It's kept until the user says otherwise; deleting it needs the user's OK.
- **Restore:**
  - Precheck that all 6 tables in `fathom` are at 0 rows.
  - Run `pg_restore -h localhost -p 5433 -d fathom --data-only --single-transaction
    --exit-on-error` with `PGTZ=America/New_York` (naive values are copied as text, so this is
    belt and braces).
  - Only `fathom` gets real data. `fathom_test` never does.
- **Check against the old database:** `scripts/restore/compare.sql` runs on both sides (old side
  read-only) and the outputs are diffed. It must be identical:
  - exact `count(*)` per table;
  - price_bars: distinct tickers, `min(date)`/`max(date)`, and per ticker (rows, min date,
    max date, `md5(string_agg(row::text ORDER BY date))`), so any difference is pinned to one
    ticker;
  - full-table md5 over primary-key order for the 5 small tables;
  - sequence `last_value` ≥ `max(id)`.
- **Step 4 then converts the timestamps** (migration 0002, `ALTER … TYPE timestamptz USING col AT
  TIME ZONE 'America/New_York'`). Afterwards `compare.sql` checks the old side's
  `col AT TIME ZONE 'America/New_York'` against the new values. The test written first shows the
  mixed-semantics problem on `fathom_test`. Ambiguous fall-back hours (01:00–02:00 on a DST change)
  are listed if any rows fall in them.
- **Catch-up (step 8, after the pipeline merges):**
  - `ingest` runs over all tracked tickers (old semantics: `ticker_metadata`, 506, which includes
    SPY/BROS/CROX), from each ticker's last date to the last completed session.
  - Then `check-actions`, because splits since 2026-09-08 change adjusted history.
  - Then a fresh universe snapshot, appended under a new `snapshot_at` and never overwritten, so
    point-in-time membership is kept; new members are backfilled from 2010 by the same ingest.
  - Report: the ingestion_runs row, per-ticker failures listed by name (missing stays missing),
    rows added, and 3 sample closes for the user to check by hand against a public quote page.
  - yfinance is free, so this spends no money.

## 3. Preconditions
**(a) `DATABASE_URL` host+port guard (P1, test first, before the restore).**
- A new `core.db_guard.refuse_old_database(url)` is called inside `core.db.make_engine`, so the API,
  the CLI ingest, Alembic's `env.py`, the gate and the tests all pass through it, and it fires
  before any connection.
- The rule is: **port 5432 (or no port, which libpq treats as 5432) is allowed only when the host
  is `postgres`**, the Compose service name.
  - Refused: `localhost`, `127.0.0.1`, `::1`, `0.0.0.0`, no host (Unix socket, which reaches
    Homebrew's server), and `host.docker.internal` (which from inside Docker reaches the Mac's
    5432).
  - Also refused, on any host and port: a database name starting with `strategy_research`.
- Parametrized tests cover each refused form, plus `postgres:5432/fathom` and
  `localhost:5433/fathom` allowed. A further test proves `make_engine` raises without opening a
  socket.
- The existing `DATABASE_URL_TEST` guard in `tests/conftest.py` stays as it is (it also checks the
  `fathom_test` name).

**(b) Commit-log conflict fix (P2, before the split; decision 0008, amending 0004).**
- **One file per commit**: `docs/explanations/phase-N/commits/<short-sha>.md`, holding the same
  stub and note as today. Two branches never write the same file, so merges can't conflict.
- Hook changes:
  - It takes the repo root from the hook input's `cwd` (`git -C "$cwd" rev-parse --show-toplevel`)
    instead of `$CLAUDE_PROJECT_DIR`. Whether that variable points at the worktree in a
    `--worktree` session is unverified, and `cwd` is right either way.
  - Its "already logged" check becomes "file exists".
- It's tested by piping sample hook JSON into the script inside a throwaway git repo in the
  scratchpad: a commit gets a file; a docs-only commit and a second run get none.
- Branches merge with `git merge --no-ff`, and worktrees update from `main` by merging, never
  rebasing, so SHAs (and the file names) stay valid.
- Worktree sessions don't edit `docs/STATUS.md`. Only the main session does, after each merge.
- Updated with it: CLAUDE.md (one line), the session-handoff and explanation-writer skills,
  `parallel-work.md`.
- The existing `phase-1/commit-log.md` entry (a684db2) moves to `commits/a684db2.md`; the Phase 0
  log stays as it is.

## 4. Parallel split
- **Before the split, merged and pushed on `main`:** P1, P2, steps 1–4. That covers every
  dependency (no worktree touches `pyproject.toml`/`uv.lock`), the models and both migrations, and
  the shared test fixtures in `tests/conftest.py`:
  - migrate `fathom_test` with `alembic upgrade head` once per session;
  - a fixture that truncates the 6 tables;
  - the old `make_synthetic_data`.
- **Worktree A `pipeline-import`** (steps 5a–7a): `src/data_pipeline/` (except `db/`),
  `src/core/market_calendar.py`, `tests/data_pipeline/`, `tests/core/test_market_calendar.py`.
- **Worktree B `backtester-import`** (steps 5b–7b): `src/backtester/`, `src/research_stats/`,
  `tests/backtester/`, `tests/research_stats/`, `scripts/_extended_codegen.py`,
  `scripts/verify_extended_indicators.py`.
- **Neither touches:** migrations, `src/data_pipeline/db/`, `tests/conftest.py`, pyproject/uv.lock,
  STATUS.md, CLAUDE.md, `.claude/`. If either finds it needs a schema or dependency change, it
  stops and reports; it doesn't make one.
- **Migrations owner:** the main session, the only one that runs Alembic `revision`.
- **Merge order:**
  1. A first (smaller; the catch-up needs it).
  2. B merges `main` in and reruns the full suite.
  3. Then B merges.

  Each merge needs `make test` + `make lint` green on the branch, and the code-reviewer agent run.
- Two sessions, the plan table's pairing. The number checker stays in `main` after the merges
  rather than a third worktree, because you review every session.

## 5. Dependencies
- **New cutoff:** `exclude-newer` and npm's `before=` both move to the install date minus 14 days
  (e.g. 2026-10-15T23:59:59Z if installed 10-29). I'll run `scripts/check_dependency_age.py` and
  show its output.
- **Pins:** the old-venv versions, per decision 0003. Publish dates are from PyPI (2026-10-28) and
  every one predates the cutoff. Each one has a cp313 wheel (or is pure Python / abi3) for macOS
  arm64, Linux x86_64 (CI) and Linux aarch64 (the API image on this Mac):

| Package | Pin | Published | Why |
| --- | --- | --- | --- |
| yfinance | 1.5.1 | 2026-06-28 | prices (pulls curl_cffi 0.15.0, 2026-04-03, abi3 wheels) |
| pandas | 3.0.3 | 2026-05-11 | everything |
| numpy | 2.2.6 | 2025-05-17 | held below 2.3 by numba 0.61.2 |
| scipy | 1.18.0 | 2026-06-19 | significance, bootstrap, BH |
| backtesting | 0.6.6 | 2026-07-22 | engine (pulls bokeh 3.9.2, 2026-07-25) |
| pandas-ta | 0.4.71b0 | 2025-09-14 | indicators; pins **numba==0.61.2** (2025-04-09) → llvmlite 0.44.0 (2025-01-20) |
| tenacity | 9.1.4 | 2026-02-07 | fetch retries |
| alembic | 1.19.1 | 2026-08-08 | migrations |
| requests | 2.34.2 | 2026-05-14 | universe CLI |
| lxml | 6.1.2 | 2026-08-19 | `pd.read_html` (universe) |
| openpyxl | 3.1.5 | 2024-06-28 | SSGA xlsx cross-check |
| exchange-calendars | 4.13.2 | 2026-03-10 | **new**: XNYS sessions, holidays, early closes |

- **Python 3.13.16:** numba 0.61.2 declares ≥3.10, has cp313 wheels and requires numpy <2.3, which
  2.2.6 satisfies. The old venv ran the same set on 3.13.7.
- **Risks:**
  - pandas-ta is a beta with no release since 2025-09-14.
  - exchange-calendars declares `pandas>=1.5`; whether it works with pandas 3.0.3 is
    **unverified**. Its tests in 7a show it. Fallback: pandas_market_calendars, a new dependency
    for which I'd ask.
  - If yfinance 1.5.1 breaks against Yahoo during the catch-up, upgrading it is a dependency change
    and I'll ask first.
- **How the imported tests are adapted:**
  - The old root conftest's autouse fixture made every test need a database with pgvector. It goes:
    database fixtures are explicit, and pure tests (evaluator, schema, significance,
    number checker) run with no database.
  - The schema comes from Alembic on `fathom_test`, not `create_all()`.
  - Fixtures come only from Fathom's `engine` fixture, so the 5432 and `fathom_test` guards always
    apply. Nothing reads `.env` for the old URL, and the old database is never touched.
  - `test_fetch.py` (real yfinance) gets the `live` marker. The other tests already mock yfinance,
    so pytest-socket stays on.
  - The old `known_prices.csv` has `FILL_IN_SOURCE`/`FILL_IN_DATE` placeholders, so its number has
    no recorded source. It's kept only for the live test and re-recorded with its source when you
    ask for a live run. No unsourced number enters an offline test.
  - **The live-test gap moves up from Phase 2:** this is the first live test, so the fix lands with
    it.
    1. `live` tests skip unless `FATHOM_ALLOW_LIVE=1`.
    2. A test marked `enable_socket` errors unless it's also marked `live`.
    3. Whether a command prefixed with `FATHOM_ALLOW_LIVE=1` falls outside the allow rule is tested
       then, too.
  - The gate's test-count check (section 6) catches any dropped test.

## 6. Phase 1 gate (`tests/gates/test_phase1_gate.py`, `make gate PHASE=1`)
1. **All imported tests pass.**
   - The gate runs the default suite in a subprocess and requires exit code 0.
   - It also compares the collected counts per directory against a committed manifest of the old
     counts: data_pipeline 14 minus screener 6 = 8, of which 1 is live; backtester 91 test
     functions; research_stats 12; plus the ported number-checker tests.
   - *Can fail:* deleting or skipping a test drops a count below the manifest.
2. **Every S&P 500 ticker's latest price is from the last trading day.**
   - The S&P 500 is the tickers in the latest `universe_snapshots` row set.
   - The "last trading day" comes from the calendar, never from the data:
     `last_completed_session(now)` is the latest XNYS session whose close (13:00 on early-close
     days) plus a 2 h availability buffer is ≤ now. exchange-calendars carries holidays and early
     closes. The 2 h buffer is my assumption for yfinance's lag; unverified.
   - The gate queries `fathom` (read-only transaction) for tickers whose `max(date)` < that day,
     and the set must be empty; failures are listed by name.
   - *Can fail:* the same function run on `fathom_test` with one planted stale ticker returns it.
   - Fixed-date unit tests for the calendar: Saturday → Friday; Thanksgiving 2026-11-26 →
     11-25; the Monday 15:00 ET before close → the previous Friday; 2026-11-27 (early close)
     after 15:00 → 11-27.
3. **A zero-trade backtest returns a clean result.** An impossible rule gives `no_trades=True`,
   `None` metrics, survives a JSON round trip, and significance returns "no trades".
   - *Can fail:* a rule that does trade returns `no_trades=False` with numeric metrics, so it isn't
     hard-coded.
- **Written walkthrough (not automatable):** the nightly job ran by itself — `launchctl print`
  shows the last exit code is 0, and an ingestion_runs row has a start time at the scheduled time
  that no one started by hand.
- Result, date and raw output go into STATUS.md.

## 7. Nightly price job (step 9)
- **The job is code; the trigger is replaceable.**
  - `python -m data_pipeline.cli nightly` (make target `make nightly`) runs `ingest` up to the
    last completed session, then `check-actions` (weekly cadence in the old docs; nightly is cheap
    at 506 tickers, revisit if slow).
  - On a non-session day it's a logged no-op.
  - It's idempotent and incremental from each ticker's last date, so a missed night heals on the
    next run.
- **Trigger in Phase 1: a macOS launchd user agent.**
  - The plist is committed at `ops/launchd/com.fathom.nightly-prices.plist`; `make nightly-install`
    copies it to `~/Library/LaunchAgents` and loads it.
  - It runs Mon–Sat at 19:00 local (ET), via `make nightly` with uv on the host, against
    localhost:5433. Output goes to `~/Library/Logs/fathom/`.
  - Per launchd's documentation, a run missed during sleep fires on wake; unverified until
    installed.
  - Installing changes your user's LaunchAgents, so **I'll ask before `make nightly-install`**.
  - It needs the Compose stack up. If Postgres is down the run fails, the log says why, and the
    next run catches up.
- **Why not now:**
  - arq is the Phase 4 worker, and its status is still unverified. PyPI shows 0.28.0 on
    2026-04-16, but the repo's maintenance status still needs checking before Phase 4.
  - A homegrown loop scheduler or APScheduler would add code or a dependency that Phase 4 replaces
    anyway.
  - Phase 4 swaps the trigger (arq cron, or whatever replaces it) and keeps the same CLI function.
- Failure alerting is Phase 6. Until then the gate's freshness check and `ingestion_runs` show it.

## Changes from review (approved 2026-10-28)
1. **Timestamp conversion, per column, from evidence.** The New York evidence covers
   `ingestion_runs` only. Before migration 0002, list every timestamp column in the six tables
   and show, from the old code that writes it (file and line), whether it was written as an aware
   UTC datetime or a naive one. Add a data check wherever possible (e.g. `snapshot_at` and
   `fetched_at` against the market close). Convert each column with the zone its evidence
   supports. **Any column without evidence: stop and ask.**
2. **Separate test databases for the worktrees.**
   - Before the split, create `fathom_test_a` and `fathom_test_b`, migrated the same way as
     `fathom_test`, so the two worktrees' truncate fixtures can't wipe each other's data mid-run.
   - Widen the conftest guard to accept only `fathom_test` or `fathom_test_<letters>`
     (regex `^fathom_test(_[a-z]+)?$`).
   - Each worktree gets its own `DATABASE_URL_TEST`. The proposal states how before step 4 ends.
3. **Decision 0009** records the `corrected_threshold` change (dropping the per-tier multiplier)
   and what it changes in reported significance.
4. **The number checker moves to worktree C** (`number-checker`). This replaces step 10 in the
   main session.
   - **Start:** as soon as P2 is pushed. It runs alongside steps 1–4 in the main session.
   - **Scope:** it touches only `src/fact_check/` and `tests/fact_check/`. It uses no database
     and needs no new dependency. If it turns out to need either, that session stops and
     reports.
   - **Merge:** C merges to `main` before worktrees A and B start, so there are never more than
     3 sessions at once.
   - **New order:** P1 → P2 → (main: 1–4 ∥ C) → merge C → (A ∥ B) → merge A, B → 8 → 9 → 11.
5. **P1 as built (approved 2026-10-28).**
   - **Two layers:**
     1. A URL check before any engine exists. Beyond the original rule, it refuses lists of
        hosts or ports, `hostaddr`/`dsn`/`service` in the query, `PGHOSTADDR`/`PGSERVICE`/
        `PGSERVICEFILE` in the environment, and a `strategy_research*` name in the query's
        `dbname`.
     2. A check on every new connection: the server reached must have no `strategy_research*`
        database.
   - **The scan:** `tests/unit/test_connection_paths.py` reads every Python file in the repo
     except `.venv`, `node_modules`, `.git` and `.claude/worktrees`. It fails if anything other
     than `src/core/db.py` opens a Postgres connection.
   - **Known limits:** dynamic imports aren't detected, and no test checks that a refused
     connection is closed.

## Verification, per step
Every step ends with the tests run (failing test shown first where it's a fix), `make test`,
`make lint`, real-data output, the code-reviewer agent, and a step explainer
(explanation-writer). Servers are restarted after code changes (`make up` rebuilds the API image
for the new dependencies). Steps 3, 4 and 8 also show the `compare.sql` diff, the
ingestion_runs and failure listing, and the sample closes.

## Kept in view (not changed by this plan)
- Public repo: your decision. Nothing secret or bulk data is committed.
- arq: check before Phase 4.
- Survivorship bias (today's members) is disclosed wherever the universe is used.
- `plansDirectory` works: this plan file was created in `plans/`. That Known issue closes at
  handoff.
- The catch-up stores today's adjusted prices; `raw_*` is never overwritten (old upsert
  semantics). Kept as is.
