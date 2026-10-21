# Fathom status

Last updated: 2026-10-21 · by: Claude Code, Phase 0 session

**Current phase:** 0 — Setup

## Done
- Phase 0 proposal approved with changes (2026-10-19).
- Step 1: ignore files, `.env.example`, CLAUDE.md, this file, `docs/ideas.md`,
  decisions 0001–0006. Commit `79d788b`, pushed.
- Step 2: `.claude/` settings, commit-log hook, rules, skills, agents. Commit `9db2fd7`, pushed.
  The hook ran live on that commit and wrote its own stub.
- Step 3: Python project (uv, exact pins, `uv.lock`), `GET /health`, postgres + redis services
  in `compose.yaml`, 7 tests against real services, pytest-socket network guard, 5432 guard.
  Commit `a8f660e`, pushed. Verified: 7 passed, ruff check and format clean, guard stopped
  three bad `DATABASE_URL_TEST` values. Explainers: `step-01-claude-code-setup.md`,
  `step-03-health-check.md`.

## In progress
- Step 4: empty React app in `web/` plus the 14-day dependency rule (decision 0007,
  `.claude/rules/dependencies.md`, `scripts/check_dependency_age.py`). Built and checked, not
  committed: lint, typecheck, 5 Vitest tests and build pass on Node 24.21.0. Both lockfiles are
  within the 2026-10-06T23:59:59Z cutoff. `/api/health` returns 200 through the Vite proxy with
  uvicorn on 8001. ruff downgraded to 0.16.10 and limited to Python files.

## Next
- Step 5: `api` and `web` services in `compose.yaml`, Dockerfiles, Makefile (`make up`), Phase 0
  gate test. No `~/.aws` mount until Phase 3. Node image `node:24.21.0-bookworm-slim`; the web
  container must run Vite with `--host` (it listens on localhost only by default) and set
  `API_PROXY_TARGET=http://api:8000` and `WEB_PORT=5173`. Makefile npm targets use
  `NODE24_BIN` (default `$HOME/.local/node/v24.21.0/bin`). The gate run must show the gate tests actually ran
  and weren't deselected: `addopts` has `-m 'not gate and not live'`, and we rely on a later
  `-m gate` overriding it.
- Step 6: CI. Look up current action major versions; service containers on 5433/6380; update
  decision 0005's CI line.
- Step 7: Phase 0 gate (`make gate PHASE=0` + CI green on `main`, checked by the user
  on the Actions page).

## Gate results
| Phase | Result | Date | Evidence |
| --- | --- | --- | --- |

## Known issues
- `verdict.py` in the old repo imports old charter/hypothesis/verdict models and
  `llm_client`. Phase 1 must extract the number checker, not copy the file.
- The old `data_pipeline/db/init_db.py` imports `agentic_core.db.models`. Remove on import.
- A single `docs/explanations/phase-N/commit-log.md` will cause merge conflicts once parallel
  worktrees both commit. Decide the fix (e.g. one log file per commit) before the first
  parallel split in Phase 1.
- arq's maintenance status is unverified. Check before Phase 4 starts and report.
- `plansDirectory` support in Claude Code 2.1.281 is unverified. In this session the plan file
  stayed at `~/.claude/plans/pasted-content-id-5a72-we-re-starting-reactive-dijkstra.md` and
  `plans/` was never created; that file existed before the setting, so this doesn't settle it.
  Check in a new session's first plan.
- `fsevents@2.3.3` (macOS file watcher, pulled in by the web tooling) has an install script that
  npm 11 didn't run because it isn't approved (`npm install-scripts approve`). Lint, typecheck,
  tests, build and the dev server all worked without it. Not approved; decide if file watching
  misbehaves.
- Live-test gap: `Bash(uv run pytest *)` in the allow list also matches `uv run pytest -m live`.
  Fix in Phase 2, with the first live test: (1) live tests skip in code unless
  `FATHOM_ALLOW_LIVE=1` is set, so the allow rule alone can never run them; (2) unverified whether
  a command prefixed with that variable falls outside `Bash(uv run pytest *)` and prompts. Test it
  when the first live test exists. Also: a test marked `enable_socket` bypasses pytest-socket
  entirely (read in pytest-socket 0.8.1's source), so the fix must make `enable_socket` fail
  unless the test is also marked `live`, and `live` stays behind `FATHOM_ALLOW_LIVE=1`.
- The project skills (`explanation-writer`, `phase-gate`, `session-handoff`) were not available
  as skills in the session that created them ("Unknown skill"); they were followed from their
  files instead. Unverified whether a new session loads them. Check at the next session start.
- The 5432 guard in `tests/conftest.py` covers `DATABASE_URL_TEST` only, not the app's own
  `DATABASE_URL`. If `.env` pointed `DATABASE_URL` at port 5432, the running API would connect to
  the old database. Close before Phase 1's restore.
- Tests print a `StarletteDeprecationWarning`: Starlette's test client wants `httpx2` instead of
  `httpx`. Tests pass; not acted on (it would add a dependency). Decide before it becomes an error.

## Servers currently up
- Fathom Postgres (`postgres:16.14-bookworm`) on 127.0.0.1:5433, healthy.
- Fathom Redis (`redis:7.4.11-alpine`) on 127.0.0.1:6380, healthy.
  Both checked with `docker compose ps` at handoff (up about 2 hours). Left running.
- Vite dev server (`npm run dev`, Node 24.21.0) on localhost:5174, proxying `/api` to 8001.
- uvicorn (`api.main:app`) on 127.0.0.1:8001, using `DATABASE_URL`'s default (`fathom` on 5433).
- The old project's Postgres (5432) and API (8000) were not touched by Fathom.
