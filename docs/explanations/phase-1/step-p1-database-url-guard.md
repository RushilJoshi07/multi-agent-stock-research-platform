# Phase 1 · Step P1: The old-database guard

Commit `dc543d1`. Plan: [phase-1-import-foundations.md](../../../plans/phase-1-import-foundations.md),
section 3a and "Changes from review" item 5. Related decision notes:
[0002 selective restore](../../decisions/0002-postgres-16-debian-selective-restore.md),
[0005 host ports](../../decisions/0005-host-ports.md).

## 1. What this does, and what it doesn't

The old project's database, `strategy_research`, lives in a Homebrew Postgres server on this Mac,
listening on the standard port 5432. Phase 1 restores its price history into Fathom, so from now
on Fathom's code and the old database sit next to each other on one machine. One wrong
`DATABASE_URL` in a `.env` file, and Fathom's ingest jobs, migrations or test fixtures (which
truncate tables) would run against the old data. Nothing else in this project is that hard to
undo. This step makes that mistake impossible from Python, in two layers plus a test that keeps
the layers from being bypassed.

1. **A URL check** (`refuse_old_database` in `src/core/db_guard.py`). It runs inside
   `core.db.make_engine` before any SQLAlchemy engine exists, so a refused URL never opens a
   connection. The core rule: port 5432, or no port at all, is allowed only when the host is
   `postgres`, Fathom's own Compose service. Any database name starting with `strategy_research`
   is refused everywhere.
2. **A server check** (`refuse_old_server`). It runs on every new connection, and asks the
   server that was actually reached whether it has a database named like the old project's. If
   it does, the connection is closed and refused.
3. **A scan** (`tests/unit/test_connection_paths.py`). It reads every Python file in the repo and
   fails if anything other than `src/core/db.py` could open a Postgres connection on its own,
   because such code would skip both layers.

What this does not do:
- **It guards Python only.** The `psql`, `pg_dump` and `pg_restore` command-line tools don't go
  through `make_engine`. The Phase 1 restore uses `pg_dump` against the old database on purpose,
  read-only. Those commands are protected by how they're run (a read-only session setting), not
  by this code.
- **The test database name** (`fathom_test`) is still checked separately by
  `checked_test_db_url()` in `tests/conftest.py`. This guard doesn't replace that check.
- **Known limits, accepted when the step was approved.** None of these is closed today:
  - The scan doesn't detect dynamic imports.
  - No test proves that a connection refused by the server check actually gets closed.
  - A connection string handed to pandas through a variable (rather than written out as a
    string) isn't detected.

## 2. The code, explained

### `src/core/db.py`

```python
def make_engine(url: str) -> Engine:
    refuse_old_database(url)
    engine = create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 2})
    event.listen(engine, "connect", _check_server)
    return engine
```

`make_engine` was already the one function that built engines (the API, the health check and
the test fixtures all use it). Putting the guard here, rather than in each caller, means a new
caller is covered without anyone remembering to add a check.
- **Order matters.** `refuse_old_database` comes before `create_engine`, so a refused URL never
  even creates a connection pool. The test `test_refusal_happens_before_any_engine_exists`
  proves this by replacing `create_engine` with a function that fails the test if it's called.
- **The listener.** `event.listen(engine, "connect", ...)` attaches to SQLAlchemy's connection
  pool. The pool calls it each time it opens a new database connection. That's not every query:
  a pool reuses connections. But every distinct connection is checked once, when it's created.

```python
def _check_server(dbapi_connection, connection_record) -> None:
    try:
        refuse_old_server(dbapi_connection)
    except Exception:
        dbapi_connection.close()
        raise
```

If the check refuses, or the check query itself fails, the connection is closed before the error
is raised again. Without the `close()`, a refused connection to the old server could linger open
until garbage collection. Catching `Exception` rather than only `OldDatabaseRefused` is
deliberate: if the query can't run, nobody knows which server this is, so the connection is
treated as unsafe (it "fails closed"). As noted above, no test proves the `close()` happens.

