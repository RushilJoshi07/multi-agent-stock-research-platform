# Fathom build plan: A to Z

Oct 15, 2026 · @Rushil Joshi

## What we're building

Fathom is a multi-agent stock research app: you name a stock or an idea, a team of AI agents researches it, code-based rules decide what is allowed, and every call is graded against what the market actually did. Paper trading only, no real money.

v1 includes:

- Analyze one or a few stocks: buy, sell or hold, with confidence, a trade plan and a risk check
- The live "team at work" view and the decision report
- A watchlist the team re-analyzes every trading morning
- A paper portfolio on Alpaca
- A track record that grades every call when its time horizon ends
- Light and dark themes, phone and desktop layouts, deployed and running on its own

v1 is done when all four are true:

1. Someone who has never seen it can type "Analyze ORCL", confirm, watch the team, read the report and place a paper trade with no explanation.
2. Every number in a report traces back to a stored source.
3. It runs for 5 trading days unattended: nightly prices, morning watchlist runs and nightly grading, with no manual fixes.
4. Cost per run is measured and capped.

After v1: v2 adds Discover and Compare, v3 adds the Portfolio builder and Backtest lab, v4 adds self-improvement. Not planned for now: real-money trading, a native mobile app (the responsive web app covers phones) and Reddit sentiment, which is an optional experiment after v1.

## How we work

Claude Code builds, a separate review chat checks, and you decide. Nothing gets written before you approve the approach, and nothing counts as done until it has been checked against real data.

The build loop, for every piece of work:

1. Take the next task from this plan or from STATUS.md.
2. Claude Code explains its approach without writing code. Paste it into the review chat.
3. The review chat checks it. Send back approval or changes.
4. Claude Code writes the code and tests, runs them, verifies against real data and shows the diff.
5. Paste the results into the review chat for a gap check. Only real problems get raised.
6. Commit, push and update STATUS.md.

Session hygiene:

- One Claude Code session per phase or large task. Open each one by having it read CLAUDE.md, STATUS.md, the current phase of this plan, and the git log and status.
- When a session passes about 60–70% of its context, stop: commit, update STATUS.md, start a fresh session.
- STATUS.md is the single source of truth for where things stand: done, in progress, next, known issues. Nobody relies on memory of an old chat.
- Start a new review chat for this project too. The current one is very long.

| Who | Does | Never does |
| --- | --- | --- |
| You | Pick the next task, approve plans, paste between the two, make product calls | Approve something you don't understand |
| Claude Code (VS Code) | Proposes the approach, writes code and tests, runs them against real data, commits and pushes | Writes code before approval, or claims something it didn't check |
| Review chat (Claude) | Explains Claude Code's work in plain language, flags real gaps, gives you the exact reply to send | States as fact anything that isn't in what you pasted |

Explanations follow the old project's method: a step explainer after every working component, a phase summary after every phase, and a short commit-log note after every commit.

Rules that go into CLAUDE.md:

- Check the real repo and data before stating anything as fact; otherwise say it's unverified.
- Explain before writing, and wait for approval on each component.
- Working first: no polish, extra docs or new features until the core path works end to end.
- Every number shown to the user traces to a stored source. Nothing is invented.
- Agents only see data that existed at the moment of the decision.
- AI agents read and argue; code decides, sizes and places trades.
- Missing data is reported as missing, never filled in.
- Ask before anything that spends money (one AI run batch over $1, any paid API) or deletes data.
- After editing code, restart the servers before verifying. Leave dev servers running unless told otherwise, and say which ones are up.
- No Co-Authored-By line in commits; push after every commit.
- Update STATUS.md at the end of every session.

## Guardrails and gates

The old project's discipline carries over, plus one new gate for the trading side.

- **Sacred gate 1, no lookahead:** agents and backtests only see data that existed at the moment of the decision. This is tested, not assumed.
- **Sacred gate 2, no invented numbers:** the fact check rejects any number that doesn't match a stored source.
- **Sacred gate 3, code acts:** no AI output places, sizes or approves a trade. Only the risk rules and the portfolio manager, both plain code, can.
- **Phase gates:** each phase's "Done when" becomes an automated test in `tests/gates/` wherever possible, plus a written walkthrough for what can't be automated. The next phase starts only after the gate passes and its result is recorded in STATUS.md.
- **Golden set:** a fixed set of known cases, re-run after any agent or prompt change, to catch quality drifting.

## Repo and Claude Code setup

