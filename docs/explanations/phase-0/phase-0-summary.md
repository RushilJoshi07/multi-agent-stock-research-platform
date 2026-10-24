# Phase 0 summary: Setup

Gate passed 2026-10-24 on commit `4c3aa31`. Step explainers:
[Claude Code setup](step-01-claude-code-setup.md) ·
[health check and test setup](step-03-health-check.md) ·
[web app and the 14-day rule](step-04-web-app.md) ·
[Compose stack and the gate](step-05-compose-and-gate.md) ·
[CI](step-06-ci.md). Decision notes: `docs/decisions/0001`–`0007`.

## 1. What this phase does, and what it doesn't

Phase 0 builds the ground every later phase stands on, and nothing else. At the end of it:

- One command, `make up`, starts four services (Postgres, Redis, the FastAPI API and the React
  dev server) and returns only once each reports healthy.
- `GET /health` makes a real query against Postgres and a real `PING` against Redis, and answers
  503 with the reason when either fails.
- Every push and pull request runs CI on GitHub: the Python tests against real Postgres and Redis
  with the network blocked, the web app's lint, typecheck, tests and build, and a check that
  every locked dependency is at least 14 days old.
- Claude Code sessions start from the same committed rules, permissions and commit-log hook,
  so the way of working is part of the repo rather than of one chat.

The plan's "Done when" is: *one command starts the database, Redis, API and web app, the health
check is green, and CI passes.* All three are now true and evidenced (section 5).

What it doesn't do: there's no data, no schema, no agents, no trading code and no UI beyond one
line of text. None of the three sacred gates (no lookahead, no invented numbers, code acts) is
tested yet, because nothing exists that could break them. Phase 0 only builds the machinery
those tests will run on. The images are development images (root user, bind-mounted code,
tags rather than digests); production is Phase 6.

## 2. How the pieces fit, and why the boundaries sit where they do

The phase is five components, built in an order where each one is verified by the next.

**Working environment first (step 1–2).** CLAUDE.md, the rule files, `.claude/settings.json`
permissions and the commit-log hook came before any application code. The reason is that every
later step is written by a Claude Code session, and the rules have to exist before the code they
govern. Writing them afterwards means the first steps break rules nobody had written yet.
The boundary is "files in the repo", not "instructions in a chat", because up to three parallel
sessions must behave the same.

**Services and the test setup next (step 3).** Postgres and Redis went into Compose, and
`/health` was written with its tests against those real services, not mocks. This step also
built the two guards every later test inherits: one stops any test from reaching port 5432
(the old project's database, which runs on the same machine), and pytest-socket blocks every
outbound network connection except localhost. They sit in `tests/conftest.py` and
`pyproject.toml`'s `addopts` (pytest's always-on options), so a test can't forget to use them.

**The web app and the dependency rule (step 4).** The frontend only proves the toolchain works
and reaches the API through Vite's proxy. The 14-day rule landed in the same step because that
was when the second lockfile appeared, and a rule covering only one lockfile would leave the
other half of the tree open.

**One command (step 5).** The API and web app joined Compose with health checks that require a
real answer (`/health` must return 200; the web server must serve its page), and the Makefile
became the single front door. The gate test drives `make up` from the outside, the way a person
does, rather than calling internals.

**CI last (step 6).** CI repeats the same commands as the Makefile on a clean machine: the same
`uv run pytest` (so the same `addopts`), the same npm scripts, the same host ports. It came last
because it can only check things that already work locally; writing it first would have meant
debugging the code and the workflow at once.

The thread through all five is **one source of truth per fact**. Ports live in decision 0005
and the settings defaults, and CI uses the same ones. The test filter and network guard live in
`addopts`, and both `make test` and CI call plain `uv run pytest`. The Node version lives in
`.nvmrc`, and CI, Docker and the npm pre-scripts all read or check it. The Python version lives in
`.python-version`. Wherever a fact was copied into a second place, it could drift. Where that
couldn't be avoided (the Docker image's Node tag), only part of it is checked: the npm
pre-scripts and `engine-strict` stop a wrong Node major, but the exact 24.21.0 matches only
because it's pinned in each place.

## 3. Cross-component decisions and rejected alternatives

**Real services everywhere, never mocks or SQLite.** Chosen: real Postgres 16 and Redis 7 in
Compose locally and as service containers in CI, on the same ports. Rejected: SQLite or mocked
clients for speed. SQLite differs from Postgres in types, locking, time zones and SQL dialect, so
a test could pass on SQLite and fail on Postgres; the whole project's credibility rests on
database queries ("as of" filters for Sacred Gate 1) being right. Cost: tests need Docker
running locally, and CI starts two service containers per run. Changing later would mean
rewriting every database test.

