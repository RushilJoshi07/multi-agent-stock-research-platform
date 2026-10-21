# 0001 · Python 3.13, not 3.12

Date: 2026-10-19 · Status: approved

## Context
`docs/plan.md` picks Python 3.12 "same as the old project, so its code imports cleanly".
The old project is not on 3.12: its `pyproject.toml` says `requires-python = ">=3.13"` and its
venv runs 3.13.7. Every test of the code we import has only ever passed on 3.13.

## Decision
Fathom uses Python 3.13 (`.python-version`, Docker base image, CI).

Update 2026-10-21: the exact version is **3.13.16** (released 2026-09-30), pinned in
`.python-version` and used everywhere: locally as a uv-managed CPython (the venv's `pyvenv.cfg`
reads `version_info = 3.13.16`), in Docker as `python:3.13.16-slim-bookworm`, and in CI from
`.python-version`. It replaces the system 3.13.7 the venv used before. 3.13.17 (2026-10-21) is too
new under the 14-day rule ([0007](0007-dependency-age-14-days.md)), which now covers the Python runtime.

## Options rejected
- **3.12, as planned.** It would probably work: a grep of `data_pipeline/`, `backtester/`,
  `research_stats/` and `verdict.py` found no 3.13-only APIs, and every dependency allows 3.12.
  But the old tests were never run on 3.12, so this is unproven, and it adds risk for no gain.

## Consequences
The plan's reason for its choice ("same as the old project") is kept; only the version number changes.
