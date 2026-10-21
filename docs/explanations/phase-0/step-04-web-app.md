# Phase 0 · Step 4: The web app and the 14-day dependency rule

Commit `b8655b2`. Decision notes: [0007 dependency age](../../decisions/0007-dependency-age-14-days.md),
[0005 host ports](../../decisions/0005-host-ports.md). Rules: `.claude/rules/dependencies.md`.

## 1. What this does, and what it doesn't

Two things landed together.

**The web app.** `web/` is an empty React app whose only job is to prove the frontend toolchain
works and can reach the API. It shows "Fathom" and one line about the API's health, read from
`/api/health`. Vite's dev server forwards that request to the FastAPI app on port 8001. The page has
exactly four states (checking, healthy, degraded, unreachable), and anything it can't positively
recognise as a health response is shown as unreachable, never as healthy.

**The 14-day dependency rule.** Every dependency, including every package the lockfiles pull in
underneath, and the Node runtime itself, must have been published at least 14 days before it was
installed. Both lockfiles are cut off at the same date by the package managers themselves, and a
script checks every locked package's publish date.

What this does not do. There is no styling, theme or layout; that is Phase 5. The app doesn't run in
Docker yet (step 5) or in CI (step 6). No test drives a real browser; Playwright comes in Phase 5.
The 14-day rule doesn't cover Docker base images such as `postgres:16.14` or `redis:7.4.11`.

## 2. The code, explained

### Pinning and the cutoff: `web/.npmrc` and `pyproject.toml`

```ini
save-exact=true
engine-strict=true
before=2026-10-06T23:59:59Z
```
- `save-exact=true` makes any future `npm install some-package` write an exact version
  (`"1.2.3"`), not a range (`"^1.2.3"`). Without it, one forgotten flag would quietly reintroduce
  ranges.
- `engine-strict=true` turns the `engines` field in `package.json` from a warning into an error,
  so `npm install` and `npm ci` refuse to run on the wrong Node version.
- `before=` tells npm to resolve every package, direct or transitive, only from versions that were
  available at that moment. `npm config get before` printed
  `Tue Oct 06 2026 19:59:59 GMT-0400`, the same instant in local time.

```toml
[tool.uv]
exclude-newer = "2026-10-06T23:59:59Z"
```
The same cutoff for Python. uv records it in `uv.lock` (line 6), so the lockfile itself says which
date it was resolved against, and `uv lock --check` confirms the lock still matches.

The two dates must stay equal. `scripts/check_dependency_age.py` refuses to run if they differ.

### `web/package.json`

```json
"engines": { "node": "24.x" },
```
Together with `engine-strict`, this is the install-time guard.

```json
"prelint": "node scripts/check-node.mjs",
"lint": "oxlint --deny-warnings",
```
npm runs a script named `pre<name>` automatically before `<name>`. npm only checks `engines` when
installing, not when running scripts, so without these pre-scripts `npm test` would run happily on
Node 25. Each of `lint`, `typecheck`, `test` and `build` has one.

`--deny-warnings` matters. oxlint treats many rules as warnings, and warnings exit 0. A scratch file
containing `debugger;` exited **1** with the flag and **0** without it, so without the flag CI would
pass code with lint problems.

`"test": "vitest run"`: plain `vitest` stays in watch mode and never exits, which would hang CI.

`"build": "vite build"`: not `tsc -b && vite build` as in the old project. CI runs `typecheck` as its
own step, so building would otherwise type-check twice.

### `web/scripts/check-node.mjs`

```js
if (actual.split(".")[0] !== required) { ...; process.exit(1); }
```
It compares only the major version (24). The message tells the reader exactly how to run with the
right Node: `PATH="$HOME/.local/node/v24.21.0/bin:$PATH" npm ...`.

### `web/vite.config.ts`

