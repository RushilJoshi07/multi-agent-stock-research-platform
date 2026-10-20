# Phase 0 · Step 3: The health check

Build step 3. Decision notes: [0001 Python 3.13](../../decisions/0001-python-3.13.md),
[0002 Postgres 16 on Debian](../../decisions/0002-postgres-16-debian-selective-restore.md),
[0003 uv lockfile](../../decisions/0003-uv-lockfile.md), [0005 host ports](../../decisions/0005-host-ports.md).

## 1. What this does, and what it doesn't

Fathom now has its first running code: a FastAPI app with one endpoint, `GET /health`. It runs a
real query against Postgres (`SELECT version()`) and a real `PING` against Redis, and answers
**200** when both work and **503** when either fails, with the reason. Around it sits the test
setup every later step reuses: Postgres and Redis in Docker, a separate test database, a guard that
stops any test from reaching the old project's database, and a guard that stops any test from
reaching the internet.

What it does not do yet. The API itself doesn't run in a container (step 5 adds the `api` and `web`
services and the one-command start). There are no tables, no auth and no other endpoints. The health
check says the services answer; it doesn't say the schema is right or that data is fresh. Those
checks belong to later phases.

## 2. The code, explained

### `compose.yaml` (postgres and redis only, for now)

```yaml
image: postgres:16.14-bookworm
```
The exact version of the old database (16.14), on Debian. Same major version means the Phase 1
dump restores cleanly; Debian means text sorts the same way as the old glibc-based database
(decision 0002). The tag was confirmed on Docker Hub (HTTP 200) and the container ran healthy.

```yaml
ports:
  - "127.0.0.1:${POSTGRES_HOST_PORT:-5433}:5432"
```
Inside Docker, Postgres listens on its normal 5432. On the Mac it's published on **5433**, because
the old project's Postgres already owns 5432 and both must run at once for the Phase 1 restore
(decision 0005). `127.0.0.1:` publishes it on this machine only. Without it, Docker publishes on
every network interface, and anyone on the same Wi-Fi could try the database with the default password.

```yaml
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-change-me-local}
```
`${VAR:-default}` reads the value from `.env` if it's set and falls back to the same placeholder
as `.env.example` otherwise. So a fresh checkout works with no `.env` file, and the real `.env`
can still override it.

```yaml
- ./docker/postgres/init:/docker-entrypoint-initdb.d:ro
```
The official Postgres image runs every `.sql` file in that folder, once, when the data volume is
first created. Ours holds one line, `CREATE DATABASE fathom_test;`. **Once, at creation** matters:
if the volume already exists, editing the file does nothing. To re-run it you must delete the
volume, which deletes the data, so that is an ask-first action.

```yaml
command: ["redis-server", "--appendonly", "yes"]
```
Append-only mode writes every change to disk. Phase 4's job queue lives in Redis, and the plan wants
jobs to survive restarts. It costs nothing now and avoids changing persistence later.

The `healthcheck` blocks (`pg_isready`, `redis-cli ping`) let `docker compose up --wait` block until
both services actually accept connections, not merely until the containers have started.

### `pyproject.toml`

Every direct dependency is pinned exactly (`==`). Packages the old project also uses get the exact
version installed in its venv (FastAPI 0.141.1, SQLAlchemy 2.0.51, psycopg2-binary 2.9.12, pydantic
2.13.4, pydantic-settings 2.14.2, uvicorn 0.52.3), so the code imported in Phase 1 runs on the
versions its tests passed with. New packages got the latest PyPI release on 2026-10-20: redis
8.1.0, pytest-socket 0.8.1, ruff 0.17.1. `uv.lock` then pins everything underneath (36 packages).
`uv tree` confirmed the direct dependencies resolved to exactly these versions.

```toml
addopts = "-m 'not gate and not live' --disable-socket --allow-unix-socket --allow-hosts=127.0.0.1,::1"
```
Every pytest run gets these flags, locally and in CI alike:
- `-m 'not gate and not live'` skips phase-gate tests (slow, they start the whole stack) and live
  tests (real external APIs). Passing `-m gate` later overrides it, because pytest uses the last `-m`.
