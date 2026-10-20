# Fathom

Multi-agent stock research app: AI agents research a stock, code-based rules decide
what is allowed, and every call is graded against what the market actually did.
Paper trading only, no real money.

- Build plan: `docs/plan.md`. Each session reads only the current phase's section (plus
  "How we work" if needed), not the whole file.
- Live status: @docs/STATUS.md
- Detailed rules: `.claude/rules/`
- Approved deviations from `docs/plan.md` are recorded in `docs/decisions/` and win where
  they conflict with the plan. The first ones: Python 3.13, uv, the host ports, and the repo
  name `multi-agent-stock-research-platform` (the plan says `fathom`).

## Session start
Read this file, `docs/STATUS.md`, the current phase of `docs/plan.md`, and `git log` / `git status`.

## Working agreement
- Explain the approach before writing code, and wait for approval on each component.
- Do one numbered step at a time: show the files and results, then stop.
- Check the real repo and data before stating anything as fact; otherwise say "unverified".
- Working first: no polish, extra docs or new features until the core path works end to end.
- Step explainers (after every working component) and phase summaries (after every phase) are
  written with the explanation-writer skill into `docs/explanations/phase-N/`.
- The 3–6 line commit-log note goes in `docs/explanations/phase-N/commit-log.md` when the hook
  asks (the hook writes the stub after each commit; you fill it in).
- New ideas go to `docs/ideas.md` until v1 passes its gate.

## Sacred gates (tested, never assumed, never weakened)
1. No lookahead: agents and backtests only see data that existed at the moment of the decision.
2. No invented numbers: every number shown to the user traces to a stored source; the fact
   check rejects any number that doesn't match one.
3. Code acts: no AI output places, sizes or approves a trade. Only the risk rules and the
   portfolio manager, both plain code, can.

## Data rules
- Missing data is reported as missing, never filled in.
- AI agents read and argue; code decides, sizes and places trades.

## Money and data safety
- Ask before anything that spends money (one AI run batch over $1, any paid API) or deletes
  data (dropping tables, `docker compose down -v`, deleting dumps).
- `/Users/rushil/agentic-finance-platform` is reference only. Read it; never modify it.

## Git
- When the user says commit, commit and then push in the same step (push after every commit).
  Never commit or push without that instruction.
- No Co-Authored-By or Claude-Session line in commit messages.
- Update `docs/STATUS.md` at the end of every session.

## Plans
- Plan-mode files save to `plans/` (`plansDirectory` in `.claude/settings.json`).
- When a plan is approved, rename it to `plans/phase-N-<topic>.md`
  (e.g. `plans/phase-1-import-pipeline.md`) and refer to it only by that name.

## Servers
- After editing code, restart the affected servers before verifying.
- Leave dev servers running unless told otherwise, and say which ones are up.

## How to run (available once Phase 0 is built)
- Start everything: `make up` (`docker compose up -d --build --wait`)
- Host ports: Postgres 5433 · Redis 6380 · API 8001 · Web 5174
  (the old project uses 5432 / 8000 / 5173, so both can run at once)
- Health: `curl localhost:8001/health`
- Python tests: `make test` (uv run pytest; excludes the `gate` and `live` markers)
- Web tests: `make test-web` · Lint: `make lint`
- Phase gate: `make gate PHASE=0`
- Tests marked `live` call real external APIs; run them only when asked, never in CI.