```ts
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8001";
const port = Number(process.env.WEB_PORT ?? 5174);
```
The defaults are for running on the Mac: API on 8001, web on 5174 (decision 0005). In step 5 the
web container will set `API_PROXY_TARGET=http://api:8000` (the API container's name on the Compose
network) and `WEB_PORT=5173`. Neither name starts with `VITE_`. Vite copies `VITE_*` variables into
the JavaScript sent to the browser, and these are only for the dev server.

```ts
strictPort: true,
```
If 5174 is taken, Vite fails instead of silently moving to 5175. A silent move would leave the docs,
the gate test and the browser pointing at the wrong place.

```ts
proxy: { "/api": { target: apiTarget, rewrite: (path) => path.replace(/^\/api/, "") } },
```
The page requests `/api/health`. Vite forwards it to `http://localhost:8001/health`, stripping the
`/api` prefix because the FastAPI routes don't have one. The browser only ever talks to 5174, so no
CORS configuration is needed.

```ts
test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
```
Vitest runs the tests in jsdom, a simulated browser document, and runs the setup file before
each test file.

### `web/src/health.ts`

```ts
if (response.status !== 200 && response.status !== 503) {
  return { kind: "unreachable", status: response.status, detail: `HTTP ${response.status}` };
}
```
The API answers 200 or 503 by design (step 3). Anything else means the API didn't answer: the proxy's
502, a 404 from a wrong path, a 500. Those are "unreachable", never "healthy".

```ts
body = (await response.json()) as HealthBody;
...
if (typeof body?.checks !== "object" || body.checks === null) { return { kind: "unreachable", ... } }
```
A 200 that isn't JSON, or JSON without `checks`, is also unreachable, not a crash. The `as HealthBody`
is a type assertion, not a check; the `checks` test is the minimum real check before rendering reads it.

### `web/src/App.tsx`

```tsx
const [result, setResult] = useState<HealthResult | null>(null);
```
`null` means "request in flight" and renders "Checking API…".

```tsx
<button type="button" onClick={check} disabled={result === null}>Check again</button>
```
The button is disabled while a check is running, so impatient clicks don't stack requests whose
answers could arrive out of order.

```tsx
const version = result.body.checks.postgres?.version ?? "version unavailable";
```
If the version is missing, the page says so instead of showing nothing. That's the "missing is
missing" rule applied to one string.

### `web/src/test/setup.ts`

```ts
if (!process.versions.node.startsWith("24.")) { throw ... }
```
A second Node check, for anyone who runs `npx vitest` directly and skips the npm pre-script.

```ts
beforeEach(() => { vi.stubGlobal("fetch", vi.fn(async (input) => { throw new Error(`unmocked fetch in test: ...`) })) });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
```
Before every test, `fetch` is replaced with one that throws. A test that forgets to provide its own
mock fails loudly instead of making a real network request. This is the browser-side equivalent of
pytest-socket from step 3. `cleanup()` unmounts what the test rendered, so one test's page can't leak
into the next.

`tsconfig.app.json` includes `"node"` in its types only because this file reads `process.versions`.

### `web/src/App.test.tsx`

Five cases, each stubbing `fetch` with a specific response:
1. **In flight:** a promise that never resolves. The heading and "Checking API…" render.
2. **200:** shows "API healthy · Postgres 16.14".
3. **503 with Redis down:** shows "API degraded" and the Redis error, and does *not* list Postgres.
   That last assertion catches a page that lists every service instead of only the failing ones.
4. **502:** shows "API unreachable (HTTP 502)". This is exactly what the real proxy returned with no
   API running.
5. **fetch throws:** shows "API unreachable".

### `scripts/check_dependency_age.py`

- **Inputs:** it reads both cutoffs and refuses if they differ. Then it lists every locked package:
  - from `uv.lock`, registry packages only, which skips the project itself;
  - from `package-lock.json`, every entry under `packages`, including other platforms' optional
    binaries that aren't installed on this Mac. They're still in the lockfile, so CI or Docker
    could install them.
- **Publish dates:**
  - PyPI: the earliest upload time of that exact version, because a version's files can be uploaded
    at different times and the first one is when it became installable.
  - npm: the registry's `time[version]`.
