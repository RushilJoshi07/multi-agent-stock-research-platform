# Phase 0 · Step 6: Continuous integration (CI)

Commit `4c3aa31`. Decision notes: [0005 host ports](../../decisions/0005-host-ports.md),
[0007 dependency age](../../decisions/0007-dependency-age-14-days.md). Rule file:
`.claude/rules/dependencies.md`.

## 1. What this does, and what it doesn't

**Continuous integration (CI)** means a machine re-runs the project's checks on every change,
so "it works on my laptop" is never the evidence. This step adds one GitHub Actions workflow,
`.github/workflows/ci.yml`. It runs on every push to `main` and on every pull request, as three
jobs that run in parallel:

- **backend**: starts real Postgres and Redis next to the job, installs the locked Python
  dependencies, runs ruff (the linter and formatter check), then runs the test suite with the
  network blocked except for localhost.
- **web**: installs the locked npm packages and runs the same lint, typecheck, test and build
  commands as on the laptop.
- **dependency-age**: runs `scripts/check_dependency_age.py`, which fails if any locked package
  was published after the 14-day cutoff.

The workflow has no secrets and calls no paid API. Its token can read the repository and do
nothing else. Every third-party action is pinned to an exact commit, and each one's release is
older than the same cutoff that governs the lockfiles.

