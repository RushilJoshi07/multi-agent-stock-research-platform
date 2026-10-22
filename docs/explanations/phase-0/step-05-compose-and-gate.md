# Phase 0 · Step 5: The full Compose stack and the Phase 0 gate

Commit `b2cdaa9`, plus a follow-up that redesigned the web container's mounts (described here as
built). Decision notes: [0001 Python](../../decisions/0001-python-3.13.md),
[0003 uv](../../decisions/0003-uv-lockfile.md), [0005 host ports](../../decisions/0005-host-ports.md),
[0007 dependency age](../../decisions/0007-dependency-age-14-days.md).

## 1. What this does, and what it doesn't

One command, `make up`, now starts all four services: Postgres, Redis, the FastAPI app and the
React dev server. It returns only once each one reports healthy. The Phase 0 gate test runs that
command and proves the result from the outside:
- all four services are healthy;
- `/health` is green;
- `/health` goes red when Redis is stopped;
- the web app is served and reaches the API through its proxy.

A small pytest hook makes the gate prove its own tests actually ran.

The same step tightened the toolchain under the 14-day rule. uv moved from Homebrew's 0.13.4,
published the day before, to 0.12.23 from the official release archive. Python moved from the
system 3.13.7 to 3.13.16, now the same version on the Mac, in Docker and in CI. Making uv findable
after the Homebrew copy was removed meant one edit outside the repo, to `~/.zprofile`.

What this does not do. These are development images: code is bind-mounted, servers reload on change,
and processes run as root. Production images, secrets and AWS come in Phase 6. CI is step 6. The
Phase 0 gate also requires CI to pass, so it isn't recorded as passed yet.

## 2. The code, explained

### `docker/api.Dockerfile`

```dockerfile
FROM python:3.13.16-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.12.23 /uv /uvx /bin/
```
The base image's Python is exactly the version in `.python-version`. Copying the `uv` binary out of
Astral's own image gives the container the same uv version as the Mac, without a separate
installer.

```dockerfile
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/opt/venv/bin:$PATH"
```
- `UV_PROJECT_ENVIRONMENT=/opt/venv` puts the virtualenv outside `/app`. Compose bind-mounts
  `./src` into `/app/src`; a venv under `/app` could be hidden or replaced by a mount.
- `UV_PYTHON_DOWNLOADS=never` makes uv use the image's Python or fail. Without it, a mismatch
  could make uv quietly download a different Python, one the 14-day rule never checked.
- `UV_LINK_MODE=copy` avoids a warning about hard links across file systems inside Docker builds.
- The venv's `bin` on `PATH` lets the command and the healthcheck use plain `uvicorn` and `python`.

```dockerfile
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project
COPY src ./src
RUN uv sync --locked --no-dev
```
Dependencies are installed in a layer that depends only on the three dependency files, so editing
code doesn't reinstall every package. `--locked` fails the build if `uv.lock` doesn't match
`pyproject.toml`; the image can never resolve its own, different versions. `--no-dev` leaves out
pytest and ruff. The second `sync` installs the project itself in editable mode, pointing at
`/app/src`, which is why the bind-mounted code is what actually runs.

```dockerfile
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "src"]
```
`--host 0.0.0.0` is required in a container. On `127.0.0.1` uvicorn would accept connections only
from inside the container itself, and the published port would get nothing. `--reload` restarts on
code changes; the container log shows "Started reloader process [1] using WatchFiles".

### `docker/web.Dockerfile`

```dockerfile
FROM node:24.21.0-bookworm-slim
COPY web/package.json web/package-lock.json web/.npmrc ./
RUN npm ci
COPY web/ ./
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
```
- **The Node version** is exactly the one in `.nvmrc`.
- **`npm ci`** installs exactly the lockfile, with `.npmrc`'s `engine-strict` in force. Inside Linux
  it installs the Linux builds of the platform-specific packages (rolldown, oxlint, Tailwind's CSS
  engine). Those builds are in the lockfile, and the age check covered them.
