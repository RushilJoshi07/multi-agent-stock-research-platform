import uuid
from collections.abc import Iterator

import pytest
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, make_url, text

from api.main import create_app
from core.config import get_settings
from core.db import get_engine, make_engine
from core.redis import get_redis, make_redis

# The old project's Postgres listens on 5432 (docs/decisions/0005). Tests must never reach it.
OLD_PROJECT_PG_PORT = 5432
TEST_DB_NAME = "fathom_test"


def checked_test_db_url() -> str:
    """Return DATABASE_URL_TEST, or stop the whole run before any connection is made if it
    could point at the old project's database or at a non-test database."""
    url = make_url(get_settings().database_url_test)
    port = url.port or OLD_PROJECT_PG_PORT  # no port means libpq's default, 5432
    if port == OLD_PROJECT_PG_PORT:
        pytest.exit(f"DATABASE_URL_TEST uses port {port}, the old project's Postgres. Refusing.")
    if url.database != TEST_DB_NAME:
        pytest.exit(f"DATABASE_URL_TEST database is {url.database!r}, not {TEST_DB_NAME!r}.")
    return url.render_as_string(hide_password=False)


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    eng = make_engine(checked_test_db_url())
    with eng.connect() as conn:
        current = conn.execute(text("SELECT current_database()")).scalar_one()
    if current != TEST_DB_NAME:
        pytest.exit(f"Connected to {current!r}, not {TEST_DB_NAME!r}. Refusing.")
    yield eng
    eng.dispose()


@pytest.fixture
def health_client_name() -> str:
    """A name no other connection has, so CLIENT LIST can find exactly this test's client."""
    return f"fathom-health-test-{uuid.uuid4().hex[:12]}"


@pytest.fixture
def redis_client(health_client_name: str) -> Iterator[redis.Redis]:
    client = make_redis(get_settings().redis_url, client_name=health_client_name)
    yield client
    client.close()


@pytest.fixture
def observer() -> Iterator[redis.Redis]:
    """A separate connection for inspecting Redis, so inspecting never changes what the
    health client's connection last ran."""
    client = make_redis(get_settings().redis_url, client_name="fathom-test-observer")
    yield client
    client.close()


@pytest.fixture
def app(engine: Engine, redis_client: redis.Redis) -> FastAPI:
    app = create_app()
    app.dependency_overrides[get_engine] = lambda: engine
    app.dependency_overrides[get_redis] = lambda: redis_client
    return app


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client