- `--allow-hosts=127.0.0.1,::1` makes any connection to an address other than this machine raise
  `SocketConnectBlockedError` inside `connect()`, before a packet is sent. The list uses IP
  addresses, not the name `localhost`, so nothing depends on how the name resolves.
- `--disable-socket` is the fallback. Reading pytest-socket 0.8.1's source showed that when
  `--allow-hosts` is set, the host list takes over, and the full block applies only to tests with no list.
- `--allow-unix-socket` permits local Unix sockets, which never leave the machine.

`pythonpath = ["src"]` lets tests import `api` and `core` directly.

### `src/core/config.py`

```python
model_config = SettingsConfigDict(env_file=".env", extra="ignore")
database_url: str = "postgresql://fathom:change-me-local@localhost:5433/fathom"
```
pydantic-settings fills each field from the environment variable of the same name
(`DATABASE_URL`), then from `.env`, then from the default. The defaults match `.env.example`,
including port 5433. `extra="ignore"` lets `.env` hold keys this class doesn't know yet (Alpaca,
Finnhub) without raising an error.

```python
@lru_cache
def get_settings() -> Settings:
```
The settings are read once and reused. Tests change behavior by overriding the dependencies that
use these settings, not by editing the environment.

### `src/core/db.py`

```python
connect_args={"connect_timeout": CONNECT_TIMEOUT_S},   # 2 seconds
```
Without this, connecting to a Postgres that isn't answering can wait far longer, and `/health`
would hang instead of reporting the failure. A health check that hangs when things are broken is
useless exactly when you need it.

```python
pool_pre_ping=True,
```
SQLAlchemy keeps connections open in a pool. If Postgres restarts, the pooled connections are dead.
Pre-ping tests a connection when it's taken from the pool and replaces it if it's dead, so the first
request after a database restart doesn't fail for a stale reason.

`get_engine()` is cached for the same reason as the settings: one engine and one pool per process.

### `src/core/redis.py`

```python
HEALTH_CLIENT_NAME = "fathom-health"
...
redis.Redis.from_url(url, client_name=client_name, socket_connect_timeout=TIMEOUT_S, socket_timeout=TIMEOUT_S)
```
`client_name` makes redis-py send `CLIENT SETNAME` when it connects, so this connection shows up
under that name in Redis's `CLIENT LIST`. That's what lets the test identify the app's own
connection (section 5). The two timeouts do for Redis what `connect_timeout` does for Postgres.

### `src/api/routes/health.py`

```python
def check_postgres(engine: Engine) -> dict[str, Any]:
    ...
    with engine.connect() as conn:
        full = conn.execute(text("SELECT version()")).scalar_one()
    except Exception as exc:
        return {"ok": False, "error": describe_error(exc)}
```
A real query, not just opening a connection: it proves the server answers SQL. Catching every
exception is deliberate here and nowhere else. Whatever goes wrong, a health check's job is to say so
in its response, not to crash with a 500 that hides which service failed.

```python
_PG_VERSION = re.compile(r"PostgreSQL (\d+(?:\.\d+)*)")
```
`version()` returns a long string (`PostgreSQL 16.14 (Debian ...) on aarch64 ...`). The pattern
extracts `16.14`. If it ever fails to match, the full string is returned rather than nothing,
because missing data is reported, never hidden.

```python
def check_redis(client: Redis) -> dict[str, Any]:
    client.ping()
```
Same pattern for Redis.

```python
_URL_PASSWORD = re.compile(r"://([^:/@\s]+):[^@\s]+@")
def describe_error(exc: Exception) -> str:
```
Error messages go into the HTTP response, so they must never carry a password. This keeps only
the first line of the exception (SQLAlchemy appends multi-line background text) and replaces the
password in any `scheme://user:password@` URL with `***`. Real connection errors seen in the test
run carried no password, but the masking doesn't rely on that.