- **`COPY web/ ./`** then adds the config files (`vite.config.ts`, the tsconfigs) and the source. The
  Mac's `web/node_modules` is excluded by `.dockerignore`, so the image's `node_modules` is always the
  one `npm ci` built.
- **`--host 0.0.0.0`** fixes the problem step 4 found: Vite listens only on localhost by default.

### `.dockerignore`

It keeps `.env` files, `.git`, `.venv`, both `node_modules` folders, build output, dumps and worktrees
out of the build context. The important entries are the `.env` ones. Docker sends the whole directory to
the build, so without them a `COPY` could bake secrets into an image.

`.dockerignore` patterns match from the build-context root, so a plain `.env` only excludes the root
file. Vite reads `.env` files from its own folder, and `web.Dockerfile` copies `web/`, so a future
`web/.env` would have gone into the image. Hence `**/.env` and `**/.env.*` (keeping
`!**/.env.example`).

Checked:
- **web:** with a temporary `web/.env` containing `CHECK=1`, a rebuild left the `COPY web/ ./` step
  `CACHED` and the image ID unchanged (`8af891af7916`). That means the file never reached the build
  context. `ls -la /app` and a `find` for `.env*` in a fresh container showed none, and the temporary
  file was then deleted.
- **api:** the image's `/app` contains only `.python-version`, `pyproject.toml`, `src` and `uv.lock`.

### `compose.yaml`: the api service

```yaml
DATABASE_URL: postgresql://${POSTGRES_USER:-fathom}:${POSTGRES_PASSWORD:-change-me-local}@postgres:5432/${POSTGRES_DB:-fathom}
REDIS_URL: redis://redis:6379/0
```
Inside Docker, services find each other by service name on Compose's private network, on their
normal ports. The 5433 and 6380 host ports exist only for the Mac. This is why the Phase 1 guard on
the app's own `DATABASE_URL` must check host and port together: `postgres:5432` is correct here, while
`localhost:5432` on the Mac is the old project's database.

```yaml
ports: ["127.0.0.1:${API_HOST_PORT:-8001}:8000"]
volumes: ["./src:/app/src"]
```
Published on this machine only (decision 0005), and the code is live-mounted for reload.

```yaml
depends_on:
  postgres: { condition: service_healthy }
  redis: { condition: service_healthy }
healthcheck:
  test: [... "urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3).status == 200" ...]
```
The API starts only after Postgres and Redis are healthy, and the API itself counts as healthy only
when `/health` returns 200. So "api: healthy" means "the API can reach both services". A check for
"the process is running" would pass with the database down.

There is no `~/.aws` mount; Bedrock credentials aren't needed until Phase 3.

### `compose.yaml`: the web service

```yaml
volumes:
  - ./web/src:/app/src
  - ./web/index.html:/app/index.html
```
Only what Vite needs to see live is mounted: the source folder, and `index.html`, the page shell Vite
serves and transforms on each request. Everything else stays in the image, above all `node_modules`.
The Mac's `web/node_modules` holds macOS builds of rolldown and oxlint and can never reach the
container. A change to `package.json`, the lockfile, `.npmrc` or a config file changes the image's
inputs, so the next `make up` rebuilds the image through `--build`. Nothing else needs to be live:
there is no `public/` folder yet, and `vite.config.ts` is only read when Vite starts.

`index.html` is a single-file bind mount, which has one catch. Editors that save by writing a new file
and renaming it over the old one replace the file on the Mac, but the container keeps seeing the old
one until `make up` or a restart. `web/src` is a directory mount and isn't affected. `index.html`
rarely changes, so this is recorded in STATUS.md rather than designed around.

Because the image also copies `web/src`, editing source changes the image's inputs too, so the next
`make up` rebuilds and recreates the web container. The api container behaves the same way with `src/`.
Postgres and Redis are never affected.