### `src/core/db_guard.py`: the URL check

```python
OLD_PROJECT_PG_PORT = 5432
OLD_PROJECT_DB_PREFIX = "strategy_research"
COMPOSE_PG_HOST = "postgres"
```

Why is the host `postgres` allowed on 5432 at all? Inside Docker, the API container reaches
Fathom's database by the Compose service name `postgres`, on the container port 5432
(`compose.yaml`: `@postgres:5432/fathom`). From the Mac, Fathom's database is on 5433 (decision
0005). So "refuse port 5432" alone would break the running API, and "refuse localhost" alone
would miss `host.docker.internal:5432`. That name, from inside a container, means "the Mac",
which is where the old database runs. The rule therefore checks host and port together, as an
allow-list: there is exactly one acceptable combination with 5432, and every other host on 5432
is refused. An allow-list means hosts nobody thought of (the Mac's LAN address, its hostname,
`gateway.docker.internal`) are refused too.

```python
REDIRECTING_QUERY_KEYS = ("hostaddr", "dsn", "service")
REDIRECTING_ENV_VARS = ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")
```

Postgres connections are made by libpq, the C library under psycopg2. libpq has ways to choose
where to connect that aren't the URL's host:
- `hostaddr=127.0.0.1` makes it connect to that IP address and use `host` only for
  authentication. So `postgres:5432/fathom?hostaddr=127.0.0.1` *looks* like Fathom's database
  but reaches the old one.
- `dsn=` and `service=` can carry a `hostaddr` inside them.
- libpq also reads `PGHOSTADDR` and the service-file variables from the environment.

None of these is needed by Fathom, so any of them present is a refusal. That's simpler and safer
than parsing them. `PGHOST` and `PGPORT` aren't in the list on purpose: a URL with no host is
already refused, and an explicit URL port wins over `PGPORT`.

```python
for database in [parsed.database or "", *_query_values(parsed, "dbname")]:
    if database.lower().startswith(OLD_PROJECT_DB_PREFIX):
```

The name check reads the query's `dbname` as well as the path, because SQLAlchemy passes query
options through to psycopg2, and a `?dbname=` replaces the database named in the path. The first
version checked only the path, and the code review caught it.
- **Why a prefix:** it covers both `strategy_research` and the old `strategy_research_test`.
- **Why lowercased:** a mixed-case name in the URL still means the same database to libpq (see
  the boilerplate note at the end of this section).

```python
query_hosts = [_split_host_port(value) for value in _query_values(parsed, "host")]
query_ports = _query_values(parsed, "port")
if len(query_hosts) > 1 or len(query_ports) > 1:
    refuse("a list of hosts or ports")
```

libpq accepts a list of hosts (`?host=a&host=b`, or `?host=a,b`) and tries them in order,
connecting to the first one that answers. The first version read only the last value. So
`?host=localhost:5432&host=postgres` was allowed, and libpq would connect to `localhost:5432`,
the old database, first. Lists are now refused outright, since nothing in Fathom needs one.
`_split_host_port` handles `host:port` written inside a query host (including bracketed IPv6
`[::1]:5432`). It mirrors how SQLAlchemy's psycopg2 dialect splits them, so the guard sees the
same host and port that libpq will.

```python
port = int(port_text) if port_text else OLD_PROJECT_PG_PORT
if port == OLD_PROJECT_PG_PORT and host.lower() != COMPOSE_PG_HOST:
```

These two lines encode the defaults libpq would apply:
- **No port** means 5432.
- **No host** (`postgresql:///fathom`) means a Unix socket on this machine, which is the Homebrew
  server. An empty host string is never `postgres`, so it's refused.
- **A non-numeric port** is refused with the guard's own error, so every refusal looks the same.

```python
def _shown(url):
    shown = url.set(query={}).render_as_string(hide_password=True)
```

