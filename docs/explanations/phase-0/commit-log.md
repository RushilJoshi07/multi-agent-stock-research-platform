# Phase 0 commit log

## 79d788b — Phase 0 step 1: working agreement, status, env template, decisions
2026-10-19 · 12 files changed, 345 insertions(+)
Added the working agreement (CLAUDE.md), STATUS.md, ideas.md, .env.example and the ignore files,
plus decisions 0001–0006 recording where Fathom deviates from docs/plan.md.
Why: every later session starts from these, so they come first.
Non-obvious: CLAUDE.md does not @-import docs/plan.md (it would load in full every session), only
STATUS.md. This entry was added by hand: the commit-log hook didn't exist until step 2.

## 9db2fd7 — Phase 0 step 2: Claude Code settings, commit-log hook, rules, skills, agents
2026-10-20 · 15 files changed, 431 insertions(+), 3 deletions(-)
Added .claude/settings.json, the commit-log hook, six rule files, three skills and two agents.
Why: every session, including parallel worktrees, starts from the same rules and permissions.
Non-obvious: commit and push are deliberately not auto-allowed, so each asks the user. The docs say
path deny rules only apply to Edit/Read, so one Edit(//...) rule protects the old repo from writes.
This commit was the hook's first live run, and it wrote this entry's stub itself.
