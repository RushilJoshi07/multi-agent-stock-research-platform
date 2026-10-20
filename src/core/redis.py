from functools import lru_cache

import redis

from core.config import get_settings

# The name is set with CLIENT SETNAME on connect, so this connection can be told apart from
# others (e.g. Docker's healthcheck) in CLIENT LIST.
HEALTH_CLIENT_NAME = "fathom-health"
TIMEOUT_S = 2


def make_redis(url: str, client_name: str = HEALTH_CLIENT_NAME) -> redis.Redis:
    return redis.Redis.from_url(
        url,
        client_name=client_name,
        socket_connect_timeout=TIMEOUT_S,
        socket_timeout=TIMEOUT_S,
    )


@lru_cache
def get_redis() -> redis.Redis:
    return make_redis(get_settings().redis_url)
