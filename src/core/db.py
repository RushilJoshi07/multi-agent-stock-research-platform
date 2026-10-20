from functools import lru_cache

from sqlalchemy import Engine, create_engine

from core.config import get_settings

# Fail fast instead of hanging when Postgres is down, so /health answers either way.
CONNECT_TIMEOUT_S = 2


def make_engine(url: str) -> Engine:
    return create_engine(
        url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": CONNECT_TIMEOUT_S},
    )


@lru_cache
def get_engine() -> Engine:
    return make_engine(get_settings().database_url)
