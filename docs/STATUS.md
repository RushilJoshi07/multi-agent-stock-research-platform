# Fathom status

Last updated: 2026-10-20 · by: Claude Code, Phase 0 session

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
- Nothing. Session handed off after step 3.

## Next
- Step 4: empty React app in `web/` (React 19, TypeScript 5.9, Vite 8, Tailwind 4, npm,
  Node 24), Vite proxy `/api/*` to the API, one Vitest smoke test. Approach first, no code
  before approval.
- Step 5: `api` and `web` services in `compose.yaml`, Dockerfiles, Makefile (`make up`), Phase 0
  gate test. No `~/.aws` mount until Phase 3. The gate run must show the gate tests actually ran
  and weren't deselected: `addopts` has `-m 'not gate and not live'`, and we rely on a later
  `-m gate` overriding it.
- Step 6: CI. Look up current action major versions; service containers on 5433/6380; update
  decision 0005's CI line.
- Step 0 (deferred by the user): copy the approved proposal to `plans/phase-0-setup.md`.
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
- `plansDirectory` support in Claude Code 2.1.281 is unverified. Confirm in the next
  plan-mode session.
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
- The old project's Postgres (5432) and API (8000) were not touched by Fathom.
