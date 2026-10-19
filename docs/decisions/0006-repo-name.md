# 0006 · Repo name `multi-agent-stock-research-platform`

Date: 2026-10-19 · Status: approved

## Context
`docs/plan.md` (Phase 0 and "Day one") says to create a private GitHub repo called `fathom`.
The repo was created as `multi-agent-stock-research-platform`
(`github.com/RushilJoshi07/multi-agent-stock-research-platform`), and `plan.md` was not edited.

## Decision
The repo is `multi-agent-stock-research-platform`. The product is still called Fathom: the
app, Compose project, database (`fathom`), and docs all use "Fathom". Where `plan.md` says the
repo is `fathom`, this note wins.

## Options rejected
- **Rename the repo to `fathom`.** The user chose the descriptive name for the GitHub repo.
- **Edit `plan.md` to match.** It stays as written; deviations live in `docs/decisions/`.

## Consequences
Any command or doc that names the repo (clone URLs, CI badges, worktree paths) uses
`multi-agent-stock-research-platform`.