- **Result:** it prints the count and the newest date per lockfile, lists every package past the
  cutoff and every package with no known date, and exits 1 if there are any. "No known date" counts
  as a failure, because missing data is not assumed to be fine.

### `pyproject.toml`: ruff only checks Python

```toml
include = ["*.py", "*.pyi", "**/pyproject.toml"]
```
After the downgrade to 0.16.10, `ruff format --check` started checking the ```python examples inside
the explainers' Markdown and wanted to rewrite partial lines into wrong code, e.g.
`pool_pre_ping=True,` into `pool_pre_ping = (True,)`. Those examples are deliberately fragments.
Limiting ruff to Python files keeps it on the code.

## 3. Decisions and rejected alternatives

**14 days, enforced on the whole lockfile, not just direct pins.** A compromised release usually
appears in a package you never chose directly. One of the 175 lockfile entries pulled in by 15 direct
web dependencies is far likelier to be hit than React itself. Pinning only the direct dependencies
would leave the other 160 entries resolving to "newest". Most bad releases are found and pulled within
days, so a two-week delay keeps them out. Rejected: always-latest (no buffer); version ranges (the
tree changes silently between installs); a 30-day or longer delay (further from security fixes for
little extra protection). Cost: pins sit a little behind, and an urgent security fix needs an explicit,
recorded exception. See [decision 0007](../../decisions/0007-dependency-age-14-days.md).

**An absolute cutoff date, not a rolling "14 days".** uv accepts `14 days` and npm has
`min-release-age`, and a rolling window would save editing the date. It was rejected because the
cutoff would move every day without a commit: re-locking next week could produce a different tree
from the one reviewed today, and it might make `uv sync --locked` in CI treat the lock as stale
(unverified). With an absolute date, the cutoff only moves in a reviewed commit, and both files show
exactly when. `min-release-age` was also unverified for the npm version bundled with Node 24.21.0.

**Downgrade ruff rather than make an exception.** ruff 0.17.1 was five days old when installed.
Keeping it as a "pre-rule" exception would have started the rule with a hole. 0.16.10 passed every
check on the existing code. The only side effect was the Markdown issue above, which pointed to a real
improvement: ruff shouldn't be reading docs at all.

**Node 24.21.0 from the official tarball.** 24.22.0 (released 2026-10-14) was six days old at install, so the rule required
24.21.0. Homebrew only offers the newest 24.x. nodejs.org's `.pkg` installer needs admin rights and
installs into `/usr/local/bin`, where it could shadow Homebrew's Node 25 for every project on the
machine. A version manager (nvm, fnm, volta) would be a new tool to install and trust, and none is on
this Mac. The tarball, checksum-verified against nodejs.org's `SHASUMS256.txt` and extracted into
`~/.local/node/v24.21.0/`, needs no admin rights and changes nothing else. Cost: commands need the
PATH prefix until step 5's Makefile hides it.

**Same Node everywhere, guarded at three points.** `.nvmrc` (CI), the Docker image tag (step 5) and the
local install are all 24.21.0. `engine-strict` stops installs, the pre-scripts stop `npm run`, and the
test setup stops direct `npx vitest`. Only the major version is enforced; the patch versions match
because they're pinned in the same places, not because a check enforces it.

**TypeScript 5.9.3, not 7.** TypeScript 7 is a new native compiler, not an incremental release. Taking it
in an empty app would make any later problem ambiguous: our code or the compiler? 5.9 was the approved
version, and moving to 7 deserves its own decision.

**Mocking `fetch` in the UI tests.** These tests check that each response renders the right state, which
needs exact control over the response. Whether the real API answers is a different question, covered by
the step 3 Python tests and, in step 5, by the gate test calling `/api/health` through the real proxy. The
mocks are honest about their scope: the 502 case uses the status the real proxy was seen returning.

**A dev-server proxy instead of calling the API directly.** Calling `http://localhost:8001` from the
browser would need CORS settings on the API and a different API address per environment, baked into
the frontend. The proxy keeps the browser on one origin and moves the address into server-side config.

