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

Update 2026-10-21: uv itself is now pinned to **0.12.23** (published 2026-10-03) under the 14-day rule
([0007](0007-dependency-age-14-days.md)). Homebrew had installed 0.13.4, published 2026-10-20, a day
before the check. Homebrew only offers the newest version, so uv 0.12.23 is installed from the
official GitHub release archive, its SHA-256 checked against both the release's `.sha256` file and
GitHub's asset digest, into `~/.local/uv/0.12.23/`, with symlinks in `~/.local/bin` (appended to PATH
in `~/.zprofile`). Homebrew's uv was uninstalled, so only one uv exists. uv 0.12.23 reads the
existing `uv.lock` unchanged (`uv lock --check` passes). The Docker image uses
`ghcr.io/astral-sh/uv:0.12.23`, and CI pins `setup-uv` to 0.12.23 (step 6).
