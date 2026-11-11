#!/usr/bin/env bash
# PostToolUse(Bash) hook. After a successful `git commit`, write a commit-log stub to its own file,
# docs/explanations/phase-N/commits/<short-sha>.md, and ask the session to replace it with a
# 3-6 line note. One file per commit, so parallel worktrees never edit the same file.
# Design and rejected alternatives: docs/decisions/0004 (the hook), 0008 (one file per commit).
# Tests: tests/unit/test_commit_log_hook.py
set -uo pipefail

input="$(cat)"
cmd="$(jq -r '.tool_input.command // ""' <<<"$input")"

# Act only on a commit. PostToolUse fires only when the Bash command succeeded,
# so a failed commit never gets here.
commit_re='git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)'
# The real command is the first line with a commit on it, and its leftmost match. A commit
# message (-m '...', or a heredoc body on later lines) always comes after it, so text in the
# message such as "git -C x commit" can't be mistaken for the command.
line="$(grep -E "(^|[;&|(]|[[:space:]])$commit_re" <<<"$cmd" | head -n1)"
[[ -n "$line" ]] || exit 0
first="$(grep -oE "$commit_re" <<<"$line" | head -n1)"
# --dry-run counts only among the options before the message: the text after `first`, cut at the
# first quote, so a message that mentions --dry-run is still a real commit.
options="${line#*"$first"}"
options="${options%%[\"\']*}"
grep -Eq -- '(^|[[:space:]])--dry-run([[:space:]]|$)' <<<"$options" && exit 0

# The repo is the one the command ran in: the input's cwd. In a worktree session that is the
# worktree, whatever CLAUDE_PROJECT_DIR says. Fall back to CLAUDE_PROJECT_DIR only if cwd is missing.
cwd="$(jq -r '.cwd // ""' <<<"$input")"
cwd="${cwd:-${CLAUDE_PROJECT_DIR:-}}"
[[ -n "$cwd" ]] || exit 0

# A `cd` before the commit moved the shell somewhere the hook can't see, so cwd's HEAD may be the
# wrong commit. Write nothing and say so (decision 0008: commit from the repo's directory or -C).
before="${cmd%%"$first"*}"
if grep -Eq '(^|[;&|(])[[:space:]]*cd([[:space:]]|$)' <<<"$before"; then
  jq -n '{hookSpecificOutput: {hookEventName: "PostToolUse",
    additionalContext: "This commit ran after a `cd`, so the commit-log hook could not tell which repo it is in and wrote no stub. Write its note by hand at docs/explanations/phase-N/commits/<short-sha>.md in that repo (decision 0008)."}}'
  exit 0
fi

# `git -C <path> commit` commits in <path> (relative to cwd, ~ for $HOME), not in cwd.
dash_c="$(sed -nE 's/^git[[:space:]]+-C[[:space:]]+([^[:space:]]+).*/\1/p' <<<"$first")"
dash_c="${dash_c#[\"\']}"
dash_c="${dash_c%[\"\']}"
[[ "$dash_c" == "~" || "$dash_c" == "~/"* ]] && dash_c="$HOME${dash_c#\~}"
if [[ -n "$dash_c" ]]; then
  [[ "$dash_c" == /* ]] && cwd="$dash_c" || cwd="$cwd/$dash_c"
fi
root="$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)" || exit 0
cd "$root" || exit 0
sha="$(git rev-parse --short HEAD 2>/dev/null)" || exit 0

# Skip commits that only touch docs/explanations/, so note commits don't ask for notes. The file
# list is captured first: piping it into `grep -q`, which stops reading at the first match, makes
# diff-tree die of SIGPIPE on a large commit, and pipefail would then skip that commit.
# Merge and empty commits list no files, so they are skipped too. The -n test is needed because
# a here-string always ends in a newline, and grep -v would select that one empty line.
changed="$(git diff-tree --no-commit-id --name-only -r --root HEAD)" || exit 0
[[ -n "$changed" ]] || exit 0
grep -qv '^docs/explanations/' <<<"$changed" || exit 0

phase="$(sed -nE 's/^\*\*Current phase:\*\*[[:space:]]*([0-9]+).*/\1/p' docs/STATUS.md 2>/dev/null | head -n1)"
phase="${phase:-0}"
note="docs/explanations/phase-$phase/commits/$sha.md"

# Already written (the hook ran twice for the same HEAD): leave it, note and all.
[[ -e "$note" ]] && exit 0
mkdir -p "$(dirname "$note")"

subject="$(git log -1 --format=%s HEAD)"
date="$(git log -1 --format=%cs HEAD)"
stat="$(git show --shortstat --format= HEAD | sed 's/^ *//')"
printf '# %s — %s\n%s · %s\n_note pending_\n' "$sha" "$subject" "$date" "$stat" >"$note"

jq -n --arg sha "$sha" --arg note "$note" '{hookSpecificOutput: {hookEventName: "PostToolUse",
  additionalContext: "Commit \($sha) landed. In \($note), replace the `_note pending_` line with a 3-6 line note: what changed, why, and anything non-obvious. The note ships with the next commit."}}'