The error message shows the URL so you can see what was refused, but a password must never land
in a log. `hide_password=True` hides only the password in `user:password@`. A password can also
sit in the query (`?password=` or inside `dsn=`), so the message leaves the whole query out and
names the offending key in words instead.

### `src/core/db_guard.py`: the server check

```python
cursor.execute(
    "SELECT datname FROM pg_database WHERE datname LIKE %s ORDER BY datname LIMIT 1",
    (OLD_PROJECT_DB_PREFIX + "%",),
)
```

A URL can't show where a host name resolves. If someone added `127.0.0.1 postgres` to
`/etc/hosts`, which is a common trick to make one `.env` work both on the Mac and in Docker, then
`postgres:5432` from the Mac would reach the old server and pass the URL check. The server check
asks the server itself. `pg_database` is the catalog of databases on a Postgres server, readable
by every user by default. The old server always has `strategy_research`. Fathom's server never
has one, because Fathom names its databases `fathom` and `fathom_test`. So the presence of that
name is a reliable fingerprint, and it doesn't depend on how the connection got there.

`dbapi_connection.rollback()` afterwards: psycopg2 opens a transaction for any query, so without
the rollback, the pool would hold connections left "idle in transaction". That state can hold
locks and block schema changes. After the change, `pg_stat_activity` showed 0 such connections
on `fathom`.

Boilerplate, not explained further: the `OldDatabaseRefused(RuntimeError)` class (a subclass, so
existing `RuntimeError` handling still works), the cursor `try/finally`, and `.lower()` on names.
Postgres folds unquoted names to lower case, so the lowercasing keeps `Strategy_Research` from
slipping past the prefix check.

### `tests/unit/test_connection_paths.py`: the scan

The two layers protect only connections built by `make_engine`. Code that calls `create_engine`
itself, or imports psycopg2 and calls `psycopg2.connect`, skips both. Later Phase 1 steps import
old-project code, which built its own engines in three kinds of place:
`src/data_pipeline/db/session.py`, `tests/conftest.py`, and Alembic's `migrations/env.py`. Alembic
is the database-migration tool, and its default template uses `engine_from_config`.

The scan parses each file with Python's `ast` module (it reads the code's structure, it never
runs it) and flags:
- **imports of a Postgres driver:** psycopg2, psycopg (version 3), asyncpg, pg8000;
- **SQLAlchemy's engine and pool factories, sync and async:** whether imported by name or called
  as an attribute like `sa.create_engine(...)`;
- **pandas `read_sql*` / `to_sql` given a connection string,** which makes pandas build its own
  engine internally.

It walks the whole repo except `.venv` (installed packages), `node_modules`, `.git`, and
`.claude/worktrees`. Worktrees are other branches' checkouts, each of which scans itself.
- **Why the whole repo:** the first version scanned a fixed list of folders, which a new
  top-level folder would have escaped.
- **Why `os.walk`:** it lets the scan prune excluded trees in place (`dirnames[:] = ...`), so it
  never reads thousands of files under `.venv` only to throw them away.

## 3. Decisions and rejected alternatives

**An allow-list for port 5432, not a deny-list of hosts.** The rejected version refused
`localhost`, `127.0.0.1` and `::1` on 5432 and allowed the rest. It would have let through
`host.docker.internal:5432`, the Mac's LAN IP, and its `.local` hostname. All of them reach the
old server, and no list of them is ever complete. The allow-list has one entry, and everything
unknown is refused. Cost to change later: one constant.

**Refuse port 5432 outright instead?** Rejected because it breaks the running API, which connects
to `postgres:5432` inside Docker. Moving Fathom's container port to 5433 as well would have
avoided the special case, but it means changing the Compose file, the healthcheck and CI's
service mapping to fit a guard. The guard should fit the setup, not the other way round.

**A server check, not only a URL check.** The URL check can't see DNS, `/etc/hosts`, or tricks
nobody has listed yet. Checking the server reached is the only layer that holds whatever route
was taken. Rejected alternatives:
- **Checking `inet_server_port()`:** inside Docker, Fathom's own server also reports port 5432,
  so it can't tell the two apart.