**Tailwind wired in but unused.** Setting it up now means step 5's Docker build and step 6's CI cover it,
so a version problem shows up during setup rather than in Phase 5. No utility classes are used; design
waits for the mockups.

**`fsevents` install script left unapproved.** npm 11 asks before running package install scripts.
`fsevents` (macOS file watching) asked; everything worked without it, so it stays off until there's a
reason. Install scripts are a common attack path, so the default is no.

## 4. Concepts introduced

**Supply-chain attack.** An attacker publishes a malicious version of a legitimate package, often by
stealing a maintainer's credentials. Everyone who installs "the latest" in the next hours or days
runs the attacker's code. The 14-day rule bets that by the time a version is two weeks old, a bad one
has been noticed and pulled.

**Transitive dependencies and lockfiles.** A direct dependency is one you name (`vite`). Its own
dependencies, and theirs, are transitive. Here, 15 direct web dependencies produce 175 lockfile
entries, and 7 direct Python dependencies plus 4 dev tools resolve to 35 locked packages. The lockfile
records the exact version of every one, so every install is identical. The lockfile is only as safe as
the moment it was resolved, which is why the cutoff applies at resolution time.

**`engines` and `engine-strict`.** `engines` declares which runtime versions a package supports. By
default npm only warns on a mismatch; `engine-strict` makes it an error. Neither applies to
`npm run`, which is why the pre-scripts exist.

**Same-origin and the dev proxy.** Browsers restrict JavaScript from one origin (scheme, host and port)
calling another unless the server allows it (CORS). Serving the page and proxying the API from the same
origin sidesteps that entirely.

**Mock scope.** A mock replaces a real dependency with a controlled one. It's legitimate when the test
is about what *your* code does with a given input, and misleading when the test claims something about
the real dependency. The health tests mock in the frontend (rendering) and use real services in the
backend (behavior), so each claim is tested where it's true.

## 5. Verification

**What was run, on Node 24.21.0 / npm 11.19.0:**

- **Node install:** the tarball's SHA-256 matched both `SHASUMS256.txt` and the hash in the approved
  plan (`bed7eea5…`). `node --version` printed v24.21.0, and the system Node stayed v25.2.1.
- **Python relock:** `uv lock` with the cutoff changed six packages:
  - ruff 0.17.1 → 0.16.10
  - certifi 2026.10.19 → 2026.7.22
  - httptools 0.9.0 → 0.8.0
  - pluggy 1.7.0 → 1.6.0
  - starlette 1.9.0 → 1.7.0
  - websockets 17.3 → 17.2

  `uv lock --check` passed, and `uv.lock` line 6 records the cutoff. pytest: 7 passed. ruff check
  and `format --check` (12 files) passed.
- **npm:** `npm install` under `before`, then `npm ci` from the lockfile, both succeeded.
  `npm ls --depth=0` showed all 15 direct packages at exactly their pins.
- **The age check:**
  - `uv.lock`: 35 packages, newest iniconfig 2.3.1 at 2026-10-06T22:48Z, OK.
  - `package-lock.json`: 175 packages, newest tinybench 6.2.1 at 2026-10-06T18:22Z, OK.
  - Run against an earlier cutoff (2026-09-01) with no files changed, it listed 10 Python packages as
    TOO NEW and returned FAIL. So the check can fail.
- **npm scripts:** `lint` (7 files, 96 rules, 0 warnings), `typecheck`, `test` (5 passed) and `build`
  (221 kB JS, 4 kB CSS) all exited 0.
- **Node 25 guard:** `npm test` stopped at the pre-script with exit 1; `npm ci --dry-run` failed with
  "Unsupported engine".
- **Dev server with no API:** `GET /` returned 200 with `<div id="root">`. `GET /api/health` returned
  **502 Bad Gateway**, and Vite logged `ECONNREFUSED`.
