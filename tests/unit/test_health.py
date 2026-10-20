import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event, text

from api.routes.health import describe_error
from core.db import get_engine, make_engine
from core.redis import get_redis, make_redis

# Nothing listens on localhost port 1, so connecting there fails at once. It's localhost,
# so the network guard allows the attempt.
CLOSED_PORT = 1


def test_health_is_green_when_both_services_are_up(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"]["ok"] is True
    assert body["checks"]["redis"]["ok"] is True


def test_health_runs_a_real_select_version(client: TestClient, engine: Engine) -> None:
    statements: list[str] = []

    def record(conn, cursor, statement, parameters, context, executemany) -> None:
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        response = client.get("/health")
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert "SELECT version()" in statements
    with engine.connect() as conn:
        server_version = conn.execute(text("SHOW server_version")).scalar_one()
    reported = response.json()["checks"]["postgres"]["version"]
    print(f"\nreported version: {reported!r}; SHOW server_version: {server_version!r}")
    assert reported == server_version.split()[0]
    assert reported.startswith("16.")


def test_health_pings_redis_on_its_own_named_connection(
    client: TestClient, health_client_name: str, observer: redis.Redis
) -> None:
    def named_clients() -> list[dict]:
        return [c for c in observer.client_list() if c.get("name") == health_client_name]

    # The name is new for this test, so no connection can have it yet. Docker's healthcheck
    # pings on its own unnamed connections and can't create one.
    assert named_clients() == []

    response = client.get("/health")

    assert response.status_code == 200
    entries = named_clients()
    print(f"\nCLIENT LIST entry for {health_client_name}: {entries}")
    assert len(entries) == 1
    assert entries[0]["cmd"] == "ping"


def test_health_is_503_when_postgres_is_down(app: FastAPI, client: TestClient) -> None:
    dead = make_engine(f"postgresql://fathom:secret-pw@127.0.0.1:{CLOSED_PORT}/fathom_test")
    app.dependency_overrides[get_engine] = lambda: dead

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["postgres"]["ok"] is False
    assert body["checks"]["postgres"]["error"]
    assert "secret-pw" not in body["checks"]["postgres"]["error"]
    assert body["checks"]["redis"]["ok"] is True
    print(f"\npostgres error: {body['checks']['postgres']['error']}")


def test_health_is_503_when_redis_is_down(app: FastAPI, client: TestClient) -> None:
    dead = make_redis(f"redis://127.0.0.1:{CLOSED_PORT}/0", client_name="fathom-health-dead")
    app.dependency_overrides[get_redis] = lambda: dead

    response = client.get("/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["redis"]["ok"] is False
    assert body["checks"]["redis"]["error"]
    assert body["checks"]["postgres"]["ok"] is True
    print(f"\nredis error: {body['checks']['redis']['error']}")


def test_describe_error_masks_url_passwords() -> None:
    message = describe_error(ValueError("could not reach postgresql://fathom:hunter2@db:5432/x"))

    assert "hunter2" not in message
    assert message == "ValueError: could not reach postgresql://fathom:***@db:5432/x"