```python
@router.get("/health")
def health(
    engine: Annotated[Engine, Depends(get_engine)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    ...
    status_code=200 if ok else 503,
    content={"status": "ok" if ok else "degraded", "checks": checks},
```
FastAPI calls `get_engine()` and `get_redis()` and passes the results in. That indirection is what
makes the endpoint testable: a test can swap in a different engine (the test database, or one aimed
at a closed port) without touching this code. The `Annotated[..., Depends(...)]` form replaced
`engine: Engine = Depends(get_engine)` after ruff's B008 rule flagged the function call in a default
argument. FastAPI's current documentation uses the `Annotated` form.

The function is plain `def`, not `async def`. FastAPI runs plain functions in a worker thread, so the
blocking database and Redis calls don't stall other requests.

### `src/api/main.py`

`create_app()` builds the app; `app = create_app()` is what uvicorn will load in step 5. Tests call
`create_app()` themselves to get a fresh app whose dependency overrides don't leak between tests.

### `tests/conftest.py`: the guard

```python
port = url.port or OLD_PROJECT_PG_PORT  # no port means libpq's default, 5432
if port == OLD_PROJECT_PG_PORT:
    pytest.exit(...)
if url.database != TEST_DB_NAME:
    pytest.exit(...)
```
Before any database connection, the test database URL is checked. A URL with no port counts as
5432, because that's what the Postgres client library would connect to. `pytest.exit` stops the
whole run, not just one test. Then, after connecting, `SELECT current_database()` must return
`fathom_test`. That catches a URL that looks right but lands somewhere else.

```python
return url.render_as_string(hide_password=False)
```
SQLAlchemy masks the password when it turns a URL back into text. Without `hide_password=False`,
the engine would get `***` as the password and fail to authenticate.

The fixtures give each test a fresh app pointed at `fathom_test`, a Redis client with a **unique
name per test** (`fathom-health-test-<random>`), and a separately named observer connection used only
for inspecting Redis, so inspecting never changes what the health client's connection last ran.

## 3. Decisions and rejected alternatives

**Only Postgres and Redis in `compose.yaml` now, the rest in step 5.** The test needed real services
before the API container exists. The old project's Homebrew Postgres was already running, but it is
the database we must never touch, so using it was rejected outright. A test-container library, which
starts throwaway containers from inside pytest, was also rejected. It adds a dependency, the tests
would need access to the Docker socket, and the test services would differ from the stack Fathom
actually runs. Writing the two services now means the tests use the same images and ports as the final
stack. Cost: `compose.yaml` is unfinished until step 5.

**Exact pins, not version ranges.** Fathom is an application, not a library, so nothing downstream
needs flexibility, and upgrades should be deliberate. The old project's `>=` ranges are why nobody
could say which versions its tests passed with ([decision 0003](../../decisions/0003-uv-lockfile.md)).
The cost is upgrading by hand.

**SQLAlchemy 2.0.51, though 2.1.5 exists.** The old code was only ever tested on 2.0. Moving to 2.1
can wait until after the Phase 1 import passes on the version it was written for. Same reasoning for
keeping psycopg2 rather than psycopg 3: switching the database driver while importing code that uses it
would mix two changes.

**503 on failure, not 200 with `ok: false`.** Docker healthchecks, load balancers and uptime monitors
read the status code, not the body. A 200 with bad news inside would show as healthy to all of them.

**Proof of the PING by connection name, not by Redis's command counter.** The first design compared
Redis's server-wide PING counter (`cmdstat_ping.calls`) before and after the request. Review caught
that Docker's healthcheck runs `redis-cli ping` every 5 seconds against the same server (CI's service
healthcheck does too), so the counter could rise with no help from the endpoint. The counter
couldn't tell the app's PING from anyone else's. The fix names the app's connection, and the name is
unique per test, so no other process can create that connection.

**Guarding the test database by port and name, plus a check after connecting.** A port check alone
would pass a URL aimed at the wrong database on port 5433. A name check alone would pass
`localhost:5432/fathom_test` if someone created that database on the old server. The check after
connecting catches what both miss. CI's service containers will map to 5433 too (step 6), so the
guard needs no CI exception.

**A plain `def` endpoint, not `async def`.** Async would need async database and Redis drivers, a bigger
change than one health check justifies. Reversible later, per endpoint.