Fathom uses Claude Code's own project structure, so every session, including parallel ones, starts from the same rules, skills and agents.

| Path | Holds |
| --- | --- |
| `CLAUDE.md` | Working agreement, the rules above, how to run and test everything |
| `.claude/rules/` | Detailed rule files: data rigor, agent honesty, backtesting, testing and gates, frontend, parallel work |
| `.claude/skills/explanation-writer/` | The explainer skill from the old project, adapted for Fathom |
| `.claude/skills/phase-gate/` | Runs a phase's gate checks and reports pass or fail with evidence |
| `.claude/skills/session-handoff/` | Updates STATUS.md and writes the next session's opening message |
| `.claude/agents/` | Custom subagents for focused jobs, such as a code reviewer and a test writer |
| `.claude/settings.json` | Permissions and hooks, including the commit-log note after every commit |
| `docs/plan.md`, `docs/STATUS.md` | This plan and the live status |
| `docs/explanations/phase-N/` | Step explainers, the phase summary and the commit log for each phase |
| `docs/decisions/` | One short note per real design decision, with the options rejected |
| `docs/ideas.md` | Ideas parked until after v1 |

## Parallel work

Run up to three Claude Code sessions at once, each in its own git worktree, and only on tasks that touch different folders and share an interface agreed beforehand. More sessions save calendar time but multiply AI usage, and you review every one, so beyond three you become the bottleneck.

One-time setup in VS Code:

1. Install the Claude Code command-line tool so `claude --version` works in VS Code's terminal. The extension's chat panel may not offer a per-session worktree option, so parallel sessions run from the terminal.
2. Run `claude` once in the repo to accept the workspace trust prompt; worktree sessions won't start until you have.
3. Add `.claude/worktrees/` to `.gitignore`, and add a `.worktreeinclude` file listing `.env` so every worktree gets your API keys.
4. Push `main` before starting parallel work. New worktrees branch from the remote's `main` by default, so unpushed work won't be in them.

Running a parallel task:

1. Open a new VS Code terminal and run `claude --worktree <task-name>`, e.g. `claude --worktree edgar-client`. It gets its own folder under `.claude/worktrees/` and its own branch.
2. Install dependencies inside the new worktree first; it's a fresh checkout.
3. Read its code in the VS Code explorer under `.claude/worktrees/<task-name>/`, or open that folder in a new window.
4. When it passes its tests and review, merge its branch into `main`, push, and have the other sessions update from `main` before continuing.
5. Exit the session; Claude Code offers to remove the worktree, and `git worktree remove <path>` cleans up any leftovers.

What can run in parallel:

| Phase | In parallel | Must stay one at a time |
| --- | --- | --- |
| 0 Setup | Nothing | Everything: it defines the shared structure |
| 1 Import | Price pipeline import; backtester and significance test import | Database restore and migrations |
| 2 Data | EDGAR client; Finnhub client; Alpaca client | The shared "as of" query rules, written first; migrations |
| 3 Agents | The four analysts; risk rules and portfolio manager; fact check | Shared report formats first; wiring the graph last |
| 4–5 API and app | Backend API; frontend screens, split by page | The API contract, fixed before either side starts |
| 6 Deploy | Deployment and CI; end-to-end tests | The production cutover |
| 7–8 | Discover and Compare; Portfolio builder; Backtest lab | Shared navigation and layout |

Rules for parallel work:

- One session owns database migrations at a time; parallel sessions never create them.
- Shared formats and API shapes are written and merged before parallel work starts.
- Every branch runs the full test suite before it merges, and branches merge one at a time.
- The review chat says when a proposed task is safe to run in parallel.

Sources: Run parallel sessions with worktrees (Claude Code docs).

## Tech stack

The stack keeps what already works in the old project (Python, FastAPI, Postgres, Claude on Bedrock) and adds what production needs: a real job queue, tracing, and proper deployment.