**Host ports offset by one (5433 / 6380 / 8001 / 5174), everywhere including CI**
([0005](../../decisions/0005-host-ports.md)). The old project runs on the same machine and Phase
1 restores its database into Fathom's, so both must be up at once. Rejected: stopping the old
project (breaks the restore); standard ports with switching (an easy way to point a command at
the wrong database); standard ports in CI only (needs a CI exception in the 5432 guard, and
exceptions are where safety checks get turned off by accident).

**The 14-day rule across the whole supply chain**
([0007](../../decisions/0007-dependency-age-14-days.md)). It covers Python and npm packages
including transitive ones, both runtimes, uv, and the GitHub Actions. Rejected: always-latest
(no buffer against a broken or compromised release), direct pins only (most poisoned releases
land in transitive packages), a rolling "14 days" (the cutoff moves without a commit). Cost:
several tools sit a release or two behind (ruff, Node, setup-uv, setup-node), and a security fix
inside the window needs a recorded exception.

**Toolchain from official archives with checksums, not Homebrew or `curl | sh`**
([0003](../../decisions/0003-uv-lockfile.md), [0007](../../decisions/0007-dependency-age-14-days.md)).
Homebrew only offered versions inside the 14-day window, and `curl | sh` runs whatever the server
returns. Cost: one manual install per tool, and a `~/.zprofile` edit outside the repo.

**Gates as tests that must be able to fail.** The gate checks `/health` turns red when Redis is
stopped, and a pytest hook fails the run if any gate test was deselected or skipped. Rejected:
a gate that only checks the green path. A health check hard-coded to return "ok" passes that.

**Rules enforced by configuration, not by instructions.** Reading `.env` is denied in
permissions rather than "please don't"; the network is blocked in pytest rather than "don't call
APIs in tests"; actions are pinned by SHA rather than "trust the tag". The same principle drives
the sacred gates later: make the wrong thing impossible, not discouraged.

## 4. Concepts introduced across the phase