**pytest-socket in addition to "CI has no secrets".** Missing keys only stop services that need keys.
yfinance and SEC EDGAR need none, so a stray test could still hit them. A guard at the connection level
blocks everything except this machine, whatever the service.

## 4. Concepts introduced

**Health check.** An endpoint that reports whether a service and the things it depends on work. It's
only useful if it's honest: a check that returns 200 without really testing anything gives false
confidence exactly when something is broken. That's why the tests prove the queries actually run,
not just that the response looks right.

**Dependency injection.** Code receives what it needs (an engine, a Redis client) instead of
creating it. In FastAPI that's `Depends`. The payoff here: tests replace the real dependency with a
test one (`app.dependency_overrides[get_engine] = ...`), so the same endpoint code runs against the test
database, or against a closed port to simulate an outage.

**Connection pool.** Opening a database connection is slow, so SQLAlchemy keeps a few open and reuses
them. The cost is that pooled connections can go stale when the server restarts, which `pool_pre_ping`
handles.

**Timeouts.** A dependency that is down can fail in two ways: fast (connection refused) or slow
(no answer at all). Without a timeout, the slow way makes the caller hang. Both the Postgres and Redis
clients here give up after 2 seconds.

**Test isolation from real data.** Tests create and delete data freely, so they must run against a
database whose loss doesn't matter. Here that's `fathom_test`, enforced in code before any connection.
The failure this prevents is concrete: a test that empties a table, pointed at the wrong URL, empties
the real table.

**`CLIENT SETNAME` and `CLIENT LIST`.** Redis lets a connection name itself. `CLIENT LIST` shows
every open connection with its name and the last command it ran (`cmd=`). This makes it possible to
verify one particular connection's behavior on a server that other processes also use.

## 5. Verification

**What was run:**

`uv run pytest -v`: 7 passed, 0 failed.

| Test | What it proves |
| --- | --- |
| `test_health_is_green_when_both_services_are_up` | 200 and `ok` when both services are up. |
| `test_health_runs_a_real_select_version` | A listener on the engine recorded `SELECT version()` being sent during the request, and the reported version equals the server's own `SHOW server_version`. Output: `reported version: '16.14'; SHOW server_version: '16.14 (Debian 16.14-1.pgdg12+1)'`. |
| `test_health_pings_redis_on_its_own_named_connection` | Before the request, no connection has this test's unique name. After it, exactly one does, and its last command is `ping`. Output: `'name': 'fathom-health-test-1b35f80b3fde', ... 'cmd': 'ping', ... 'lib-name': 'redis-py', 'lib-ver': '8.1.0'`. |
| `test_health_is_503_when_postgres_is_down` | Engine aimed at `127.0.0.1:1`: 503, `postgres.ok == false`, Redis still ok, and the URL's password is absent from the error. Error: `OperationalError: (psycopg2.OperationalError) connection to server at "127.0.0.1", port 1 failed: Connection refused`. |
| `test_health_is_503_when_redis_is_down` | Redis client aimed at `127.0.0.1:1`: 503, `redis.ok == false`, Postgres still ok. Error: `ConnectionError: Error 61 connecting to 127.0.0.1:1. Connection refused.` |
| `test_describe_error_masks_url_passwords` | `postgresql://fathom:hunter2@db:5432/x` becomes `postgresql://fathom:***@db:5432/x`. |
| `test_outbound_connection_is_blocked` | Connecting to `1.1.1.1:443` raises `SocketConnectBlockedError`. |

The guard was also shown working outside the test suite, by setting `DATABASE_URL_TEST` three ways:
port 5432 stopped the run ("uses port 5432, the old project's Postgres. Refusing."); no port stopped it
the same way; database `fathom` stopped it ("not 'fathom_test'"). A read-only query on the old server
afterwards found 0 connections from the `fathom` user.

`ruff check`: all checks passed (after the `Annotated` change). `ruff format --check`: 34 files
already formatted. Ruff 0.17 also checks Python code blocks inside the 22 Markdown files, which is why
the count is higher than the 12 Python files.