| Layer | Choice | Why |
| --- | --- | --- |
| Backend | Python 3.12, FastAPI | Same as the old project, so its code imports cleanly |
| Database | PostgreSQL, SQLAlchemy, Alembic | Reuses the old schema and the 506-ticker price history |
| Agent orchestration | LangGraph | Graph of agents with state, branching and retries |
| Tracing and evals | LangSmith | Every run replayable step by step; agent-quality test sets |
| AI model | Claude via Amazon Bedrock | Already set up and paid for in the old project |
| Background jobs | Redis and an arq worker | Analyses run outside the web server and survive restarts, which fixes the old BackgroundTasks weakness |
| Scheduled jobs | arq cron jobs | Nightly prices, morning watchlist runs, nightly grading |
| Live progress | Server-Sent Events | The "team at work" screen updates as each step finishes |
| Frontend | React, TypeScript, Vite, Tailwind | Light and dark color tokens taken from the mockups |
| Price charts | An open-source finance chart library (TradingView Lightweight Charts is the first candidate) | Proper candlestick and line charts |
| Paper trading and quotes | Alpaca paper API | Free, real-time quotes, realistic fills, short selling |
| Market data | yfinance (prices), SEC EDGAR (financials), Finnhub (news) | All have usable free tiers |
| Tests | pytest; Vitest and Playwright for the key screens; LangSmith eval sets | Code, UI and agent quality each get checked |
| Deploy | Docker Compose locally; AWS (a small server plus a managed Postgres database) for v1; GitHub Actions | Simple to run, real cloud deployment for the resume |
| Monitoring | LangSmith, structured logs, an error tracker with a free tier, alerts on failed scheduled jobs | You hear about failures without checking manually |
| Access control | Single-user login, rate limit, daily AI cost cap | A public demo can't run up your bill |

Any choice can change if Claude Code finds a concrete reason during Phase 0, but it has to say what the reason is.

## What to import from the old project

Bring over the data and math that already work and were tested against real data; leave behind everything that decided what to research. The old repo at `/Users/rushil/agentic-finance-platform` stays untouched as a reference.

| Piece | Old location | Use in Fathom |
| --- | --- | --- |
| Price pipeline (fetch, raw and adjusted prices, splits and dividends, upsert, ingestion logs) | `src/data_pipeline/` | Prices for every feature |
| S&P 500 universe and snapshot table | `src/data_pipeline/` | Sector lists for Discover |
| Price history: 506 tickers, 2010 to Sep 8, 2026 | Postgres `strategy_research` | Restore it, then catch up the missing days |
| No-lookahead backtester | `src/backtester/` | Technical analyst's tool and the Backtest lab |
| Significance test (comparison with random entries, corrected thresholds) | `src/research_stats/` | "Chance this is luck" in pattern tests |
| Number checker (the Sacred Gate 2 logic) | `src/agentic_core/verdict.py` | The fact-check step |
| Retry-with-feedback pattern | `verdict.py`, `hypothesis.py` | Every structured agent output |

Leave behind: the charter parser, the hypothesis generator, literature grounding and the old frontend.

How to import:

1. One commit per piece, with a message naming the source, e.g. "Import data pipeline from agentic-finance-platform" plus the old commit hash.
2. Copy each piece together with its tests. Its tests must pass in the new repo before anything is built on top of it.
3. Restore the price data with a Postgres dump rather than re-downloading 16 years, then run the normal ingest to fill the gap since Sep 8.
4. Fix the known zero-trade crash on import: a backtest with no trades returns an empty win rate that breaks the run. It has to return a clean "no trades" result before the backtester becomes an agent tool.

## Phases 0–6: building v1

Seven phases take Fathom from an empty repo to a deployed v1 in about 11 weeks. Each phase ends with a gate that has to pass before the next one starts.

### Phase 0: Setup (2–3 days)

- Create a private GitHub repo `fathom`, open it in VS Code with the Claude Code extension.
- Write CLAUDE.md and the rule files, put this plan in `docs/plan.md`, start STATUS.md.
- Docker Compose with Postgres and Redis; a FastAPI app with a health check; an empty React app; GitHub Actions running tests; `.env.example` listing every key.

**Done when:** one command starts the database, Redis, API and web app, the health check is green, and CI passes.

### Phase 1: Import the foundations (week 1)

- Import the price pipeline, universe, backtester, significance test and number checker, each with its tests.
- Restore the 506-ticker database and catch up the missing days.
- Fix the zero-trade crash. Add the nightly price job.

**Done when:** all imported tests pass; a query shows every S&P 500 ticker's latest price is from the last trading day; a backtest with zero trades returns a clean result.

### Phase 2: New data sources (week 2)

- SEC EDGAR: map tickers to company IDs, pull reported financials (revenue, margins, debt, EPS) with their filing dates.
- Finnhub news: store headline, source, link, publish time and fetch time.
- Alpaca: live quotes, paper orders, positions.
- Rate limiting, caching and retries for each; "as of" queries so nothing reads data newer than the decision time.

