import re
import time
from typing import Annotated, Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import Engine, text

from core.db import get_engine
from core.redis import get_redis

router = APIRouter()

_PG_VERSION = re.compile(r"PostgreSQL (\d+(?:\.\d+)*)")
_URL_PASSWORD = re.compile(r"://([^:/@\s]+):[^@\s]+@")


def describe_error(exc: Exception) -> str:
    """First line of the exception, with any password in a connection URL masked."""
    lines = str(exc).splitlines()
    message = _URL_PASSWORD.sub(r"://\1:***@", lines[0] if lines else "")
    return f"{type(exc).__name__}: {message}"


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000, 1)


def check_postgres(engine: Engine) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            full = conn.execute(text("SELECT version()")).scalar_one()
    except Exception as exc:
        return {"ok": False, "error": describe_error(exc)}
    match = _PG_VERSION.match(full)
    version = match.group(1) if match else full
    return {"ok": True, "version": version, "latency_ms": _elapsed_ms(start)}


def check_redis(client: Redis) -> dict[str, Any]:
    start = time.perf_counter()
    try:
        client.ping()
    except Exception as exc:
        return {"ok": False, "error": describe_error(exc)}
    return {"ok": True, "latency_ms": _elapsed_ms(start)}


@router.get("/health")
def health(
    engine: Annotated[Engine, Depends(get_engine)],
    redis_client: Annotated[Redis, Depends(get_redis)],
) -> JSONResponse:
    checks = {"postgres": check_postgres(engine), "redis": check_redis(redis_client)}
    ok = all(check["ok"] for check in checks.values())
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ok" if ok else "degraded", "checks": checks},
    )
