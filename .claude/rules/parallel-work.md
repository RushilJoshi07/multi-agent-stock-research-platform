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
- Commit-log notes are one file per commit (`docs/explanations/phase-N/commits/<short-sha>.md`,
  decision 0008), so branches never conflict on them. To keep those file names valid:
  merge branches into `main` with `git merge --no-ff`, and update a worktree from `main` by
  merging, never rebasing.
- Worktree sessions don't edit `docs/STATUS.md`; the main session updates it after each merge.
- Before a branch merges, the worktree session fills every pending note and commits them, so no
  note is lost when the worktree is removed. Commit with `git commit` in the worktree's own
  directory, or with `git -C <worktree>`, never `cd <worktree> && git commit`. Don't amend a
  commit that already has a note file.
