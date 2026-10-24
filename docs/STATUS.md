# Fathom status

Last updated: 2026-10-22 · by: Claude Code, Phase 0 session

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
- Step 4: empty React app in `web/` plus the 14-day dependency rule (decision 0007,
  `.claude/rules/dependencies.md`, `scripts/check_dependency_age.py`). Commit `b8655b2`, pushed.
  Lint, typecheck, 5 Vitest tests and build pass on Node 24.21.0; both lockfiles within the
  2026-10-06T23:59:59Z cutoff; `/api/health` 200 through the Vite proxy; page checked by hand in
  a browser once.
- Step 5: full Compose stack, Makefile, Phase 0 gate test with the deselection check, uv 0.12.23
  and Python 3.13.16. Commit `b2cdaa9`, pushed. `make gate PHASE=0`: 6 passed, "6 gate tests ran,
  0 deselected, 0 skipped".
- Step 5 follow-up:
  - the web container bind-mounts only `web/src` and `web/index.html`, with `node_modules` and
    config in the image;
  - `make up` sets `BUILDX_NO_DEFAULT_ATTESTATIONS=1`, so a second `make up` recreates nothing;
  - `.dockerignore` excludes `.env` files at any depth;
  - the leftover anonymous volumes and the `alpine:3.22` image were deleted;
  - the step 5 explainer, and the CLAUDE.md image-pull rule.

  Commit `6578dd5`, pushed.
- `.vscode/settings.json` committed with `python.terminal.useEnvFile: false`, so VS Code terminals
  never load `.env`. Commit `4aa17d5`, pushed.

## In progress
- Nothing. Session handed off after step 5.

## Next
- **Step 6: CI** (`.github/workflows/ci.yml`). Approach first; no code before approval.
  - Look up the current major versions of the GitHub actions; don't use remembered ones.
  - **backend job:**
    - uv pinned to 0.12.23 through `setup-uv`;
    - Python from `.python-version` (3.13.16);
    - Postgres (`postgres:16.14-bookworm`) and Redis (`redis:7.4.11-alpine`) as service
      containers mapped to host ports 5433 and 6380, so the 5432 guard needs no CI exception;
    - `uv sync --locked`, ruff check and format, then `pytest -m "not gate and not live"` with
      pytest-socket.
  - **web job:** Node from `.nvmrc` (24.21.0), `npm ci`, then lint, typecheck, test and build.
  - **dependency-age job:** a separate job that runs `scripts/check_dependency_age.py`, apart from
    the test jobs, so pytest-socket stays in force for tests.
  - No secrets; nothing in CI calls Bedrock, Finnhub, Alpaca or any paid API.
  - Update decision 0005's CI line, which still says CI uses the standard ports.
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
- The web container bind-mounts the single file `web/index.html`. Editors that save by writing a
  new file and renaming it replace the file on the Mac, but the container keeps seeing the old
  one until `make up` or a restart. `web/src` is a directory mount and isn't affected.
- Phase 6: production images keep build attestations (provenance). `BUILDX_NO_DEFAULT_ATTESTATIONS=1`
  in `make up` is for local development images only.
- Phase 6 decision: pin Docker images by digest (`image@sha256:...`). Tags such as
  `postgres:16.14-bookworm` can be re-pushed by Docker Hub, so a tag isn't immutable.
- `plansDirectory` support in Claude Code 2.1.281 is unverified. In this session the plan file
  stayed at `~/.claude/plans/pasted-content-id-5a72-we-re-starting-reactive-dijkstra.md` and
  `plans/` was never created; that file existed before the setting, so this doesn't settle it.
  Check in a new session's first plan.
  Update 2026-10-22 (step 6 session): still unsettled. No plan file was written anywhere this
  session: `plans/` doesn't exist and `~/.claude/plans/` holds only the 2026-10-20 file above.
  Claude got no Plan-mode instructions or plan-file path, so the session apparently never ran in
  Plan mode. Next test: start a session in Plan mode, have Claude write a plan, then check
  `plans/` and `~/.claude/plans/`.
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
  the old database. Close before Phase 1's restore. Inside Docker the API legitimately connects
  to `postgres:5432`, so the guard must check host and port together, not port alone.
- Tests print a `StarletteDeprecationWarning`: Starlette's test client wants `httpx2` instead of
  `httpx`. Tests pass; not acted on (it would add a dependency). Decide before it becomes an error.

## Servers currently up
The full Compose stack (checked with `make ps` at handoff on 2026-10-22, all healthy, up about
23 hours), left running:
- postgres (`postgres:16.14-bookworm`) on 127.0.0.1:5433
- redis (`redis:7.4.11-alpine`) on 127.0.0.1:6380
- api (`fathom-api`: uvicorn with reload, Python 3.13.16) on 127.0.0.1:8001
- web (`fathom-web`: Vite, Node 24.21.0) on 127.0.0.1:5174

The old project's Postgres (5432) and API (8000) were not touched by Fathom.
