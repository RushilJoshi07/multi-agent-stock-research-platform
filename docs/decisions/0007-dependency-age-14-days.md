# 0007 · Dependencies must be at least 14 days old, including everything in the lockfiles

Date: 2026-10-20 · Status: approved

## Context
A brand-new release carries the most risk: it may be broken, or it may be a compromised
("poisoned") version of a legitimate package. Most such releases are noticed and pulled or
patched within days. Pinning direct dependencies is not enough, because most poisoned releases
land in transitive packages, the ones a lockfile resolves underneath. Before this rule,
`uv.lock` and `package-lock.json` resolved those to whatever was newest.

## Decision
- Every Python and npm dependency, every package in `uv.lock` and `web/package-lock.json`, and
  the Node runtime must have been published at least 14 days (UTC) before installation. If the
  newest is younger, the latest older version is used and the proposal says so.
- Direct pins are exact.
- The transitive tree is cut off with uv's `exclude-newer` and npm's `before`, set to the same
  absolute timestamp and moved together.
- `scripts/check_dependency_age.py` checks every locked package against the cutoff.
- Rules: `.claude/rules/dependencies.md`.

## Options rejected
- **Always latest.** No buffer at all against a bad release.
- **Version ranges.** The installed tree changes silently between installs.
- **Direct pins only.** Leaves the transitive tree, where most poisoned releases land, unguarded.
- **A rolling duration (uv accepts `14 days`).** The cutoff moves every day without a commit, so
  the reviewed lockfile and a later re-lock can differ. It might also make `uv sync --locked`
  see the lock as stale (unverified). An absolute date moves only in a reviewed commit.
- **A longer delay (30+ days).** Further from security fixes for little extra protection.

## Consequences
- First cutoff: `2026-10-06T23:59:59Z` (set on 2026-10-20).
- ruff 0.17.1 (published 2026-10-15) was downgraded to 0.16.10 (2026-10-01).
- Re-locking with the cutoff downgraded five transitive Python packages: certifi, httptools,
  pluggy, starlette and websockets.
- Node is 24.21.0 (2026-09-07), not 24.22.0 (2026-10-14). Homebrew only offers 24.22.0, so it is
  installed locally from the official nodejs.org tarball, checksum-verified, into
  `~/.local/node/v24.21.0/`.
- Several npm pins sit one patch or minor version behind the newest.
- A security fix younger than 14 days needs an explicit, recorded exception.