```yaml
depends_on:
  api: { condition: service_started }
```
`service_started`, not `service_healthy`. If the API is down, the web app should still load and say
"API unreachable", as designed in step 4, rather than not exist.

### `Makefile`

```make
NODE24_BIN ?= $(HOME)/.local/node/v24.21.0/bin
UV_BIN ?= $(HOME)/.local/uv/0.12.23
```
`?=` sets a default that can be overridden (`make test UV_BIN=/elsewhere`). Both point at the pinned
installs, so `make` works even in a shell whose PATH doesn't include them.

```make
up:
	BUILDX_NO_DEFAULT_ATTESTATIONS=1 docker compose up -d --build --wait
```
- `--build` rebuilds the images when their inputs change.
- `--wait` returns only when every service with a healthcheck is healthy, or fails.
- `BUILDX_NO_DEFAULT_ATTESTATIONS=1` turns off the build-provenance attestation Docker adds by default.
  That attestation records when the image was built. Because it's part of the image's manifest, the
  image ID changed on every build even when every layer came from cache, so Compose saw a "new" image
  and recreated api and web on every `make up`. With it off, an unchanged build keeps its ID. Setting
  `provenance: false` in `compose.yaml` was tried first and had no effect on this setup (Compose v5.1.1,
  containerd image store); the attestation was still exported.

```make
down:
	docker compose down
```
Never with `-v`. That would delete the named volumes, which hold the database. Deleting data is an
ask-first action.

`logs` uses `--tail=200` without `-f`, so it returns instead of following forever. `lint` runs ruff check,
ruff format check, oxlint and the TypeScript check.

```make
gate:
	@test -n "$(PHASE)" || { echo "usage: make gate PHASE=<n>"; exit 2; }
	FATHOM_GATE=1 $(UV) run pytest tests/gates/test_phase$(PHASE)_gate.py -m gate -v -rA
```
`-m gate` overrides the default `-m 'not gate and not live'` from `pyproject.toml`, because pytest uses
the last `-m`. `-v -rA` lists every test and its result. `FATHOM_GATE=1` switches on the check below.

### `tests/gates/conftest.py`: proving the gate tests ran

Gate tests are deselected by default, and the gate depends on a later `-m gate` undoing that. If the
override ever stopped working, the gate tests would be silently deselected. Pytest does fail when
*nothing* runs (exit code 5), but not when only *some* tests are deselected or skipped. The hooks close
that gap:
- `pytest_deselected` records every test from `tests/gates/` that gets deselected.
- `pytest_runtest_logreport` records each gate test's outcome: passed, failed, or skipped.
- `pytest_sessionfinish` runs only when `FATHOM_GATE=1`. It fails the run if any gate test was
  deselected or skipped, or if none ran, and prints why. Otherwise it prints
  `GATE CHECK: N gate tests ran, 0 deselected, 0 skipped`.

The check is keyed to the environment variable, not to the `-m` expression, because a plain `make test`
deselects the gate tests *on purpose* and must not fail for it.

### `tests/gates/test_phase0_gate.py`

The module-scoped `make_up` fixture runs the real `make up`, with a 15-minute timeout for first
builds, once for all six tests. Afterwards it prints which services are left running; it never stops
them.
1. **`test_one_command_starts_the_stack`:** `make up` exited 0. On failure it shows the last 3,000
   characters of output.
2. **`test_all_four_services_are_running_and_healthy`:** reads `docker compose ps --format json`.
   Compose versions print either one JSON array or one object per line, so the parser handles both.
3. **`test_health_is_green`:** 200, Postgres major version ≥ 16, Redis ok.
4. **`test_health_goes_red_when_redis_stops`:** stops the real Redis container, polls `/health` until
   it returns 503 with Redis down and Postgres up, then restarts Redis in a `finally` block, so a failed
   assertion can't leave it stopped, and waits for 200 again.