**Done when:** five test tickers return real data from every source with timestamps, and a test proves an "as of last month" query excludes newer rows.

### Phase 3: The agent team (weeks 3–5)

- Request understanding and the confirm step.
- Four analysts (fundamentals, news, sentiment, technical), each with read-only tools and a fixed output format. In v1 the sentiment analyst scores the tone of news coverage, not social media.
- Fact check in code; bull and bear debate (2 rounds) and a summary step; the trader.
- Risk rules in code: position limits, shorts capped at 2%, stop-loss required, volatility limit.
- Portfolio manager in code, the only part allowed to place paper orders.
- Decision log storing everything the team saw; LangSmith tracing; retries with feedback; a cost and time budget per run; clear handling of missing data.

**Done when:** "Analyze ORCL" from the command line produces a full report with every number traced; a planted wrong number is caught; a simulated news outage shows "unavailable" instead of a guess; an agent-quality test set of 20–30 cases runs in LangSmith with recorded scores; cost per run is measured.

### Phase 4: API, jobs and safety (week 6)

- Endpoints for runs, reports, watchlist, portfolio, decisions and track record.
- arq workers; live progress over Server-Sent Events.
- Scheduled jobs: nightly prices, morning watchlist runs, nightly grading.
- Login, rate limit, daily AI cost cap.

**Done when:** a run started through the API streams its progress and survives an API restart; scheduled jobs fire on a test clock; the cost cap blocks runs once reached.

### Phase 5: The app (weeks 7–9)

- Build from the mockups: Home, Stock page, Team at work, Report, Watchlist, Paper portfolio, Track record.
- Light and dark themes; phone and desktop layouts.
- Playwright test for analyze → report → paper trade.

**Done when:** someone who has never seen the app analyzes a stock and places a paper trade without help, on desktop and phone; the Playwright test passes.

### Phase 6: Deploy and monitor, v1 launch (weeks 10–11)

- Docker images, AWS deployment, secrets, CI/CD on every push to `main`.
- Database backups, error tracking, alerts on failed jobs, LangSmith in production.

**Done when:** v1 runs 5 trading days unattended, with prices, watchlist runs and grading all happening without manual fixes. At this point v1 is resume-ready.

## Phases 7–10: after v1

Start applying for jobs as soon as v1 passes its gate; v2 to v4 ship while you apply, each one a new talking point.

### Phase 7: v2, Discover and Compare (2–3 weeks)

- Sector or plain-language request → a stock list you edit and confirm → a fast numbers-only screen → the full team on your picks.
- Compare 2–4 stocks: one chart, a metrics table, each stock's team view and a ranked verdict for your horizon.

**Done when:** "pharma stocks with strong momentum" returns an editable list and a ranked screen, and Compare ranks three stocks with every number sourced.

### Phase 8: v3, Portfolio builder and Backtest lab (3–4 weeks)

- Portfolio builder: conservative, balanced and aggressive allocations, volatility, worst historical drop, how the stocks move together.
- Backtest lab: pattern detectors in code, starting with morning star and a few common candlestick patterns, run through the imported backtester and significance test.

**Done when:** a 4-stock allocation's risk numbers match a hand calculation, and "does morning star work on ORCL?" returns every occurrence, the outcome compared with random days, and an honest "too few to judge" when that's the case.

### Phase 9: v4, Self-improvement (about 2 weeks)

- A reflection agent reads graded calls and writes short lessons.
- Future runs pull in the lessons relevant to them; reports show which lessons were used.

**Done when:** lessons are stored, retrieved and visible, and a before/after comparison of hit rates is published, whatever it shows.

### Phase 10: Job-search material (starts at v1, ongoing)

- README with the architecture diagram and screenshots.
- A 2–3 minute demo video.
- Evaluation results and measured costs.
- An honest limitations section.
- Resume bullets.

Reddit sentiment is an optional experiment after v1. It ships only if the track record shows it improves the calls, and it never blocks a phase.

## Timeline, accounts, costs and risks

Working full-time from Oct 19, 2026, v1 is ready to show around mid-January 2027 and v2 to v4 land by mid-March. Part-time roughly doubles the build weeks.

**v1 is ready to show around mid-January; v2 to v4 follow by mid-March.** Estimated, assuming full-time work from Oct 19, 2026. (The original plan shows this as a timeline chart; the dates are listed here.)