- **End to end:** with uvicorn on 8001, `GET /api/health` through the proxy returned
  `200 {"status":"ok","checks":{"postgres":{"ok":true,"version":"16.14",...},"redis":{"ok":true,...}}}`.
  `pg_stat_activity` showed the API's two connections (`client backend`) on database `fathom`. A row with
  no database name turned out to be Postgres's own `logical replication launcher` background process.

**What this does not prove:**

- **The rendered page was checked by hand once, not automatically.** The user opened
  http://localhost:5174 in a browser and the page worked. The tests render it in jsdom, and curl only
  sees the HTML shell; there is no automated browser test until Playwright in Phase 5.
- **The cutoff guarantees resolution, not installation from elsewhere.** `npm ci` installs whatever the
  lockfile says without re-checking dates; what makes it safe is that the lockfile was resolved under the
  cutoff and the script checked it. A hand-edited lockfile would only be caught by rerunning the script,
  and nothing runs it automatically yet.
- **The publish dates come from the registries.** The script trusts PyPI's upload times and npm's `time`
  field.
- **Only Node's major version is enforced.** Patch versions match because they're pinned in the same
  places, not because a check fails on a mismatch.
- **Docker base images are outside the rule** until the user extends it.
- **File watching without fsevents is unverified.** The dev server ran, but nothing tested that editing a
  file reloads the page.

## 6. Interview defense

**"Why wait 14 days for dependencies? Isn't that paranoid?"**
Supply-chain attacks work by getting malicious code into a popular package's newest version, and most
are detected and pulled within days. Waiting two weeks keeps those versions out at almost no cost: the
pins are a patch or two behind. The important part is that the rule covers the whole lockfile, because the
attack usually lands in a package you never chose directly. Here, 15 direct web dependencies meant 175
lockfile entries.

**"Doesn't that leave you exposed to vulnerabilities that were just fixed?"** (hard)
Yes, that's the tradeoff, and it's why the rule has an exception path: a security fix younger than 14 days
can go in with an explicit, recorded decision. The default protects against the common case, a bad new
release. The exception handles the rare one, a critical fix, deliberately and visibly. What I avoided was a
silent default in either direction.

**"Why not just use npm audit or Dependabot?"**
They answer a different question: is anything I already have known to be vulnerable? A freshly poisoned
release isn't in any advisory database yet, which is exactly when it does damage. Audit tools and an age
cutoff complement each other.

**"Your frontend tests mock fetch. What do they actually prove?"**
That the page turns each kind of response into the right message: healthy, degraded with the failing
service, unreachable with the status. They don't prove the API answers. The backend tests prove that
against real Postgres and Redis, and the step 5 gate test calls the endpoint through the real proxy. I also
made unmocked fetch throw in every test, so a test can't accidentally pass by hitting the network.

**"Why install Node from a tarball instead of using nvm?"**
The age rule required 24.21.0, Homebrew only had 24.22.0, and nodejs.org's installer needs admin rights
and could shadow the system Node for every project. No version manager was installed, and adding one is
another tool to trust. A checksum-verified tarball in my home folder was the smallest change. Step 5's
Makefile hides the PATH prefix.

**Honest weaknesses:** the age check runs by hand, not automatically; only Node's major version is
enforced; Docker images aren't covered; the page in a real browser was checked by hand once, with no
automated browser test until Phase 5; and `fsevents` is unapproved, so file watching is untested.

## 7. What comes next

Step 5 runs the web app in Docker on `node:24.21.0-bookworm-slim`. The container must start Vite with
`--host`, because by default it listens only on localhost inside the container, and must set
`API_PROXY_TARGET=http://api:8000` and `WEB_PORT=5173`. The Makefile's npm targets will use `NODE24_BIN`
so the PATH prefix disappears. Step 6's CI reads `.nvmrc` and runs the same four npm scripts. If this
step were wrong, the symptoms would be: a page showing healthy when the API isn't (prevented by the
unreachable classification and its tests), CI and local disagreeing (prevented by one pinned Node and the
guards), or a fresh release slipping into a lockfile (prevented by the cutoffs, and caught by the script
when it's run).
