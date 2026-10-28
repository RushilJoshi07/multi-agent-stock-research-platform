"""Refuse any database URL, or server, that could be the old project's Postgres.

The old database is Homebrew Postgres on the Mac's port 5432, named `strategy_research`
(docs/decisions/0002, 0005). Inside Docker, Fathom's API connects to the Compose service
`postgres` on 5432, so port 5432 alone can't be the test: host and port are checked together.

Two layers:
1. `refuse_old_database(url)`, before an engine exists: the URL and the libpq environment.
2. `refuse_old_server(dbapi_connection)`, on every new connection: what was actually reached.
   It catches what a URL can't show, e.g. an /etc/hosts entry that points `postgres` at the Mac.
"""

import os

from sqlalchemy import URL, make_url

OLD_PROJECT_PG_PORT = 5432
OLD_PROJECT_DB_PREFIX = "strategy_research"
# The only host allowed on port 5432: Fathom's own Compose service. Every other host on 5432
# (localhost, a Unix socket, host.docker.internal from inside a container) reaches, or could
# reach, the Mac's Homebrew server.
COMPOSE_PG_HOST = "postgres"
# libpq options that choose where to connect without being the URL's host, so the host and port
# check can't see them. `hostaddr` wins over `host`; `dsn` and `service` can carry a hostaddr.
REDIRECTING_QUERY_KEYS = ("hostaddr", "dsn", "service")
REDIRECTING_ENV_VARS = ("PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")


class OldDatabaseRefused(RuntimeError):
    pass


def _query_values(url: URL, key: str) -> list[str]:
    """Every value of `key` in the query, split on commas (libpq's multi-host form)."""
    value = url.query.get(key)
    values = value if isinstance(value, tuple) else (value,) if value else ()
    return [part.strip() for item in values for part in item.split(",")]


def _split_host_port(value: str) -> tuple[str, str]:
    """`host:port` in a query host is split by SQLAlchemy's psycopg2 dialect, as here."""
    if value.startswith("["):  # [IPv6]:port
        host, _, rest = value[1:].partition("]")
        return host, rest.removeprefix(":")
    if value.count(":") == 1:
        host, port = value.split(":")
        return host, port
    return value, ""


def _shown(url: URL) -> str:
    """The URL for error messages: password hidden, query left out (it can carry a password in
    `password=` or inside `dsn=`). Each refusal names the query key it objects to."""
    shown = url.set(query={}).render_as_string(hide_password=True)
    return f"{shown}?<query hidden>" if url.query else shown


def refuse_old_database(url: str | URL) -> None:
    """Raise, before any connection exists, if `url` could reach the old database."""
    parsed = make_url(url)
    shown = _shown(parsed)

    def refuse(reason: str) -> None:
        raise OldDatabaseRefused(f"Refusing {shown}: {reason} (the old project's Postgres).")

    for key in REDIRECTING_QUERY_KEYS:
        if key in parsed.query:
            refuse(f"`{key}` in the query can redirect the connection")
    for var in REDIRECTING_ENV_VARS:
        if os.environ.get(var):
            refuse(f"the environment sets {var}, which can redirect the connection")

    # The query's dbname replaces the path's database in what psycopg2 is sent.
    for database in [parsed.database or "", *_query_values(parsed, "dbname")]:
        if database.lower().startswith(OLD_PROJECT_DB_PREFIX):
            refuse(f"database {database!r}")

    # libpq's query host and port override the URL's own and may be lists; it tries each host
    # in turn, so every one must pass. A list is refused outright: nothing in Fathom needs one.
    query_hosts = [_split_host_port(value) for value in _query_values(parsed, "host")]
    query_ports = _query_values(parsed, "port")
    if len(query_hosts) > 1 or len(query_ports) > 1:
        refuse("a list of hosts or ports")
    host, port_text = query_hosts[0] if query_hosts else (parsed.host or "", "")
    port_text = port_text or (query_ports[0] if query_ports else str(parsed.port or ""))
    if port_text and not port_text.isdigit():
        refuse(f"port {port_text!r} is not a number")
    # No port means libpq's default, 5432. No host means a Unix socket, i.e. the local server.
    port = int(port_text) if port_text else OLD_PROJECT_PG_PORT
    if port == OLD_PROJECT_PG_PORT and host.lower() != COMPOSE_PG_HOST:
        refuse(
            f"port {port} on host {host or '(Unix socket)'}; port {port} is allowed only for "
            f"the Compose host {COMPOSE_PG_HOST!r}"
        )


def refuse_old_server(dbapi_connection) -> None:
    """Raise if the server just reached has a database named like the old project's.
    Fathom's server never has one; the old Homebrew server always does."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(
            "SELECT datname FROM pg_database WHERE datname LIKE %s ORDER BY datname LIMIT 1",
            (OLD_PROJECT_DB_PREFIX + "%",),
        )
        row = cursor.fetchone()
    finally:
        cursor.close()
    # psycopg2 opened a transaction for the SELECT; end it so the pool gets an idle connection.
    dbapi_connection.rollback()
    if row:
        raise OldDatabaseRefused(
            f"Connected to a server with database {row[0]!r}: this is the old project's "
            "Postgres. Refusing the connection."
        )
