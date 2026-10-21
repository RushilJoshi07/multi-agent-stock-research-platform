"""Check that every package in uv.lock and web/package-lock.json was published on or before
the dependency cutoff (docs/decisions/0007, .claude/rules/dependencies.md).

Makes read-only HTTPS requests to PyPI and the npm registry, so it runs by hand, not in pytest:

    uv run python scripts/check_dependency_age.py

Exits 1 if any package is newer than the cutoff or has no known publish date.
"""

import json
import sys
import tomllib
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TIMEOUT_S = 30


def read_cutoffs() -> tuple[datetime, datetime]:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text())
    uv_cutoff = datetime.fromisoformat(pyproject["tool"]["uv"]["exclude-newer"])
    npmrc = dict(
        line.split("=", 1)
        for line in (ROOT / "web" / ".npmrc").read_text().splitlines()
        if "=" in line and not line.lstrip().startswith(("#", ";"))
    )
    npm_cutoff = datetime.fromisoformat(npmrc["before"].strip())
    return uv_cutoff, npm_cutoff


def get_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=TIMEOUT_S) as response:
        return json.load(response)


def uv_locked() -> list[tuple[str, str]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return sorted(
        (pkg["name"], pkg["version"])
        for pkg in lock["package"]
        if "registry" in pkg.get("source", {})  # skips the project itself (editable)
    )


def pypi_published(name: str, version: str) -> datetime | None:
    data = get_json(f"https://pypi.org/pypi/{name}/{version}/json")
    times = [f["upload_time_iso_8601"] for f in data.get("urls", [])]
    return datetime.fromisoformat(min(times)) if times else None


def npm_locked() -> list[tuple[str, str]]:
    lock = json.loads((ROOT / "web" / "package-lock.json").read_text())
    found = set()
    for path, entry in lock["packages"].items():
        if not path or entry.get("link"):  # "" is the web/ package itself
            continue
        name = entry.get("name") or path.rsplit("node_modules/", 1)[-1]
        found.add((name, entry["version"]))
    return sorted(found)


def npm_publish_times(name: str) -> dict[str, str]:
    data = get_json(f"https://registry.npmjs.org/{urllib.parse.quote(name, safe='@')}")
    return data.get("time", {})


def check(label: str, cutoff: datetime, dated: list[tuple[str, str, datetime | None]]) -> bool:
    known = [d for d in dated if d[2] is not None]
    unknown = [d for d in dated if d[2] is None]
    too_new = sorted((d for d in known if d[2] > cutoff), key=lambda d: d[2])
    print(f"{label}: {len(dated)} packages, cutoff {cutoff.isoformat()}")
    if known:
        name, version, published = max(known, key=lambda d: d[2])
        print(f"  newest: {name} {version}, published {published.isoformat()}")
    for name, version, published in too_new:
        print(f"  TOO NEW: {name} {version}, published {published.isoformat()}")
    for name, version, _ in unknown:
        print(f"  NO PUBLISH DATE: {name} {version}")
    ok = not too_new and not unknown
    print(f"  {'OK' if ok else 'FAIL'}")
    return ok


def main() -> int:
    uv_cutoff, npm_cutoff = read_cutoffs()
    if uv_cutoff != npm_cutoff:
        print(f"Cutoffs differ: uv {uv_cutoff.isoformat()}, npm {npm_cutoff.isoformat()}")
        return 1

    with ThreadPoolExecutor(max_workers=16) as pool:
        python = uv_locked()
        python_dates = list(pool.map(lambda p: pypi_published(*p), python))

        node = npm_locked()
        names = sorted({name for name, _ in node})
        times = dict(zip(names, pool.map(npm_publish_times, names), strict=True))
        node_dates = [
            datetime.fromisoformat(t) if (t := times[name].get(version)) else None
            for name, version in node
        ]

    ok_python = check(
        "uv.lock", uv_cutoff, [(*p, d) for p, d in zip(python, python_dates, strict=True)]
    )
    ok_node = check(
        "web/package-lock.json",
        npm_cutoff,
        [(*p, d) for p, d in zip(node, node_dates, strict=True)],
    )
    return 0 if ok_python and ok_node else 1


if __name__ == "__main__":
    sys.exit(main())
