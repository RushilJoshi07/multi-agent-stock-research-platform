# 0002 · Postgres 16 on Debian, restoring only the price and universe tables

Date: 2026-10-19 · Status: approved

## Context
The plan says "PostgreSQL" with no version. The old database (checked 2026-10-19) is
PostgreSQL 16.14, collation libc `en_US.UTF-8`, with the pgvector extension (0.8.6). The only
vector column is `corpus_chunks.embedding`, from literature grounding, which Fathom leaves behind.
The price history lives in `price_bars`: 506 tickers, 2010-01-04 to 2026-09-08, 1,987,174 rows.

## Decision
- Image: `postgres:16.x-bookworm` (Debian), the same major version as the dump, in Compose and CI.
- Phase 1 restores only the price and universe tables with `pg_dump -t` (about 321 MB of 332 MB).

## Options rejected
- **Alpine image.** Its musl locales can sort text differently from the old glibc database,
  which risks inconsistent indexes on restored text columns such as `ticker`.
- **Full dump with a pgvector image.** It would drag in tables and an extension we are leaving behind.
- **A newer major (17 or 18).** It would work, but matching 16 removes one variable from the
  restore. Amazon RDS supports 16, so Phase 6 is unaffected.

## Consequences
The exact tag `postgres:16.14-bookworm` is confirmed (2026-10-20): Docker Hub's API returned
HTTP 200 for it, and the container ran healthy in Phase 0 step 3.