**Supply-chain risk.** Your code is only as trustworthy as everything it runs: packages, tools,
CI actions, base images. Phase 0 defends at several layers: pinning (exact versions, lockfiles,
commit SHAs, checksums), delay (14 days), least privilege (CI's read-only token, no secrets) and
isolation (no network in tests). The gap left on purpose: Docker images are pinned by tag, not
digest, and that's a recorded Phase 6 decision.

**Mutable vs immutable references.** A version range, a git tag or a Docker tag can point at
different content tomorrow; an exact lockfile entry, a commit SHA or a checksum can't. Phase 0
moves almost everything to the immutable kind, and lists what's left.

**Reproducibility.** The same commit should behave the same on the Mac, in Docker and in CI.
That's why the Python, Node and uv versions are identical across all three and why installs
are lockfile-exact (`uv sync --locked`, `npm ci`). Later phases depend on this: a backtest that
gives different numbers on two machines can't be graded.

**Testing from the outside.** The gate drives `make up` and HTTP requests exactly as a person
would. A test that imports the app's internals can pass while the real entry point is broken.

## 5. Verification: the full gate

| Condition | How checked | Result | Evidence |
|---|---|---|---|
| One command starts the database, Redis, API and web app | Gate tests `test_one_command_starts_the_stack`, `test_all_four_services_are_running_and_healthy` | PASS | `make gate PHASE=0`: both PASSED; all four services `running (healthy)` |
| The health check is green | Gate tests `test_health_is_green`, `test_health_goes_red_when_redis_stops`, plus the web proxy tests | PASS | `/health: {'status': 'ok', ... 'postgres': {'ok': True, 'version': '16.14'} ... 'redis': {'ok': True}}`; with Redis stopped: `'status': 'degraded'`, redis `ok: False` |
| CI passes | GitHub Actions run on `4c3aa31` | PASS | User confirmed; GitHub API: backend, web, dependency-age all `success`. [Run 40123000260](https://github.com/RushilJoshi07/multi-agent-stock-research-platform/actions/runs/40123000260) |

The recorded gate run started from nothing. First, read-only queries confirmed there was
nothing to lose: `fathom` and `fathom_test` each held 0 tables (0 non-system relations of any
kind), and Redis held 0 keys. Then `docker compose down -v` removed every container, the network
and both data volumes. This was approved once, because after Phase 1's restore the volumes will
hold price history and deleting them stops being cheap. From that empty state,
`make gate PHASE=0` ended with `6 passed` in 13.60 s and `GATE CHECK: 6 gate tests ran, 0
deselected, 0 skipped`, make exit 0. The Postgres log shows the empty volume being initialized
and the init script running again:

```
/usr/local/bin/docker-entrypoint.sh: running /docker-entrypoint-initdb.d/01-create-test-db.sql
CREATE DATABASE
PostgreSQL init process complete; ready for start up.
```

The new volume's creation time was 2026-10-24T20:22:29Z, `pg_database` listed both `fathom` and
`fathom_test`, and `make test` passed 7 tests against the recreated `fathom_test`. An earlier
run the same day, against the stack that was already up, also passed 6 of 6.

What the gate proves: the stack starts with one command from empty volumes and every service
reports healthy on its own check; the test database is created by the init script, not left
over from an earlier run; `/health` depends on Postgres and Redis for real (stopping Redis makes it go
red, so it isn't hard-coded); the web app is served and reaches the API through its proxy; and
the same tests, lint and build pass on a clean Linux machine with no secrets and no network.

What it does **not** prove:
- **A cold build.** The volumes were empty, but the Docker images and their build cache were
  not deleted, so the run doesn't show a first-ever build on a new machine (pulling images,
  installing packages from scratch).
- **That the gate runs in CI.** It needs Docker Compose and the full stack, so it's run by hand.
  CI covers the unit tests, not the gate.
- **Anything about the sacred gates.** No lookahead, no invented numbers and code acts are
  **not verified at all** in Phase 0, because there's no data, agent or trading code yet. Phase 0
  only provides the tools their tests will use: real Postgres for "as of" queries, pytest-socket
  so tests can't fetch live data, and gate tests that must be able to fail.
- **Production readiness.** Development images only: root user, bind mounts, tag-pinned images.

## 6. Interview defense

**"Phase 0 is just setup. Why spend days on it?"** Because each later phase's evidence depends
on it. Phase 3's claim "the agent never saw the future" is only as good as the test setup that
checks it, and that setup (real Postgres, network blocked, tests that can fail) is what Phase 0
built. If the foundation is wrong, every later result is suspect, and finding that out in Phase
5 costs far more than the days spent here.

**"Why didn't you just use SQLite for tests? It's faster."** The project's core correctness
claim is in database queries: "as of time T, what was known?" SQLite handles time zones, types
and SQL differently from Postgres. A test passing on SQLite says nothing about production. The
cost is Docker in the loop and about 30 seconds in CI.

**"How do you know the gate isn't passing because of leftovers from earlier runs?"** (the hard
one) Because the recorded run started from empty volumes. The first gate run that day was
against a stack that had been up for days, and I flagged that as a gap: the test database
could have been left over, and the init script that creates it had run only once. Before the
Phase 1 restore made deleting data expensive, I checked read-only that both databases held no
tables, deleted the volumes with explicit approval, and re-ran the gate. The Postgres log shows
the init script creating `fathom_test` again. What's still not covered is a first-ever build
on a new machine, because the images and build cache stayed.

**"Isn't the 14-day rule paranoid?"** It's cheap insurance. Most compromised releases are
caught within days, and the cost is running a release or two behind. Security fixes have a
documented exception path. Without it, one bad transitive package could ship into CI the day
it's published.

**Honest weaknesses:**
- The sacred gates have no tests yet; Phase 0 can't have them.
- The recorded gate started from empty volumes but reused built images, so a first build on
  a new machine is untested.
- Docker images are pinned by tag, and the Node and Python downloads in CI aren't pinned by
  checksum the way uv's is.
- Several known issues carry forward (section 7): the `DATABASE_URL` guard covers only the test
  database's port; the commit log will conflict across parallel worktrees; `enable_socket` can
  bypass pytest-socket; and the GitHub repo is public, while the plan said private.

## 7. What comes next, and what breaks downstream if Phase 0 is wrong

Phase 1 imports the foundations from the old project: the price pipeline, the database restore
(decision 0002: Postgres 16, price and universe tables only) and the number checker. Two Phase 0
items must be closed first. The 5432 guard must also cover the app's own `DATABASE_URL`, by host
and port together, before the restore. And the commit-log merge-conflict fix must be decided
before the first parallel worktree split.

If Phase 0 were wrong, the damage shows up later and quietly:
- If the 5432 guard failed, a test or the restore could write into the old project's database.
- If pytest-socket weren't in force, a Phase 2 test could call Finnhub or Bedrock in CI, spending
  money and making results depend on the day the test ran.
- If CI and local disagreed (different ports, Python or filters), a green CI run would stop
  meaning "the code on `main` works", and every parallel branch's merge check in Phase 1 would
  be meaningless.
- If the health check weren't real, Phase 4's jobs and Phase 6's monitoring would report a
  healthy system while the database was down.