5. **`test_web_app_is_served`:** 200 with `<div id="root">`.
6. **`test_web_app_reaches_the_api_through_its_proxy`:** `/api/health` on 5174 returns 200 and
   `status: ok`. That request goes through Vite's proxy inside Docker to `api:8000`.

Every request goes to `127.0.0.1`, so pytest-socket's localhost-only rule stays on. The `make` and
`docker` subprocesses aren't affected by pytest-socket, which only patches sockets inside the test process.

### The toolchain changes

**uv 0.12.23.**
- **The problem:** Homebrew had installed uv 0.13.4, published 2026-10-20, a day before the check. Homebrew
  only offers the newest version.
- **The install:**
  1. Download `uv-aarch64-apple-darwin.tar.gz` from the 0.12.23 GitHub release (published 2026-10-03).
  2. Check its SHA-256 against two independent sources: the release's `.sha256` file, and the
     `digest` GitHub's API publishes for the asset. Both gave `50487ae5…`.
  3. Extract it to `~/.local/uv/0.12.23/`, with symlinks `~/.local/bin/uv` and `uvx`.
  4. `brew uninstall uv`, so only one uv exists on the machine.
- **The lockfile:** `uv lock --check` with 0.12.23 passed and `uv.lock` was byte-for-byte unchanged, so
  the older uv reads the lockfile the newer one wrote.

**Python 3.13.16.**
- **The change:** `.python-version` went from `3.13` to `3.13.16` (released 2026-09-30; 3.13.17 came out
  on the day of the change, too new).
- **The install:** `uv python install 3.13.16` installed uv's managed CPython build, compiled 2026-10-03,
  from uv 0.12.23's own download list. `uv sync` then rebuilt the venv.
- **Proof:** `.venv/pyvenv.cfg` reads `version_info = 3.13.16`, with its home in
  `~/.local/share/uv/python/cpython-3.13.16-macos-aarch64-none`.
- **Everywhere else:** Docker uses `python:3.13.16-slim-bookworm`, and CI will read `.python-version`.

**`~/.zprofile`.** Four lines were appended, a blank separator and then:
```sh
# uv 0.12.23 (symlinks in ~/.local/bin -> ~/.local/uv/0.12.23). Appended last so
# Homebrew's binaries (including claude) keep priority.
export PATH="$PATH:$HOME/.local/bin"
```
- **Why it's needed:** after the uninstall, nothing on the PATH pointed to uv. `/usr/local/bin` needs
  admin rights.
- **Why it goes at the end:** `~/.local/bin` already held a `claude` symlink to a *different* Claude Code
  install than the Homebrew one in use. Putting the folder first would have changed which `claude` runs.
  Appended last, uv resolves there (nothing else provides it) and `claude` stays Homebrew's.
- **A side effect:** `uv python install` also added `~/.local/bin/python3.13`. Because the folder is
  last, the existing 3.13.7 install still wins for plain `python3.13`; the project always uses its venv.

## 3. Decisions and rejected alternatives

**Testing the stack from the outside.** The gate drives the same `make up` a person types and checks
results over HTTP and `docker compose ps`. Importing the app in-process, as the step 3 unit tests do,
would prove the code works but not that the images build, the ports are published, the containers
reach each other by name, or the proxy points at the right place. Those are exactly the failures a
container setup introduces.

**The healthcheck requires 200 from `/health`, not just a running process.** A process check passes while
the API can't reach its database. The cost is that during the gate's Redis test the api container briefly
reports unhealthy. No restart policy is set, so Docker records it and doesn't restart anything.

**Mount only `web/src` and `web/index.html`; keep `node_modules` and the config in the image.** The
problem being solved: the web container must run the Linux `node_modules` its image built, while the
Mac's macOS `node_modules` sits in the same folder.