| Phase | Dates |
| --- | --- |
| Phase 0 · Setup | Oct 19 to Oct 21 |
| Phase 1 · Import foundations | Oct 22 to Oct 28 |
| Phase 2 · New data sources | Oct 29 to Nov 4 |
| Phase 3 · Agent team | Nov 5 to Nov 25 |
| Phase 4 · API, jobs, safety | Nov 26 to Dec 2 |
| Phase 5 · The app | Dec 3 to Dec 23 |
| Phase 6 · Deploy, monitor | Dec 24 to Jan 6 |
| **v1 gate · 5 days unattended** | **Jan 13** |
| Phase 7 · Discover, Compare | Jan 14 to Feb 3 |
| Phase 8 · Portfolio, Lab | Feb 4 to Mar 3 |
| Phase 9 · Self-improvement | Mar 4 to Mar 17 |

The v1 gate is five trading days running unattended. Job applications start there.

### Accounts to set up

| Account | Used for | Cost | When |
| --- | --- | --- | --- |
| GitHub | Repo and CI | Free | Day one |
| Alpaca (paper only) | Paper portfolio, live quotes | Free | Day one |
| Finnhub | Company news | Free for personal, non-commercial use | Day one |
| LangSmith | Tracing and evals | Free tier; check its limits | Day one |
| AWS | Claude via Bedrock (already set up), hosting | Pay as you go | Hosting in Phase 6 |
| SEC EDGAR | Company financials | Free, no key; requests must send a User-Agent with your email | Phase 2 |
| Reddit API | Optional sentiment experiment after v1 | Free for non-commercial use; approval can take 2–4 weeks | Apply early only if you want the experiment |
| Error tracker (e.g. Sentry) | Error alerts | Free tier | Phase 6 |

### Costs

AI calls are the only real running cost. The old project measured about $0.06 for a 15-step run, and a full team run will cost several times that per stock. Phase 3 measures the real figure and the daily cap holds it.

Market data and paper trading cost nothing on the free tiers for personal, non-commercial use.

Hosting gets estimated in Phase 6 with the AWS pricing calculator: one small server and a small managed database.

### Risks

| Risk | Effect | Fallback |
| --- | --- | --- |
| yfinance breaks or rate-limits | Prices stop updating | Alpaca's price history as a backup |
| Free Finnhub news covers about one year | Little testing on older periods | Save every decision from day one; test on recent data |
| Agent outputs vary run to run | Unreliable reports | Fixed output formats, retries with feedback, LangSmith eval sets |
| AI costs grow | A surprise bill | Per-run budget, daily cap, watchlist of about 10 stocks |
| New ideas arrive mid-build | v1 slips | Park them in `docs/ideas.md` until v1 passes its gate |
| Long chats lose track | Wrong assumptions | STATUS.md and the check-before-claiming rule |

## Day one

Day one is setup only: accounts, an empty repo, this plan inside it, and Claude Code proposing Phase 0 without writing anything yet.

1. Install VS Code and the Claude Code extension, and sign in.
2. Create a private GitHub repo called `fathom`, clone it, open it in VS Code.
3. Sign up for Alpaca (paper only), Finnhub and LangSmith. Apply for Reddit API access now if you want social sentiment later.
4. Export this doc to Markdown and save it in the repo as `docs/plan.md`.
5. Start a new review chat in this Claude project and paste the review-chat starter below.
6. Open Claude Code in the repo and send the first message below.

First message to Claude Code:

```
We're starting a new project called Fathom, a multi-agent stock research app.
The full plan is in docs/plan.md. Read it first, especially "How we work" and
Phase 0. The old project at /Users/rushil/agentic-finance-platform is
reference only; never modify it.

Task: Phase 0 only. Before creating any files, propose:
1. The repo folder structure.
2. The contents of CLAUDE.md and STATUS.md, based on the plan's rules.
3. The Docker Compose services.
4. Anything in the plan's tech stack you would change, and why.
Wait for my approval before writing anything.
```

Review-chat starter:

```
I'm building Fathom, a multi-agent stock research app (plan attached). Claude
Code builds it in VS Code. I'll paste what Claude Code sends me. For each
one: explain it in plain language with examples from this project, say what's
genuinely good, flag only real gaps or risks, and give me the exact message
to send back. Never state anything as fact that isn't in what I pasted. When
a proposed task can safely run in parallel with others (different folders,
agreed interfaces), tell me and how to split it.
```
