# Parallel work

Applies to: any session running in a git worktree (`claude --worktree <task>`).

- At most three sessions at once, each on tasks that touch different folders.
- Shared formats and API shapes are written and merged to `main` before parallel work starts.
- One session owns database migrations at a time. Parallel sessions never create migrations.
- Push `main` before starting; new worktrees branch from the remote's `main`.
- Install dependencies inside a new worktree first; it's a fresh checkout.
- Every branch runs the full test suite before it merges. Branches merge one at a time; the
  other sessions update from `main` before continuing.
- The review chat says whether a proposed task is safe to run in parallel.
- Known issue: the per-phase commit log will conflict across worktrees. The fix is decided
  before Phase 1's first parallel split (see `docs/STATUS.md`).