Rejected designs, in the order they were tried or considered:
- **Mount all of `./web` with an anonymous volume over `node_modules`** (the first design). The
  volume hid the Mac's copy, but Compose carries an anonymous volume's contents over to the next
  container. After a dependency change, the web container could keep the *old* `node_modules` while
  the image had the new one.
- **The same design plus `--renew-anon-volumes`** (added after review). That fixed the stale copy,
  but recreated all four containers, Postgres and Redis included, on every `make up`, and left the
  previous volume behind each time, about 137 MB.
- **A cleanup step that deletes leftover volumes.** It would have treated the symptom and put a
  delete command in the everyday path.

The final design removes the cause. Nothing the image installs is ever covered by a mount, there is
no volume to go stale or be left behind, and dependency or config changes rebuild the image through
`--build`. The cost: a config change needs a `make up` rather than appearing live, and `index.html`
has the single-file-mount catch described above.

**Turning off default build attestations.** Without it, Compose recreated api and web on every
`make up` even with no changes, because the attestation's build time changed the image ID each time.
`provenance: false` in `compose.yaml` was the obvious fix, but had no effect on this setup; the
environment variable did. The attestation would matter for published images, which record how they
were built. These are local development images that are never pushed, so nothing is lost. Production
images keep attestations; that's recorded for Phase 6.

**uv from the release archive with two independent checksums, not a `curl | sh` installer.** An install
script runs code downloaded at that moment, with no fixed artifact to verify. The archive is fixed, and
its hash came from two separate sources.

**Appending to PATH instead of prepending, and editing `~/.zprofile` at all.** The other option was
calling uv only through the Makefile's `UV_BIN`. That would leave plain `uv` broken in every terminal, so
the user chose the profile edit. Appending is what keeps `claude` unchanged.

**Development images run as root.** It's simpler, and nothing here is exposed beyond 127.0.0.1. Production
images with a non-root user belong to Phase 6.

**Image tags, not digests.** Tags like `16.14-bookworm` can be re-pushed by Docker Hub with Debian
updates, so a tag isn't immutable. Pinning by `@sha256:` digest is recorded as a Phase 6 decision.

## 4. Concepts introduced

**Container networking.** Compose puts the services on a private network where each is reachable by its
service name (`postgres`, `redis`, `api`) on its normal port. Ports published to the host (`127.0.0.1:8001`)
are a separate doorway for the Mac. The same database is `localhost:5433` from the Mac and `postgres:5432`
from the API container.

**Bind mounts vs. volumes.** A bind mount (`./src:/app/src`) shows a Mac folder inside the container,
so edits appear instantly, and it covers whatever the image had at that path. A named volume
(`fathom_pgdata`) is storage Docker manages that outlives containers. An anonymous volume is the same
without a name. It's easy to create by accident and easy to leave behind, which is why the web
container no longer uses one.

**Image identity and recreation.** Compose recreates a container when its configuration or its image ID
changes. Build caching makes the layers identical, but anything else in the manifest, like a
timestamped attestation, still changes the ID. "Every layer CACHED" doesn't mean "same image".

**Healthchecks and `--wait`.** A healthcheck is a command Docker runs periodically inside the container.
`depends_on: condition: service_healthy` delays a service until its dependency passes. `up --wait` blocks
until all of them pass. Together they replace "sleep 10 and hope".

**Build layers and caching.** Each Dockerfile instruction makes a layer, and Docker reuses a layer when
its inputs haven't changed. Copying the dependency files before the code means a code edit reuses the
expensive dependency layer.

**Marker-based selection.** Pytest markers (`gate`, `live`) tag tests, and `-m` selects by expression. A
default expression in `addopts` is convenient but dangerous: a test excluded by default is silently not
run unless something checks that it was.

## 5. Verification