- **Checking `version()`:** both servers report 16.14. The old one says "(Homebrew)", but a
  version string is fragile.

The database-name fingerprint is specific and stable. Cost: one small query per new connection.
Connections are pooled, so that's a handful per process, not one per request.

**Refuse redirecting options instead of interpreting them.** We could have parsed `hostaddr`,
`dsn` and service files and run their contents through the same host and port rule. That's more
code, more libpq rules to get exactly right, and none of these options is used by Fathom. If one
is ever needed, the guard will say so loudly, and the rule can be extended deliberately then.

**Inside `make_engine`, not a pydantic validator on the settings.** A settings validator would
only check `DATABASE_URL` and `DATABASE_URL_TEST`. A URL built any other way (a CLI flag, a
script, Alembic's `-x` argument) would skip it. Every engine passes through `make_engine`, and the
scan enforces that, so the guard covers every source of URL.

**A static scan, not runtime patching.** Patching `sqlalchemy.create_engine` at import time to
refuse all callers but `make_engine` would catch dynamic imports too. But it's fragile (import
order matters, and the patched function can be captured before the patch), and it's surprising
to anyone reading the code. The scan is plain to read, fails with a file and a line number, and
runs in milliseconds.

**Consequence for Phase 6 (recorded for the handoff).** A managed cloud database such as Amazon
RDS listens on 5432 by default, and this guard will refuse it. The agreed fix: production gets an
explicit allow for its managed database host, never a weaker rule. Until then, refusing it is the
right behaviour.

## 4. Concepts introduced

**libpq and its defaults.** psycopg2 hands connection settings to libpq, and libpq fills the gaps:
- **no host** means a Unix socket on the local machine;
- **no port** means 5432 (or `PGPORT`);
- **`hostaddr`** overrides where `host` points.

A guard that checks only what's written in the URL is checking the wrong thing. It has to check
what libpq *will do*. Every bypass the reviews found came from this gap: a host list, `hostaddr`,
`?dbname=`.

**Defence in depth.** Two independent checks that fail differently. The URL check is fast and
runs before any network traffic, but it's blind to DNS. The server check sees the truth, but it
runs after a connection exists. Each one covers the other's blind spot. Concrete failure without
the second layer: an `/etc/hosts` entry turns a passing `postgres:5432` into a connection to the
old database.

**Fail closed.** When a safety check can't reach a verdict (the server query errors), the system
treats it as a refusal, not a pass. The opposite, fail open, would mean a permissions glitch
silently disables the guard.

**Tests that can fail.** A guard test that only shows allowed URLs pass proves nothing. Every
check here was first shown failing:
- 17 failures against the unguarded code;
- then 12 more for the review findings;
- then 1 for the `dsn=` password.

The scanner has 17 known bypasses it must flag and 5 clean snippets it must not. The server check
is tested by pointing its fingerprint at `fathom_test`, a name the test server does have, so it
must refuse a real connection. The engine is built before the fingerprint changes, so the URL
check can't be what refuses.

## 5. Verification

