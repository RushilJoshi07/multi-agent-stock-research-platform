"""The DATABASE_URL guard: no Fathom engine may point at the old project's Postgres.

The old database is Homebrew Postgres on the Mac's port 5432 (docs/decisions/0005). Inside
Docker, Fathom's own API legitimately connects to `postgres:5432`, so the guard checks host and
port together: port 5432 (or no port, which libpq treats as 5432) is allowed only for the
Compose service `postgres`.
"""

import pytest

import core.db
import core.db_guard
from core.db import make_engine

REFUSED = [
    pytest.param("postgresql://fathom:pw@localhost:5432/fathom", id="localhost-5432"),
    pytest.param("postgresql://fathom:pw@LOCALHOST:5432/fathom", id="localhost-uppercase"),
    pytest.param("postgresql://fathom:pw@127.0.0.1:5432/fathom", id="ipv4-loopback-5432"),
    pytest.param("postgresql://fathom:pw@[::1]:5432/fathom", id="ipv6-loopback-5432"),
    pytest.param("postgresql://fathom:pw@0.0.0.0:5432/fathom", id="all-interfaces-5432"),
    pytest.param("postgresql://fathom:pw@localhost/fathom", id="localhost-no-port"),
    pytest.param("postgresql:///fathom", id="no-host-unix-socket"),
    pytest.param("postgresql://fathom:pw@/fathom?host=/tmp", id="unix-socket-in-query"),
    pytest.param("postgresql://fathom:pw@postgres/fathom?host=localhost", id="query-host-wins"),
    pytest.param("postgresql://fathom:pw@localhost:5433/fathom?port=5432", id="query-port-wins"),
    pytest.param("postgresql://fathom:pw@host.docker.internal:5432/fathom", id="docker-to-mac"),
    pytest.param("postgresql+psycopg2://fathom:pw@localhost:5432/fathom", id="driver-suffix"),
    pytest.param("postgresql://fathom:pw@localhost:5433/strategy_research", id="old-db-name"),
    pytest.param(
        "postgresql://fathom:pw@localhost:5433/strategy_research_test", id="old-test-db-name"
    ),
    pytest.param("postgresql://fathom:pw@postgres:5432/strategy_research", id="old-name-docker"),
    # libpq tries a list of hosts in order, so the first one is the one that matters.
    pytest.param(
        "postgresql://fathom:pw@x/fathom?host=localhost:5432&host=postgres", id="host-list"
    ),
    pytest.param("postgresql://fathom:pw@x/fathom?host=localhost&host=postgres", id="host-list-2"),
    pytest.param("postgresql://fathom:pw@postgres/fathom?host=localhost,postgres", id="host-csv"),
    pytest.param(
        "postgresql://fathom:pw@postgres/fathom?host=localhost:5432", id="query-host-port"
    ),
    pytest.param("postgresql://fathom:pw@postgres/fathom?host=[::1]:5432", id="query-ipv6-port"),
    # hostaddr wins over host for where libpq connects; dsn and service can carry a hostaddr.
    pytest.param("postgresql://fathom:pw@postgres:5432/fathom?hostaddr=127.0.0.1", id="hostaddr"),
    pytest.param("postgresql://fathom:pw@postgres/fathom?dsn=hostaddr%3D127.0.0.1", id="dsn"),
    pytest.param("postgresql://fathom:pw@postgres/fathom?service=old", id="service"),
    # The query's dbname replaces the path's database in what psycopg2 is sent.
    pytest.param(
        "postgresql://fathom:pw@localhost:5433/fathom?dbname=strategy_research", id="query-dbname"
    ),
    pytest.param("postgresql://fathom:pw@localhost:5433/fathom?port=abc", id="bad-port"),
]

ALLOWED = [
    pytest.param("postgresql://fathom:pw@postgres:5432/fathom", id="docker-service-5432"),
    pytest.param("postgresql://fathom:pw@postgres/fathom", id="docker-service-no-port"),
    pytest.param("postgresql://fathom:pw@localhost:5433/fathom", id="host-port-5433"),
    pytest.param("postgresql://fathom:pw@127.0.0.1:5433/fathom_test", id="test-db-5433"),
    pytest.param("postgresql://fathom:pw@x/fathom?host=localhost:5433", id="query-host-5433"),
]


@pytest.mark.parametrize("url", REFUSED)
def test_make_engine_refuses_the_old_database(url: str) -> None:
    with pytest.raises(RuntimeError, match="old project's Postgres"):
        make_engine(url)


@pytest.mark.parametrize("url", ALLOWED)
def test_make_engine_allows_fathom_databases(url: str) -> None:
    # create_engine is lazy, so this opens no connection.
    engine = make_engine(url)
    engine.dispose()


def test_refusal_happens_before_any_engine_exists(monkeypatch: pytest.MonkeyPatch) -> None:
    """No engine means no connection pool, so nothing can have connected."""

    def fail_if_called(*args, **kwargs):
        pytest.fail("create_engine was called for a refused URL")

    monkeypatch.setattr(core.db, "create_engine", fail_if_called)
    with pytest.raises(RuntimeError, match="old project's Postgres"):
        make_engine("postgresql://fathom:pw@localhost:5432/fathom")


def test_error_message_hides_the_password() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        make_engine("postgresql://fathom:s3cret-pw@localhost:5432/fathom")
    assert "s3cret-pw" not in str(excinfo.value)


@pytest.mark.parametrize("variable", ["PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
def test_make_engine_refuses_libpq_variables_that_redirect_the_connection(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    monkeypatch.setenv(variable, "127.0.0.1")
    with pytest.raises(RuntimeError, match="old project's Postgres"):
        make_engine("postgresql://fathom:pw@postgres:5432/fathom")


def test_error_message_hides_a_password_in_the_query() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        make_engine("postgresql://fathom@localhost:5432/fathom?password=s3cret-pw")
    assert "s3cret-pw" not in str(excinfo.value)


def test_connecting_checks_which_server_was_reached(
    monkeypatch: pytest.MonkeyPatch, engine
) -> None:
    """Second layer: a URL that passes can still resolve to the old server (an /etc/hosts entry
    for `postgres`, for example). On every new connection, make_engine's engines check that the
    server has no database named like the old project's. Here the marker is set to a name
    Fathom's test server does have, so the check must refuse. The engine is built before the
    marker changes, so the URL check can't be what refuses."""
    guarded = make_engine(engine.url.render_as_string(hide_password=False))
    monkeypatch.setattr(core.db_guard, "OLD_PROJECT_DB_PREFIX", "fathom_test")
    try:
        with pytest.raises(RuntimeError, match="old project's Postgres"):
            with guarded.connect():
                pass
    finally:
        guarded.dispose()


def test_connecting_to_fathoms_own_server_passes_the_server_check(engine) -> None:
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT 1").scalar_one() == 1


def test_error_message_hides_a_password_inside_dsn() -> None:
    with pytest.raises(RuntimeError) as excinfo:
        make_engine("postgresql://fathom@postgres/fathom?dsn=host%3Dx%20password%3Ds3cret-pw")
    assert "s3cret-pw" not in str(excinfo.value)
