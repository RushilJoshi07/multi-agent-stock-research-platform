"""Guard the guard: every Postgres connection in Fathom's Python must go through
core.db.make_engine.

`make_engine` runs the old-database guard (core/db_guard.py). Code that builds its own engine or
opens a driver connection skips it, so this test reads every Python file in the repo (except
installed packages, git internals and other worktrees) and fails on any other way of opening a
Postgres connection. The whole repo, not a list of folders, so a new folder can't escape it. The
old project built engines in three kinds of place (src/data_pipeline/db/session.py,
tests/conftest.py, migrations/env.py); imported code arrives in later steps, and this catches it
without anyone having to remember.

What counts as "another way" (the ways known in our dependencies):
- importing a Postgres driver directly: psycopg2, psycopg (v3), asyncpg, pg8000;
- SQLAlchemy's engine and pool factories, sync and async, imported or called as attributes;
- pandas read_sql* / to_sql given a connection string, which makes pandas build its own engine.
Known limits: a URL string passed to pandas through a variable, and dynamic imports
(`importlib.import_module("psycopg2")`, `getattr(sqlalchemy, "create_engine")`), are not detected.
"""

import ast
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# Directory names skipped anywhere in the tree, and paths (from the root) skipped.
EXCLUDED_NAMES = {".venv", "node_modules", ".git"}
EXCLUDED_PATHS = {Path(".claude") / "worktrees"}
ALLOWED_FILE = ROOT / "src" / "core" / "db.py"

DRIVER_MODULES = {"psycopg2", "psycopg", "asyncpg", "pg8000"}
FACTORIES = {
    "create_engine",
    "engine_from_config",
    "create_pool_from_url",
    "create_async_engine",
    "async_engine_from_config",
    "create_async_pool_from_url",
}
PANDAS_SQL = {"read_sql", "read_sql_query", "read_sql_table", "to_sql"}


def _is_string(node: ast.expr | None) -> bool:
    return isinstance(node, ast.JoinedStr) or (
        isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def find_connection_paths(source: str) -> list[str]:
    """Return one description per way `source` could open a Postgres connection itself."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in DRIVER_MODULES:
                    found.append(f"line {node.lineno}: imports driver {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in DRIVER_MODULES:
                found.append(f"line {node.lineno}: imports from driver {module}")
            for alias in node.names:
                if alias.name in FACTORIES:
                    found.append(f"line {node.lineno}: imports {alias.name} from {module}")
        elif isinstance(node, ast.Call):
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in FACTORIES:
                found.append(f"line {node.lineno}: calls {name}")
            elif name in PANDAS_SQL:
                # pandas' signatures: read_sql*(sql, con), DataFrame.to_sql(name, con).
                con = next((kw.value for kw in node.keywords if kw.arg == "con"), None)
                if con is None and len(node.args) >= 2:
                    con = node.args[1]
                if _is_string(con):
                    found.append(f"line {node.lineno}: {name} with a connection string")
    return found


def scanned_files(root: Path = ROOT) -> list[Path]:
    files = []
    for dirpath, dirnames, filenames in os.walk(root):
        here = Path(dirpath)
        # Prune in place so os.walk never descends into excluded trees.
        dirnames[:] = [
            d
            for d in dirnames
            if d not in EXCLUDED_NAMES and (here / d).relative_to(root) not in EXCLUDED_PATHS
        ]
        files.extend(here / name for name in filenames if name.endswith(".py"))
    return sorted(files)


def test_only_core_db_opens_postgres_connections() -> None:
    offenders = {}
    for path in scanned_files():
        if path == ALLOWED_FILE:
            continue
        found = find_connection_paths(path.read_text())
        if found:
            offenders[str(path.relative_to(ROOT))] = found
    assert not offenders, (
        "These files open Postgres connections without core.db.make_engine, so they skip the "
        f"old-database guard: {offenders}"
    )


def test_the_scan_covers_the_real_repo() -> None:
    files = scanned_files()
    assert ALLOWED_FILE in files
    for folder in ("src", "tests", "scripts"):
        assert any(p.is_relative_to(ROOT / folder) for p in files), f"nothing scanned in {folder}/"


def test_the_scan_reads_new_folders_and_skips_only_the_exclusions(tmp_path: Path) -> None:
    """A folder nobody listed (e.g. old code dropped outside src/) is read; the exclusions,
    and nothing else, are skipped."""
    read = ["loose.py", "new_folder/old_code.py", "src/a.py", ".claude/hooks/x.py"]
    skipped = [
        ".venv/lib/site.py",
        "web/node_modules/pkg/x.py",
        ".git/hooks/x.py",
        ".claude/worktrees/pipeline-import/src/x.py",
    ]
    for rel in read + skipped:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("import psycopg2\n")
    assert scanned_files(tmp_path) == sorted(tmp_path / rel for rel in read)


# The scanner must be able to fail: each of these must be flagged.
BYPASSES = [
    pytest.param("import psycopg2\npsycopg2.connect('dbname=x')", id="psycopg2-import"),
    pytest.param("from psycopg2 import connect", id="psycopg2-from-import"),
    pytest.param("import psycopg2.extras", id="psycopg2-submodule"),
    pytest.param("import psycopg", id="psycopg3"),
    pytest.param("import asyncpg", id="asyncpg"),
    pytest.param("import pg8000.native", id="pg8000"),
    pytest.param("from sqlalchemy import create_engine", id="sqlalchemy-from-import"),
    pytest.param("from sqlalchemy.engine import create_engine", id="sqlalchemy-engine-module"),
    pytest.param("import sqlalchemy as sa\nsa.create_engine('postgresql://x')", id="attr-call"),
    pytest.param("from sqlalchemy import engine_from_config", id="engine-from-config"),
    pytest.param("import sqlalchemy\nsqlalchemy.engine_from_config({})", id="alembic-style"),
    pytest.param("from sqlalchemy import create_pool_from_url", id="pool-from-url"),
    pytest.param(
        "from sqlalchemy.ext.asyncio import create_async_engine", id="async-engine-import"
    ),
    pytest.param("import sqlalchemy.ext.asyncio as a\na.async_engine_from_config({})", id="async"),
    pytest.param("import pandas as pd\npd.read_sql('select 1', 'postgresql://x')", id="read-sql"),
    pytest.param("df.to_sql('t', con=f'postgresql://{h}')", id="to-sql-fstring"),
    pytest.param("pd.read_sql_query(sql='q', con='postgresql://x')", id="read-sql-query-kw"),
]

# And clean code must not be flagged.
CLEAN = [
    pytest.param("from core.db import get_engine, make_engine", id="fathom-engine"),
    pytest.param("from sqlalchemy import Engine, text, select", id="sqlalchemy-types"),
    pytest.param("pd.read_sql('select 1', engine)", id="read-sql-with-engine"),
    pytest.param("df.to_sql('t', con=conn)", id="to-sql-with-connection"),
    pytest.param("with engine.connect() as conn:\n    pass", id="engine-connect"),
]


@pytest.mark.parametrize("source", BYPASSES)
def test_scanner_flags_each_bypass(source: str) -> None:
    assert find_connection_paths(source)


@pytest.mark.parametrize("source", CLEAN)
def test_scanner_passes_clean_code(source: str) -> None:
    assert find_connection_paths(source) == []