What was run (2026-10-28, on `dc543d1`'s tree):
- `tests/unit/test_db_guard.py`: **39 passed.**
  - 25 refused URLs: the loopback forms on 5432, a missing port, Unix sockets, the query
    overrides, host lists, `host:port` inside the query, `hostaddr`/`dsn`/`service`, the old names
    in the path and in `?dbname=`, and a non-numeric port.
  - 5 allowed URLs.
  - 3 libpq environment variables.
  - Engine order (refusal before `create_engine`).
  - Passwords hidden in all three places a password can sit.
  - The server check, both refusing and passing, against real Postgres on 5433.
- `tests/unit/test_connection_paths.py`: **25 passed.**
  - The real repo: 17 Python files scanned, 0 offenders.
  - A temporary tree proving new folders are read and only the four exclusions are skipped.
  - The 17 bypass and 5 clean snippets.
  - Separately, bypass files planted for a moment in `src/`, `tests/` and `scripts/` each made
    the real-repo check fail by name. All were deleted.
- `make test`: 71 passed, 6 deselected (gate tests). `make lint`: exit 0.
- **Against the real setup:**
  - The API reloaded itself and its engine is `postgres:5432/fathom`; `/health` is ok.
  - 0 connections idle in transaction.
  - On the Mac, `DATABASE_URL=postgresql://rushil@localhost:5432/strategy_research` and
    `postgresql:///fathom` were both refused before any connection was opened.
  - `/etc/hosts` has no `postgres` entry, and no `PG*` variables are set.
- **Two code reviews:**
  - The first found the host-list, `hostaddr`/`dsn`/`service` and `?dbname=` bypasses, plus the
    scan's narrow scope.
  - The second confirmed every fix against the installed SQLAlchemy 2.0.51 source and found one
    minor leak (a password inside `dsn=` in the error message), fixed test first.

What this does not prove:
- **The server check has never run against the real old server.** That would mean connecting to
  it, which is the thing being prevented. It is proven only with a stand-in fingerprint on
  Fathom's own server.
- **What a refused server still sees.** SQLAlchemy runs a few read-only setup queries (server
  version, settings) on a new connection before this listener fires. So a connection the server
  check refuses has still said hello and read settings on that server. It hasn't written
  anything.
- **The libpq behaviours** (host lists, `hostaddr` precedence) come from reading libpq's
  documented rules and SQLAlchemy's source, not from connecting to the old server to watch them
  happen.
- **The known limits in section 1:** dynamic imports, the untested `close()`, and pandas URLs
  passed through variables.

## 6. Interview defense

**"Why not just put the old database on a different port and be done with it?"** It would help,
but the old project is a reference that stays untouched, so its port isn't ours to change. Even
then, a stray `.env` could point at whatever port it moved to. The guard encodes what makes the
old database distinct (where it is, and what it contains) instead of hoping nobody types the
wrong number.

**"Your URL check passed every test, so why add a second layer?"** Because the tests only cover
the URL forms I thought of, and the first review found three I hadn't. A URL can't show DNS:
`postgres` can resolve to the Mac through `/etc/hosts`. The server check makes the question "did
I reach the old server?" instead of "does this string look safe?", and only the first question
has a reliable answer.

**Hard: "How do you know the server check works if it has never seen the old server?"** It's
tested by changing the fingerprint to a database the test server does have, which proves the
mechanism: the listener fires on a real connection, the query runs, a match refuses, and the
error reaches the caller. What's unproven is the fingerprint itself on the real old server. That
rests on a read-only catalog query run with `psql` during planning, which showed
`strategy_research` exists there. The honest statement: the mechanism is tested end to end, and
the fingerprint is verified by inspection, not by the test.

**"Why didn't you just use a settings validator?"** It only sees settings. Engines get URLs from
settings today, but Alembic's command-line arguments, scripts and imported code can build URLs
any way they like. Guarding the single function every engine must pass through, and scanning to
keep it that way, covers every source.

**Weaknesses to state plainly:**
- **Dynamic imports aren't detected.** Mitigation: code review, and the server check still runs
  for any engine built through `make_engine`. A raw psycopg2 connection opened through a dynamic
  import would skip both layers.
- **The `close()` on refusal isn't tested.**
- **The CLI tools aren't covered.** The guard doesn't apply to `psql` or `pg_dump`, which the
  restore uses on purpose.

## 7. What comes next

**P2** splits the commit log into one file per commit, so parallel worktrees can't conflict. Then
worktree C (the number checker) starts alongside steps 1–4. Those steps cover dependencies,
schema, the restore and the timestamp conversion. The restore (step 3) is the first time this
guard stands between Fathom and the old database for real. Fathom's side connects through
`make_engine`; the old side is touched only by read-only `pg_dump` and `psql`.
