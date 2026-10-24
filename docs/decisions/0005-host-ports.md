# 0005 · Host ports 5433 / 6380 / 8001 / 5174

Date: 2026-10-19 · Status: approved

## Context
The old project runs on this machine at the same time: Homebrew Postgres 16 on 5432 (checked
2026-10-19), its API on 8000 (uvicorn was listening there), and its Vite frontend on the
default 5173. Phase 1 restores the old database into Fathom's, so both databases must be up at once.

## Decision
Fathom's host ports are the old ones plus one: Postgres **5433**, API **8001**, web **5174**,
and Redis **6380**. Inside Docker the services keep their standard ports (5432, 8000, 5173, 6379);
only the host side changes.

## Options rejected
- **Stop the old project's Postgres while Fathom runs.** It breaks the Phase 1 restore, which
  reads from the old database and writes to the new one at the same time.
- **Default ports and switch between projects.** The same problem, and an easy way to point a
  command at the wrong database.
- **Redis on 6379.** It was free (the old project has no Redis), but 6380 follows the same
  plus-one rule and won't clash with a Redis installed on the host later.

## Consequences
`.env.example`, Compose and CLAUDE.md use these ports. CI uses the same host ports
(5433 / 6380) for its Postgres and Redis service containers, so the 5432 guard in
`tests/conftest.py` needs no CI exception (updated 2026-10-22, Phase 0 step 6).