**What this does not prove:**

- **The real `fathom` database is never exercised.** Every test uses `fathom_test`. The app's own
  `DATABASE_URL` is first used when the API runs in step 5.
- **The guard covers `DATABASE_URL_TEST` only, not `DATABASE_URL`.** If `.env` set `DATABASE_URL` to
  port 5432, the running app would connect to the old database. Today it would only run
  `SELECT version()`, which is harmless, but Phase 1 writes data. A guard on the app's own URL should
  land before Phase 1's restore.
- **The version check accepts any 16.x** (`startswith("16.")`); it checks the major version, as the
  restore requires, not the exact patch.
- **Latency numbers aren't checked.** `latency_ms` is reported but no test asserts anything about it.
- **The PING proof depends on `ping` being the last command** on the health connection. If the health
  check ever sends another command after PING, this test fails. That's intended, but it would need
  updating along with the check.
- **The full stack isn't tested.** Stopping the real Redis container and seeing 503 is step 5's gate test.

**Warnings in the test output:**
- `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2
  instead.` Recorded in STATUS.md Known issues; no new dependency added.
- pytest-socket's own warning for the blocked `1.1.1.1` connection, which is the expected result of
  the network guard test.

**Observed but not relied on:** `CLIENT LIST` shows `resp=3`, meaning redis-py 8.1.0 talked to
Redis 7.4.11 using protocol version 3. Nothing here depends on it.

## 6. Interview defense

**"How do you know your health check isn't just returning 200?"**
Three ways, each tested. For Postgres, a listener on the database engine records every SQL statement
sent, and the test asserts `SELECT version()` was among them, then checks the reported version against
the server's own answer. For Redis, the health connection names itself with a fresh random name per test,
and after the request Redis's own connection list shows that connection with `ping` as its last command.
And both failure paths are tested: aim either client at a closed port and the endpoint returns 503 with
the right service marked down.

**"Your first Redis proof was wrong. What happened?"** (hard)
I first compared Redis's server-wide PING counter before and after the request. In review it was pointed
out that Docker's healthcheck pings the same server every five seconds, so the counter could rise without
my endpoint doing anything. The test would have passed even if the endpoint never pinged. I switched to
identifying the app's own connection by a unique name. The lesson: a test has to rule out every other
cause of the thing it observes, not just confirm that the thing happened.

**"Why not mock the database in tests? Real databases are slow and flaky."**
These seven tests take well under a second. The bugs this project has to catch live in the real
behavior: a query that doesn't run, a timeout that doesn't fire, a password in an error message, a URL
that points at the wrong database. A mock would return whatever I told it to and prove none of that.
The project rule is real Postgres for anything that touches data.

**"Why didn't you use testcontainers to start Postgres from the tests?"**
It's a good tool, but it would make the test services differ from the stack the app actually runs, add a
dependency, and require the tests to reach Docker's socket. Writing the two Compose services early gave
me the same images and ports as production-like local runs, with nothing extra.

**"What stops a test from wiping real data?"**
A check that runs before any connection: the test database URL can't use port 5432 (the old project's
database) and must name `fathom_test`, and after connecting, the server must confirm it's `fathom_test`.
I ran it with three bad URLs and each one stopped the whole run. The honest gap: that guard covers the
test URL, not the app's own `DATABASE_URL`, and I've flagged closing that before Phase 1 writes any data.

**Honest weaknesses:** the endpoint is synchronous; the real `fathom` database isn't exercised until step
5; the app's own database URL has no guard yet; and the version check accepts any 16.x patch.

## 7. What comes next

Step 4 adds the empty React app. Step 5 runs this API in a container next to Postgres and Redis, adds
`make up`, and adds the Phase 0 gate test, which calls this endpoint over HTTP, stops the real Redis
container, and expects 503. If this step were wrong, the symptoms would show up there as a green gate on
a broken stack, which is exactly what the "isn't hard-coded green" checks are designed to prevent.
Before Phase 1 restores data into `fathom`, the app's own `DATABASE_URL` needs the same 5432 guard the
test URL has.
