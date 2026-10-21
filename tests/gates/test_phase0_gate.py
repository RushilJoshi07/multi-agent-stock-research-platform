"""Phase 0 gate (docs/plan.md, Phase 0 "Done when"): one command starts the database, Redis,
the API and the web app, and the health check is green. The other half, CI passing, is checked
on GitHub Actions.

Run with `make gate PHASE=0`. The stack is left running afterwards.
"""

import json
import subprocess
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.gate

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8001"
WEB = "http://127.0.0.1:5174"
SERVICES = {"postgres", "redis", "api", "web"}


def run(*args: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=timeout)


def compose_services() -> dict[str, dict]:
    out = run("docker", "compose", "ps", "--format", "json").stdout.strip()
    # Compose prints either one JSON array or one JSON object per line, depending on version.
    if out.startswith("["):
        rows = json.loads(out)
    else:
        rows = [json.loads(line) for line in out.splitlines()]
    return {row["Service"]: row for row in rows}


def wait_for_health(status: int, timeout_s: float) -> dict:
    deadline = time.monotonic() + timeout_s
    last = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{API}/health", timeout=5)
            last = (response.status_code, response.text)
            if response.status_code == status:
                return response.json()
        except httpx.HTTPError as exc:
            last = repr(exc)
        time.sleep(0.5)
    pytest.fail(f"/health did not return {status} within {timeout_s}s; last: {last}")


@pytest.fixture(scope="module")
def make_up() -> subprocess.CompletedProcess:
    result = run("make", "up", timeout=900)
    yield result
    # Left running on purpose (CLAUDE.md: leave dev servers running and say which are up).
    services = compose_services()
    print("\nServices left running:")
    for name, row in sorted(services.items()):
        print(f"  {name}: {row['State']} ({row.get('Health') or 'no healthcheck'})")


def test_one_command_starts_the_stack(make_up: subprocess.CompletedProcess) -> None:
    output = f"{make_up.stdout[-3000:]}\n{make_up.stderr[-3000:]}"
    assert make_up.returncode == 0, f"make up failed:\n{output}"


def test_all_four_services_are_running_and_healthy(make_up) -> None:
    services = compose_services()

    assert SERVICES <= services.keys(), f"missing services: {SERVICES - services.keys()}"
    for name in SERVICES:
        assert services[name]["State"] == "running", f"{name}: {services[name]['State']}"
        assert services[name]["Health"] == "healthy", f"{name}: {services[name]['Health']}"


def test_health_is_green(make_up) -> None:
    response = httpx.get(f"{API}/health", timeout=10)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["postgres"]["ok"] is True
    assert int(body["checks"]["postgres"]["version"].split(".")[0]) >= 16
    assert body["checks"]["redis"]["ok"] is True
    print(f"\n/health: {body}")


def test_health_goes_red_when_redis_stops(make_up) -> None:
    try:
        assert run("docker", "compose", "stop", "redis").returncode == 0
        body = wait_for_health(503, timeout_s=30)
        assert body["status"] == "degraded"
        assert body["checks"]["redis"]["ok"] is False
        assert body["checks"]["postgres"]["ok"] is True
        print(f"\n/health with redis stopped: {body}")
    finally:
        # Always restart Redis, even if an assertion above failed.
        run("docker", "compose", "start", "redis")
    wait_for_health(200, timeout_s=60)


def test_web_app_is_served(make_up) -> None:
    response = httpx.get(f"{WEB}/", timeout=10)

    assert response.status_code == 200
    assert '<div id="root">' in response.text


def test_web_app_reaches_the_api_through_its_proxy(make_up) -> None:
    response = httpx.get(f"{WEB}/api/health", timeout=10)

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ok"
