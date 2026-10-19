# 0003 · uv with a committed lockfile

Date: 2026-10-19 · Status: approved

## Context
The old project pins nothing: its `pyproject.toml` has only `>=` floors and there is no
lockfile, so nobody can say which versions its tests passed with. Fathom installs fresh in
Docker, in CI, and in up to three parallel worktrees, and without a lock these drift apart.

## Decision
Use `uv` for the Python environment and commit `uv.lock`. CI runs `uv sync --locked`.
Phase 1 seeds the lock with the exact versions installed in the old venv for the imported
pieces (e.g. pandas 3.0.3, pandas-ta 0.4.71b0, numba 0.61.2, scipy 1.18.0, SQLAlchemy 2.0.51).

## Options rejected
- **pip with `>=` floors, as in the old project.** No reproducibility; the problem above.
- **pip-tools.** Works, but slower and needs a separate compile step; uv does both in one tool
  and has a first-party GitHub Action.

## Consequences
`brew install uv` is needed locally (approved for build step 3).