The first push of `4c3aa31` was rejected: the personal access token git used lacked the
`workflow` scope, which GitHub requires before a token may create or change a file under
`.github/workflows/`. The user pushed the commit with a new token that has the scope. The first
run ([run 40123000260](https://github.com/RushilJoshi07/multi-agent-stock-research-platform/actions/runs/40123000260))
passed: backend, web and dependency-age all succeeded on `4c3aa31`. That run is part of the
Phase 0 gate evidence.

What it doesn't do:
- It doesn't run the `gate` tests (they need `make up` and Docker Compose, which this workflow
  doesn't start) or the `live` tests (they call real APIs and cost money).
- It doesn't build or test the Docker images. Production images are Phase 6.
- It doesn't check the action pins automatically. They were checked by hand; automating that is
  parked in `docs/ideas.md`.

## 2. The workflow, explained

### Header, triggers and permissions

```yaml
on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read
```

`push` to `main` checks what actually landed. `pull_request` checks a branch before it merges,
which is what the parallel-work rule needs ("every branch runs the full test suite before it
merges"). Pushes to other branches don't trigger a run on their own. Without that filter, a
branch with an open pull request would run every check twice per push.

`permissions: contents: read` sets what the automatic `GITHUB_TOKEN` can do. GitHub gives every
job this token, and by default it may get write access (depending on repository settings) to
code, issues, pull requests and more. Setting the permission at the top level means every job
inherits read-only, and no job asks for more. If a pinned action or a compromised dependency
ran malicious code inside a job, the most it could do with that token is read code it can
already read. It couldn't push a commit, change a release or tamper with a pull request.

The workflow deliberately uses `pull_request`, not `pull_request_target`. The second runs with
the base repository's permissions and secrets even for pull requests from forks, and is a
well-known way to leak them. Plain `pull_request` from a fork gets a read-only token and no
secrets.

### The backend job

```yaml
  backend:
    runs-on: ubuntu-24.04
    timeout-minutes: 15
```

`ubuntu-24.04` instead of `ubuntu-latest`: `latest` moves to a new Ubuntu release when GitHub
decides, so a run could start failing with no change in the repo. A named image changes only
in a reviewed commit. `timeout-minutes: 15` caps a hung job. GitHub's default is 6 hours, which
on a private repo would eat the free minutes.

```yaml
    services:
      postgres:
        image: postgres:16.14-bookworm
        env:
          POSTGRES_USER: fathom
          POSTGRES_PASSWORD: change-me-local
          POSTGRES_DB: fathom_test
        ports:
          - 5433:5432
        options: >-
          --health-cmd "pg_isready -U fathom -d fathom_test"
          ...
      redis:
        image: redis:7.4.11-alpine
        ports:
          - 6380:6379
```

**Service containers** are Docker containers GitHub starts beside the job before any step runs,
and removes afterwards. They're the CI equivalent of the Compose `postgres` and `redis`
services, with the same image tags. The testing rule says database code is tested against real
Postgres, not SQLite or mocks, and this is how CI keeps that promise.

The ports are the same host ports as on the laptop: 5433 and 6380. That choice carries the most
weight in this file. The test suite's settings default to `localhost:5433/fathom_test` and
`localhost:6380` when no `.env` exists, and CI has no `.env`. So the job needs no `env:` block
at all, and the guard in `tests/conftest.py` (which stops the run if `DATABASE_URL_TEST` uses
port 5432, the old project's database) runs unchanged. Had CI used the standard 5432, the guard
would need a CI exception, and an exception that turns a safety check off in one environment is
how a safety check gets turned off by accident in another.

`POSTGRES_DB: fathom_test` replaces the local init script. Locally,
`docker/postgres/init/01-create-test-db.sql` creates `fathom_test` the first time the volume
is created. Service containers start before the repository is checked out, so there's no file
to mount. Making `fathom_test` the database the image creates on startup gives the tests what
they need without an extra `psql` step. The `fathom` database doesn't exist in CI, which is
fine: no test uses it, and if a future test did by mistake, it would fail loudly here.

The password is the `.env.example` placeholder. It's not a secret: the container is reachable
only from the job's own machine and is destroyed when the job ends.

The health options make GitHub wait until `pg_isready` and `redis-cli ping` succeed before the
first step runs. Without them, a fast job could reach pytest while Postgres is still
initializing and fail with "connection refused", a flaky failure that has nothing to do with
the code.

```yaml
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1, 2026-07-20
        with:
          persist-credentials: false
```

`actions/checkout` clones the repository into the job. By default it writes the job's token
into `.git/config` so later steps can run `git push`. Nothing here pushes, so
`persist-credentials: false` keeps the token off disk, where any later step (including code
from a dependency) could read it.

The long hex string is a full commit SHA, explained in section 3.

```yaml
      - uses: astral-sh/setup-uv@c18668ad3cf93ea998bef934396af7bb5c839dc7 # v10.2.0, 2026-09-21
        with:
          version: 0.12.23
          checksum: 9167d72b3319674b6303c4cbe071854bba13ebdf3d76b1a7cbdc175471fb66d6
```

`setup-uv` downloads uv and puts it on the job's path. `version: 0.12.23` is the same uv as on
the laptop (decision 0007 puts uv under the 14-day rule). The `checksum` is the SHA-256 that
the uv project publishes next to `uv-x86_64-unknown-linux-gnu.tar.gz` for 0.12.23. If the
downloaded archive's hash doesn't match, the step fails. This is the same rule that applies on
the laptop: tools installed outside a package manager come from the official archive with its
published checksum verified.

```yaml
      - run: uv sync --locked
      - run: uv run ruff check
      - run: uv run ruff format --check
      - run: uv run pytest
```

`uv sync --locked` installs exactly what `uv.lock` says, and fails if the lockfile is out of
date with `pyproject.toml` instead of quietly re-resolving. A quiet re-resolve could pull in a
package newer than the cutoff. uv also reads `.python-version` and installs Python 3.13.16
itself, the same way the laptop's 3.13.16 was installed, which is why there's no
`actions/setup-python` step.

The two ruff commands are the Python half of `make lint`. `uv run pytest` is exactly
`make test`, and that's deliberate. The marker filter and the network guard live in
`pyproject.toml`'s `addopts`:

```toml
addopts = "-m 'not gate and not live' --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,::1"
```

so CI and the laptop can't disagree about which tests run or whether the network is blocked.
Writing `-m "not gate and not live"` again in the workflow would create a second copy that
could drift from the first.

### The web job

```yaml
  web:
    defaults:
      run:
        working-directory: web
    steps:
      - uses: actions/checkout@... # v7.0.1
      - uses: actions/setup-node@820762786026740c76f36085b0efc47a31fe5020 # v7.0.0, 2026-07-14
        with:
          node-version-file: .nvmrc
          cache: npm
          cache-dependency-path: web/package-lock.json
      - run: npm ci
      - run: npm run lint
      - run: npm run typecheck
      - run: npm run test
      - run: npm run build
```

`defaults.run.working-directory: web` runs every `run:` step inside `web/`, so each step doesn't
need its own `cd web`. It doesn't apply to `uses:` steps, which is why `.nvmrc` (at the
repository root) and `web/package-lock.json` are written as paths from the root.

`node-version-file: .nvmrc` reads 24.21.0 from the same file that documents the laptop's Node,
so there's one place to change it. `cache: npm` keeps npm's download cache between runs,
keyed on the lockfile's hash. It only saves download time; `npm ci` still installs from the
lockfile every run.

`npm ci` is the lockfile-exact install. It deletes `node_modules` and installs exactly
`package-lock.json`, failing if the lockfile and `package.json` disagree. `npm install` would
instead update the lockfile to match, which is the wrong behavior for a check. Each `npm run`
step first runs `scripts/check-node.mjs` (npm's "pre" scripts), so a wrong Node major fails
fast here too.

`fsevents`, the macOS file watcher with an unapproved install script, is an optional
dependency for macOS only, so it isn't installed on the Linux runner.

### The dependency-age job

```yaml
  dependency-age:
    steps:
      - uses: actions/checkout@... # v7.0.1
      - uses: astral-sh/setup-uv@... # v10.2.0
        with:
          version: 0.12.23
          checksum: 9167d72b...
      - run: uv run --locked python scripts/check_dependency_age.py
```

The script asks PyPI and the npm registry for the publish date of every package in both
lockfiles. That needs the network, and the test jobs block the network. Putting the script in
its own job, with no pytest, keeps pytest-socket in force for every test without exception.
`--locked` stops `uv run` from silently updating the lockfile before running the script.

Boilerplate skipped: the `name: CI` line and the header comment.

## 3. Decisions and rejected alternatives

**Pin actions to full commit SHAs, not tags.** `uses: actions/checkout@v7` looks pinned but
isn't. A git tag is a movable pointer: whoever controls the action's repository can move `v7`
(or even `v7.0.1`) to a different commit, and every workflow using the tag runs the new code on
its next run. This isn't hypothetical. In March 2025 the popular `tj-actions/changed-files`
action was compromised and its version tags were repointed to a malicious commit that printed
CI secrets into public logs; thousands of repositories that "pinned" a tag ran it. A 40-character
commit SHA can't be moved: it names the content itself. The comment (`# v7.0.1, 2026-07-20`)
keeps it readable and records which release was reviewed.

Alternatives rejected:
- *Major tag (`@v7`).* Silent updates of code that runs with the job's token.
- *Exact tag (`@v7.0.1`).* Looks immutable but can still be moved or deleted and recreated.
- *Short SHA (e.g. 7 characters).* A prefix can match more than one commit, and an attacker can
  push a commit whose SHA starts with the same characters. Only the full 40 characters are
  unambiguous.
- *Copy the actions into this repo (vendoring).* Most immutable, but the vendored copies have to
  be updated by hand, and it adds thousands of lines of bundled JavaScript to review.

Cost to change later: bumping an action means looking up the new release's SHA and date and
editing three lines. That's manual today; the idea parked in `docs/ideas.md` would automate the
check.

**Apply the 14-day rule to actions too.** An action is code that runs inside CI with the
repository checked out, so the reason for the rule (a fresh release is the most likely to be
broken or compromised, and most bad releases are caught within days) applies just as it does to
a PyPI package. The cutoff used is the lockfiles' absolute one, `2026-10-06T23:59:59Z`, not
"14 days before today", so there's a single date to reason about. The result:

| Action | Pinned | Released | Newer releases skipped |
|---|---|---|---|
| actions/checkout | v7.0.1 | 2026-07-20 | none (newest) |
| astral-sh/setup-uv | v10.2.0 | 2026-09-21 | v10.3.0 (10-09), v10.3.1 (10-21), v10.3.2 (10-22) |
| actions/setup-node | v7.0.0 | 2026-07-14 | v7.1.0 (10-08) |

Each pin was verified by asking the GitHub API which commit the tag points to; all three tags
point straight at a commit (not through an annotated tag object), and each SHA in the workflow
matches. All three are JavaScript actions (`using: node24` with a bundled `dist/`), not
composite actions, so they don't pull in further actions by tag. A composite action could
quietly reintroduce an unpinned dependency.

**Drop `actions/setup-python`.** The obvious pattern is setup-python, then install uv. But uv
already installs the exact Python in `.python-version`, and that's how the laptop got 3.13.16.
Dropping the action means one fewer third-party action with access to the job, and CI and the
laptop get Python from the same source. setup-python's newest release (v7.1.0) was also
published on 2026-10-22, inside the cutoff window, so it would have been an older release
anyway.

**Same host ports as local (5433 / 6380), not the standard ports.** Rejected: standard ports
plus `DATABASE_URL_TEST` and `REDIS_URL` set in the workflow. That works, but it needs a CI
exception in the 5432 guard (or a guard that knows it's in CI). Decision 0005 originally said CI
would use the standard ports; this step changed that line.

**`POSTGRES_DB: fathom_test` rather than a `psql` step.** A step running `CREATE DATABASE`
would mirror the local init script more literally, but needs a Postgres client on the runner and
a connection string, and gives a second way for setup to fail. The image's own variable does it
in one line.

**A separate dependency-age job rather than a pytest test.** A test would need the network, so
it would need `enable_socket`, which bypasses pytest-socket entirely (a known issue in
STATUS.md). Keeping the network-using check out of pytest keeps the "no network in tests" rule
absolute.

**`contents: read` at the workflow level rather than per job.** Per-job blocks would also work,
but a new job added later without its own block would get the default token. A top-level setting
applies to every job, including future ones.

## 4. Concepts introduced

**Supply-chain attack.** Instead of attacking your code, an attacker compromises something your
code trusts and runs automatically: a package, a build tool, a CI action. CI is a prime target
because it runs third-party code with credentials. The defenses here are layered: pinning (the
code can't change underneath you), a delay (a bad release is likely noticed before you adopt
it), least privilege (the token can't do much if code does turn malicious) and no secrets (there
is nothing to steal).

**Mutable vs immutable references.** A tag or branch name is a label that can be moved to other
content; a content hash (git SHA, SHA-256 checksum, Docker digest) is derived from the content
and changes if any byte changes. This workflow uses hashes for the actions and for uv's archive,
but still uses tags for the Docker images (`postgres:16.14-bookworm`). Docker Hub can re-push a
tag; pinning images by digest is a recorded Phase 6 decision.

**Least privilege.** Give each piece exactly the access it needs. CI needs to read code, so the
token can read code and nothing else.

**Service containers.** Containers GitHub runs alongside a job for its lifetime, reachable on
mapped ports. Real dependencies, thrown away after each run, so tests never see leftover state
from a previous run.

**Lockfile-exact installs.** `uv sync --locked` and `npm ci` install exactly what the lockfile
pins and fail if it's stale. Without them, CI could test a different set of packages than the
one committed, and a passing CI run would say nothing about what's in the repo.

## 5. Verification

Three checks ran locally before the commit, and the fourth is the first run on GitHub:

1. **The YAML parses.** Ruby's YAML parser loaded the file and printed its structure: the
   three jobs, the two service containers with the right images and ports, `contents: read` and
   the triggers. Ruby's parser follows YAML 1.1, which reads the bare key `on` as the boolean
   `true`; GitHub's parser doesn't, so this is a known quirk of the checking tool, not a bug in
   the file.
2. **Every pinned SHA is its tag's commit, and before the cutoff.** A script read each
   `uses:` line from the workflow, asked the GitHub API which commit the tag points to and when
   the release was published, and printed MATCH and "before cutoff" for all three.
3. **The CI commands pass against the running stack**, with uv 0.12.23 and Node 24.21.0:
   `uv sync --locked`, both ruff checks, `uv run pytest` (7 passed, 6 deselected, exit 0),
   `npm ci`, lint, typecheck, test (5 passed), build, and the dependency-age script (35 Python
   and 175 npm packages, all before the cutoff).

4. **The first real run on GitHub passed** ([run 40123000260](https://github.com/RushilJoshi07/multi-agent-stock-research-platform/actions/runs/40123000260),
   commit `4c3aa31`): backend, web and dependency-age all succeeded, confirmed by the user on the
   Actions page and by the GitHub API's job list. Since the backend job passed, the
   service containers started and passed their health checks, setup-uv accepted the checksum,
   uv installed the locked environment on Linux, and the tests reached Postgres and Redis on
   `localhost` with pytest-socket on. The web job passing shows `npm ci` and the build work on
   Linux.

What this does **not** prove:
- That the tests ran against the Python and Node versions we intended. The run passing doesn't
  show which versions were installed. The job logs show it, but they weren't read for this
  explainer.
- That Node's download is checksum-verified. The workflow pins uv's checksum explicitly but
  passes no checksum for Node; whether setup-node verifies the Node archive itself is
  unverified.
- That uv verifies the Python download's hash. Unverified in this project.

The sacred gates aren't directly involved yet (there's no data, agents or trading code). What
CI does add for later phases: the no-network rule for tests is now enforced on a machine that
isn't the laptop, and the gate tests stay outside CI because they need the full stack.

## 6. Interview defense

**"Why not just use `actions/checkout@v4` like everyone else?"** A tag can be moved to different
code by whoever controls the action's repository, and CI runs that code with a token and the
source checked out. That's exactly what happened with `tj-actions/changed-files` in 2025. A full
SHA names the code itself and can't be repointed. The cost is a manual bump with a lookup, which
I'm willing to pay for something that runs with credentials.

**"You pinned the action by SHA, but the action downloads things at runtime. Doesn't that
undo the pin?"** (the hard one) Partly, yes, and it's worth saying so. Pinning the action fixes
the action's own code, not what it downloads. setup-uv downloads uv, and I closed that by
passing the published SHA-256 of the exact archive. setup-node downloads Node and I didn't
pass a checksum, so that download relies on setup-node's own behavior, which I haven't verified.
uv downloads Python and I haven't verified that it checks the hash. The Docker images are
pinned by tag, not digest, which is a recorded Phase 6 fix. So the honest answer is: the action
code and uv are pinned end to end; Node, Python and the images are trusted to their sources,
and that's a known, written-down gap.

**"Why not use `actions/setup-python`?"** uv installs the exact version in `.python-version`
already, and that's how the laptop got it. One fewer action means one fewer piece of third-party
code with access to the job, and CI and local get Python the same way.

**"Why do the service containers use ports 5433 and 6380 when nothing else runs on the CI
machine?"** So the tests run with exactly the same settings as locally, with no CI-only
configuration. The test guard that refuses port 5432 runs unchanged instead of needing a CI
exception. Exceptions to safety checks are where they get turned off by accident.

**"Isn't 14 days for actions overkill? You're running older code."** It means slower adoption of
bug fixes, and setup-uv is three releases behind. The trade is that a compromised or broken
release usually gets noticed and pulled within days, and CI runs action code with the repository
and a token. A security fix that can't wait has a documented exception path.

**Honest weaknesses, stated plainly:**
- Only one CI run exists so far, so the workflow's reliability over time (flaky service startup,
  registry outages) is unknown.
- Action pins are checked by hand; nothing stops a future edit from adding an unpinned action.
  The automated check is parked until v1.
- Node, the Python download and the Docker images aren't hash-pinned (see above).
- The dependency-age job depends on PyPI and npm being up; an outage fails CI for reasons
  unrelated to the code.

## 7. What comes next

Step 7 was the Phase 0 gate: `make gate PHASE=0` passed and CI is green on `main` (see the
[Phase 0 summary](phase-0-summary.md)). From Phase 1 on, every pull request from the parallel
worktree sessions runs this workflow before it merges.
