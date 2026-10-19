# 0004 · Commit-log note: deterministic hook stub, written by the same session

Date: 2026-10-19 · Status: approved

## Context
The plan wants a short commit-log note after every commit, triggered by a hook in
`.claude/settings.json`. The old project used an untracked `.git/hooks/post-commit` that
started a second, headless `claude -p` run per commit. It needed an OAuth token, a budget of
up to $1 per commit, and `--setting-sources user` to get around permission prompts, and that
run didn't know why the change was made.

## Decision
A PostToolUse hook on Bash (`.claude/hooks/commit-log-note.sh`) detects a `git commit`,
appends a stub (hash, subject, date, shortstat, `_note pending_`) to
`docs/explanations/phase-N/commit-log.md`, and tells the current session to replace the
stub with a 3–6 line note. The note ships with the next commit. Guards: skip if the hash is
already logged (covers failed commits) or if the commit only touched `docs/explanations/`.

## Options rejected
- **The old headless post-commit run.** Extra cost and setup, and less context than the
  session that made the change.

## Consequences
- Commits made outside Claude Code get no stub; the session-handoff skill lists any commits
  missing from the log.
- One shared log file per phase will conflict across parallel worktrees (see STATUS.md
  Known issues); to be fixed before Phase 1's first parallel split.
