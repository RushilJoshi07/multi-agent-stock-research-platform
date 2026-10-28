from functools import lru_cache

from sqlalchemy import Engine, create_engine, event

from core.config import get_settings
from core.db_guard import refuse_old_database, refuse_old_server

# Fail fast instead of hanging when Postgres is down, so /health answers either way.
CONNECT_TIMEOUT_S = 2


def make_engine(url: str) -> Engine:
    # Every Fathom engine is built here, so this guard covers the API, CLIs, Alembic and tests.
    refuse_old_database(url)
    engine = create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )
    # Second layer: check every new connection's server, which a URL can't show.
    event.listen(engine, "connect", _check_server)
    return engine


def _check_server(dbapi_connection, connection_record) -> None:
    try:
        refuse_old_server(dbapi_connection)
    except Exception:
        dbapi_connection.close()
        raise


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)