**What was run:**
- **uv:** the checksum matched both sources, and `which uv` in a fresh login shell gives
  `/Users/rushil/.local/bin/uv` → `uv 0.12.23`. `which claude` still gives `/opt/homebrew/bin/claude`.
  `/opt/homebrew/bin/uv` and `/usr/local/bin/uv` don't exist, and `brew list uv` says not installed.
  `uv lock --check` passed with `uv.lock` unchanged.
- **Python:** `.venv/bin/python --version` gives 3.13.16, and `pyvenv.cfg` reads `version_info = 3.13.16`.
  Then:
  - the age check: `uv.lock` 35 packages OK, `package-lock.json` 175 packages OK;
  - pytest: 7 passed;
  - ruff: clean.
- **Ports:** the step 4 uvicorn and Vite were stopped by task ID, and `lsof` showed 8001 and 5174 free.
- **First `make up`:** all four containers healthy in about 20 seconds. Inside them:
  - api: Python 3.13.16 and uv 0.12.23, using `/opt/venv/bin/python`;
  - web: Node v24.21.0 and npm 11.19.0;
  - the api image's `/app` holds no `.env`;
  - Vite logged `vite --host 0.0.0.0`.
- **`make gate PHASE=0`:** 6 passed, and `GATE CHECK: 6 gate tests ran, 0 deselected, 0 skipped`. With
  Redis stopped, `/health` returned `{'status': 'degraded', … 'redis': {'ok': False, 'error':
  'ConnectionError: Error -2 connecting to redis:6379. Name or service not known.'}}` with Postgres still
  ok. It returned 200 again after the restart.
- **The deselection check can fail:**
  - the gate file run without `-m gate` printed `GATE CHECK FAILED: 6 gate test(s) deselected …` and
    `no gate tests ran`, and exited 1;
  - `-m "gate and not gate"` did the same, also exit 1;
  - the same run with the check off exited 5, pytest's own "nothing ran".
- **The other Makefile targets:** `make test` (7 passed, 6 deselected), `make test-web` (5 passed),
  `make lint` (all four checks) and `make ps` (all four healthy) all passed.
- **The `--renew-anon-volumes` interim:**
  - `make up` recreated all four containers;
  - web's `node_modules` volume changed from `f273f8…` to `1b106b…`;
  - `fathom` and `fathom_test` both still existed;
  - the gate passed 6 of 6;
  - each run left a 137 MB volume behind, which led to the redesign.
- **After the redesign, `make up` twice in a row:**
  - **First run:** Postgres and Redis `Running`; api and web recreated once, because `compose.yaml`
    had changed.
  - **Second run:** all four `Running`, nothing recreated.

  Getting there exposed the attestation problem. Every build step was `CACHED`, yet the image IDs
  changed on every build. With `BUILDX_NO_DEFAULT_ATTESTATIONS=1`, two builds gave identical IDs
  (`642d618bd844` and `8af891af7916` both times); with `provenance: false` they still changed.
- **Where web's `node_modules` comes from:**
  - The container's only mounts are binds of `web/src` and `web/index.html`; there's no volume.
  - Its `node_modules/@rolldown` holds `binding-linux-arm64-gnu`, while the Mac's holds
    `binding-darwin-arm64`.
  - A fresh container from the `fathom-web` image with no mounts shows the same Linux binding,
    with 84 packages at the top level.
- **The gate after the redesign:** `make gate PHASE=0` gave 6 passed, "6 gate tests ran, 0
  deselected, 0 skipped", in 3.0 s, because its `make up` didn't need to recreate anything.
- **Cleanup, with approval:**
  - deleted the two leftover anonymous volumes (`f273f8…`, `1b106b…`), each first confirmed as
    labelled anonymous and used by no container;
  - deleted the `alpine:3.22` image.

  The named volumes are untouched. A third leftover volume, `78f694…`, which the web container used
  until the redesign, was deleted after its own approval and the same checks. Only
  `fathom_fathom_pgdata` and `fathom_fathom_redisdata` remain.

