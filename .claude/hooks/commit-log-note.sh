#!/usr/bin/env bash
# PostToolUse(Bash) hook. After a successful `git commit`, append a commit-log stub for the
# current phase and ask the session to replace it with a 3-6 line note.
# Design and rejected alternatives: docs/decisions/0004-commit-log-hook-in-session.md
set -uo pipefail

input="$(cat)"
cmd="$(jq -r '.tool_input.command // ""' <<<"$input")"

# Act only on a commit. PostToolUse fires only when the Bash command succeeded,
# so a failed commit never gets here.
grep -Eq '(^|[;&|(]|[[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)' <<<"$cmd" || exit 0
grep -q -- '--dry-run' <<<"$cmd" && exit 0

cd "${CLAUDE_PROJECT_DIR:?}" || exit 0
sha="$(git rev-parse --short HEAD 2>/dev/null)" || exit 0

# Skip commits that only touch docs/explanations/, so note commits don't ask for notes.
git diff-tree --no-commit-id --name-only -r --root HEAD | grep -qv '^docs/explanations/' || exit 0

phase="$(sed -nE 's/^\*\*Current phase:\*\*[[:space:]]*([0-9]+).*/\1/p' docs/STATUS.md 2>/dev/null | head -n1)"
phase="${phase:-0}"
log="docs/explanations/phase-$phase/commit-log.md"
mkdir -p "$(dirname "$log")"
[[ -f "$log" ]] || printf '# Phase %s commit log\n' "$phase" >"$log"

# Already logged (the hook ran twice for the same HEAD).
grep -q "^## $sha " "$log" && exit 0

subject="$(git log -1 --format=%s HEAD)"
date="$(git log -1 --format=%cs HEAD)"
stat="$(git show --shortstat --format= HEAD | sed 's/^ *//')"
printf '\n## %s — %s\n%s · %s\n_note pending_\n' "$sha" "$subject" "$date" "$stat" >>"$log"

jq -n --arg sha "$sha" --arg log "$log" '{hookSpecificOutput: {hookEventName: "PostToolUse",
  additionalContext: "Commit \($sha) landed. In \($log), replace the `_note pending_` line under it with a 3-6 line note: what changed, why, and anything non-obvious. The note ships with the next commit."}}'
