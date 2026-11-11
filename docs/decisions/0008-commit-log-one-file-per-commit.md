# 0008 · Commit-log notes: one file per commit, repo found from the hook's cwd

Date: 2026-10-28 · Status: approved · Amends: [0004](0004-commit-log-hook-in-session.md)

## Context
Decision 0004's hook appends every commit's note to one file per phase,
`docs/explanations/phase-N/commit-log.md`. Phase 1 runs up to three sessions at once in git
worktrees. Each branch would append to the end of the same file, so every merge after the first
would conflict on it. The hook also located the repo through `$CLAUDE_PROJECT_DIR`, and whether
that points at the worktree or the main checkout in a `claude --worktree` session is unverified.
A test showed the old hook writes into whatever repo `$CLAUDE_PROJECT_DIR` names, not the repo
where the commit happened.

## Decision
- Each commit's stub and note go in their own file,
  `docs/explanations/phase-N/commits/<short-sha>.md`: a `# <sha> — <subject>` heading, the date and
  shortstat, then the note. Two branches never create the same file, so merges can't conflict.
- The hook finds the repo from the hook input's `cwd` (`git -C "$cwd" rev-parse --show-toplevel`),
  so a commit made in a worktree gets its file in that worktree. `$CLAUDE_PROJECT_DIR` is only a
  fallback, used when `cwd` is missing.
  - `git -C <path> commit` is followed: the hook uses `<path>`, relative to `cwd`, with `~`
    meaning `$HOME`.
  - Not recognised as commits, so they normally get no stub:
    - a `-C` path containing spaces, or a variable or `$(...)` as the path;
    - more than one `-C`;
    - other options between `git` and `commit` (`-c key=val`, `--no-pager`, `--git-dir`).

    The handoff check finds the missing file. If such a command also carries a heredoc body
    with a line like "fix git commit hook", that line can be taken for the command, and `cwd`'s
    HEAD is used instead. That is usually a no-op, because that commit already has its file.
  - The command is the first line with a `git commit` on it, and its leftmost match there, so
    commit-message text such as "git -C x commit" isn't mistaken for the command.
  - `cd <path> && git commit` isn't followed. Whether the hook input's `cwd` is the directory
    before or after the command is unverified, so `cwd`'s HEAD may be a different commit. The
    hook writes no stub and tells the session to write that note by hand. That includes a
    subshell `(cd x && ...)`, which is safe but stricter than needed. Commit from the repo's own
    directory, or use `-C`.
  - Only a `cd` that starts a command (`cd`, `; cd`, `&& cd`, `(cd`) is detected. `pushd`,
    `{ cd`, or a `cd` inside `if`/`then` falls through. The real commit then usually gets no stub
    (`cwd`'s HEAD already has one), and the handoff check finds it.
  - `--dry-run` counts only among the options before the commit message, so a message that
    mentions it is still a real commit.
- "Already logged" is "the file exists". A second run leaves the file, and any note in it, alone.
- The guards from 0004 stay: only successful `git commit` commands (no `--dry-run`), and no stub
  for commits that only touch `docs/explanations/`. Commits that list no files get no stub
  either: merge commits (including a `--no-ff` merge finished with `git commit`) and
  `--allow-empty` commits.
- Don't `git commit --amend` a commit the hook has stubbed. The amended commit gets a new SHA and
  a new stub, and the old file is left naming a commit that is no longer on any branch. If it
  happens, delete the old file; the handoff skill checks for such orphans.
- Short SHAs must stay valid after a merge, so:
  - branches merge into `main` with `git merge --no-ff`;
  - worktrees update from `main` by merging, never by rebasing. A rebase gives every commit a new
    SHA, and the file names would then point at commits that are no longer on the branch.
- Worktree sessions don't edit `docs/STATUS.md`; the main session updates it after each merge.
- Before a branch merges, its worktree session fills every pending note and commits them (a
  docs-only commit, which the hook skips). Otherwise the last commit's note, which normally ships
  with the next commit, is lost when the worktree is removed.
- The Phase 1 entries already written (a684db2, dc543d1) moved into per-commit files. The Phase 0
  log, `phase-0/commit-log.md`, stays as it is.

## Options rejected
- **Keep one file and resolve conflicts by hand.** Every merge would need the same edit, and a
  mistake loses a note.
- **A `merge=union` driver in `.gitattributes`.** Git would keep both sides' lines without
  conflict, but it can interleave the lines of two entries, and it doesn't fix the wrong-repo
  problem.
- **One log file per branch.** It still needs merging into a phase log later, and notes for one
  phase end up in several places.
- **Notes in the commit message (`git notes`, or amending).** Amending changes the SHA. `git notes`
  aren't pushed or cloned by default, so they would be missing from GitHub and from new
  worktrees.

## Consequences
- Reading a phase's notes in order means listing `commits/` by commit order
  (`git log --format=%h`), not reading one file top to bottom.
- A file is named with the short SHA at the length git chose when the commit was made: 7
  characters for now. With the default `core.abbrev=auto`, git uses longer short SHAs as the
  repo grows, and different clones can pick different lengths. So files are matched to commits by
  prefix (the file's name is a prefix of the commit's full SHA), never by comparing strings with
  today's `%h`.
- The hook's behaviour is tested in `tests/unit/test_commit_log_hook.py` against throwaway repos,
  including a worktree.
