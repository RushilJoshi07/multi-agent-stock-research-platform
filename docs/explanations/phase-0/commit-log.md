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

## a8f660e — Phase 0 step 3: FastAPI health check against real Postgres and Redis
2026-10-20 · 22 files changed, 1687 insertions(+), 12 deletions(-)
Added the Python project, GET /health (real SELECT version() and PING; 200, or 503 with the reason),
the postgres and redis Compose services, and 7 tests against real services.
Why: every later step needs a working app skeleton and a test setup that can't reach the old DB or the internet.
Non-obvious: the PING proof uses a uniquely named Redis connection, because Docker's healthcheck
pings the same server and a command counter can't tell the two apart.

## c5a253f — Session handoff after Phase 0 step 3
2026-10-20 · 2 files changed, 28 insertions(+), 9 deletions(-)
Session handoff: STATUS.md now records step 3 as done and step 4 as next, with step 5's
deselection check and the open question of whether the project skills load in a new session.
Why: STATUS.md is the single source of truth a new session starts from.
Non-obvious: this note is committed alone, as the first real test of the hook's docs-only skip.

## b8655b2 — Phase 0 step 4: empty React app and the 14-day dependency rule
2026-10-21 · 22 files changed, 3612 insertions(+), 81 deletions(-)
Added the empty React app (health status via the Vite proxy, 5 Vitest cases) and the 14-day rule
for every dependency, both lockfiles and the Node runtime.
Why: new releases carry the most risk, and most poisoned ones land in transitive packages.
Non-obvious: ruff 0.16.10 would have rewritten the explainers' partial-line ```python examples
into wrong code, so ruff now checks Python files only. Node 24.21.0 comes from the official
tarball because Homebrew only offers 24.22.0, which is too new.

## b2cdaa9 — Phase 0 step 5: full Compose stack, Makefile and the Phase 0 gate test
2026-10-21 · 17 files changed, 776 insertions(+), 27 deletions(-)
Added the api and web containers, the Makefile and the Phase 0 gate test (6 passed), and pinned
uv 0.12.23 and Python 3.13.16 under the 14-day rule.
Why: Phase 0's "done when" is one command starting everything with a green health check.
Non-obvious: tests/gates/conftest.py fails a gate run whose tests were deselected, because
pyproject's addopts deselects gate tests by default. --renew-anon-volumes recreates every
container on each make up and leaves the old node_modules volume behind (about 137 MB each).

## 6578dd5 — Phase 0 step 5 follow-up: web mounts, stable image IDs, .env exclusion
2026-10-22 · 8 files changed, 535 insertions(+), 25 deletions(-)
Web now mounts only src/ and index.html, with node_modules and config in the image; make up turns off
default build attestations; .dockerignore excludes .env at any depth.
Why: the anonymous-volume design either kept stale packages or recreated every container and leaked a
volume per run, and a web/.env could have been baked into the image.
Non-obvious: every build layer was CACHED yet the image ID still changed, because the provenance
attestation records the build time; provenance: false in compose.yaml had no effect, the env var did.

## 4aa17d5 — Keep .env out of VS Code terminals (python.terminal.useEnvFile: false)
2026-10-22 · 2 files changed, 12 insertions(+)
Committed .vscode/settings.json with python.terminal.useEnvFile set to false.
Why: once a real .env exists, true would load every secret into every VS Code terminal, getting
around the Read(**/.env) deny rule.
Non-obvious: the file appeared on its own (most likely VS Code's Python extension) with the unsafe
value; committing the safe value gives every clone and worktree the same setting.
