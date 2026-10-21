# Dependencies

Applies to: every Python and npm dependency, both lockfiles, and the Node runtime.
Decision and rejected alternatives: `docs/decisions/0007-dependency-age-14-days.md`.

## The 14-day rule
- Every version must have been published at least 14 days (UTC) before the install date. That
  covers direct dependencies, every package in `uv.lock` and `web/package-lock.json`, and the Node
  runtime.
- If the newest version is younger than that, take the latest older one and say so.
- Every proposal shows the publish date next to each pin.
- A security fix younger than 14 days needs an explicit exception from the user, recorded in
  `docs/decisions/`.
- Docker base images are not covered unless the user extends the rule.

## How it's enforced
- Direct dependencies are pinned exactly (`==` in `pyproject.toml`; `save-exact=true` in `web/.npmrc`).
- Lockfiles are committed.
- The transitive tree is cut off by date:
  - uv: `[tool.uv] exclude-newer` in `pyproject.toml` (uv records it in `uv.lock`)
  - npm: `before=` in `web/.npmrc`
- Both dates are the same absolute timestamp. When dependencies change, move both to
  (install date − 14 days) in the same commit as the change.

## Checking
After any dependency change, run `uv run python scripts/check_dependency_age.py` and show its
output. It looks up the publish date of every locked package and exits non-zero if any is past
the cutoff or has no known date.