**What this does not prove:**
- **CI.** The Phase 0 gate requires CI to pass; that's step 6, so the gate isn't recorded as passed.
- **Reload inside containers.** The reloader started, but no test edited a file and watched the API or
  the page reload.
- **Why `provenance: false` didn't work.** It was observed to have no effect here; the reason wasn't
  investigated. The environment variable is what's verified.
- **Live updates from mounted files.** Nothing tested that an edit in `web/src` reaches the browser
  through Vite's hot reload inside the container, or the `index.html` single-file-mount catch.
- **A clean machine.** The images were built where the base images and caches already existed. A first build
  elsewhere would download everything and take longer; the 15-minute timeout allows for that.
- **A process note:** measuring the leftover volumes ran a throwaway `alpine:3.22` container that hadn't
  been approved and isn't covered by the 14-day rule. It only ran `du`; the image has since been deleted,
  and CLAUDE.md now says to ask before pulling any image not already in `compose.yaml` or a Dockerfile.

## 6. Interview defense

**"How do you know `make up` actually works, not just that it ran?"**
The gate test runs the same command, then checks from the outside: Docker reports all four services
healthy, and the API's healthcheck only passes when it can reach both databases. The health endpoint is
green over real HTTP, the web app is served, and the web app reaches the API through its proxy. It also
stops Redis and confirms the health check goes red, so I know the green isn't hard-coded.

**"Your gate tests are deselected by default. How do you know they ran?"** (hard)
That was a real risk, because `pyproject.toml` excludes gate tests from every normal run and the gate
relies on a later `-m gate` overriding it. I added pytest hooks that, during a gate run, record every gate
test that gets deselected or skipped and fail the run if any were, or if none ran. I tested the failure:
running the gate file without `-m gate` fails with the list of deselected tests. Pytest alone would only
have caught the case where *everything* was deselected.

**"How do you stop the Mac's node_modules from breaking the Linux container?"** (hard)
My first answer was an anonymous volume over `node_modules`. It hid the Mac's copy but kept stale
packages across rebuilds. The fix for that, `--renew-anon-volumes`, restarted the database on every
`make up` and leaked a 137 MB volume each time. The design I kept removes the cause instead: the container
only mounts the source folder and the page shell, and everything else, including `node_modules` and the
config, comes from the image, so a dependency change simply rebuilds it. Along the way I found that the
images got a new ID on every build despite full caching, because of a timestamped build attestation, and
that was making Compose recreate containers for no reason. Now a second `make up` recreates nothing.

**"Why not just `brew install uv` like everyone else?"**
Homebrew gave me a release that was one day old, and my rule says nothing younger than 14 days goes into
the toolchain, because that's when poisoned releases do their damage. Homebrew only offers the newest
version, so I took the release archive for an older version, verified its hash against two independent
sources, and removed the Homebrew copy so only one uv exists.

**"Why does your API container run as root?"**
It's a development image, published only on 127.0.0.1. A non-root user, secrets handling and image digests
are part of the production work in Phase 6. I'd rather do them there properly than half-do them here.

**Honest weaknesses:** CI isn't green yet; reload inside containers is untested; a config change needs a
`make up` rather than appearing live, and the single-file `index.html` mount can go stale after an atomic
save; images are pinned by tag, not digest; and one unapproved image was pulled during verification (since
deleted, and now covered by a CLAUDE.md rule).

## 7. What comes next

Step 6 adds CI:
- uv pinned to 0.12.23 through `setup-uv`;
- Python from `.python-version`;
- Node from `.nvmrc`;
- Postgres and Redis service containers on 5433 and 6380, so the 5432 guard needs no exception;
- a separate job running the dependency-age check.

When CI is green on `main`, the Phase 0 gate is complete and gets recorded in STATUS.md with this
step's evidence. If this step were wrong, it would show as a stack that starts but doesn't connect,
a green health check on a broken service, or a gate that passes without running. The checks above are
aimed at exactly those three.
