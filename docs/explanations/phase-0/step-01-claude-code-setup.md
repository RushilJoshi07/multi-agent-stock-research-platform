# Phase 0 · Step 1: Claude Code setup (build steps 1 and 2)

Commits: `79d788b` (step 1: working agreement and config files), `9db2fd7` (step 2: `.claude/`).
Decision notes: [0004 commit-log hook](../../decisions/0004-commit-log-hook-in-session.md).

## 1. What this does, and what it doesn't

Before any application code exists, Fathom has a fixed working environment for Claude Code.
Every session, including up to three running at once in separate git worktrees, starts from the
same rules, the same permissions and the same hooks, because all of them are files in the repo
rather than settings in someone's head or in one chat.

Three pieces matter most and get the depth here:

- **Permissions** in `.claude/settings.json` decide what Claude Code may do without asking, what
  it must ask about, and what it may never do.
- **The commit-log hook** writes a stub entry after every commit so no commit goes unexplained.
- **The attribution settings** keep Claude Code's default trailers out of commit messages and PRs.

What this does not do: it does not make Claude Code safe on its own. Permissions are a seatbelt
against mistakes, not a security boundary against a determined bypass (see section 5). And none of
this runs outside Claude Code: a commit typed in a plain terminal skips the hook entirely.

## 2. The files, explained

### Step 1 config files (short)

- **`.gitignore`** keeps secrets (`.env`, `.env.*` but not `.env.example`), build output, caches,
  database dumps (`*.dump`), worktrees (`.claude/worktrees/`) and personal Claude settings
  (`.claude/settings.local.json`) out of git. `.Rhistory` is ignored because an empty one appeared
  in `docs/` from an unknown source; ignoring it deletes nothing.
- **`.worktreeinclude`** lists `.env`. A worktree is a fresh checkout, so gitignored files are
  missing; this file tells Claude Code to copy `.env` in, so a parallel session has the API keys.
- **`.env.example`** lists every key the plan needs with placeholder values, grouped by phase. Host
  ports are the old project's plus one (decision 0005). The real `.env` doesn't exist yet.
- **`CLAUDE.md`** is loaded at the start of every session. It imports only `docs/STATUS.md` with
  `@`. It deliberately mentions `docs/plan.md` in backticks instead of importing it, because an
  `@` import loads the whole 375-line plan into every session; sessions read just the current phase.
- **`docs/decisions/0001–0006`** record each approved deviation from the plan and the options
  rejected. CLAUDE.md says these win where they conflict with `docs/plan.md`.

### `.claude/settings.json`: permissions

Claude Code checks every tool call against three lists. **Deny** wins over everything, then
**ask**, then **allow**. Anything that matches none of them asks, which is the default.
Fathom uses only allow and deny; everything else falls through to asking.

**Allowed without asking**, and why each is safe:

| Rule | Why it's allowed |
| --- | --- |
| `Read`, `Glob`, `Grep` | Reading the repo changes nothing. |
| `Bash(git status *)`, `git diff *`, `git log *`, `git show *` | Read-only git inspection. |
| `Bash(git add *)` | Staging only changes the index, and `git restore --staged` undoes it. No history is written. |
| `Bash(make up)`, `make test`, `make test-web`, `make lint`, `make gate *` | The project's own documented commands (they arrive in step 5). They start containers and run tests; none delete data. |
| `Bash(uv run pytest *)`, `uv run ruff *` | Running tests and the linter. See the gap in section 5. |
| `Bash(docker compose ps *)`, `docker compose logs *` | Read-only container status. |

**Asked every time** (by falling through): everything else, and in particular:

- `git commit` and `git push`. The user reviews every step before it's recorded, so these were
  deliberately left out of the allow list. CLAUDE.md adds the order: on "commit", commit and then
  push in the same step.
- `docker compose down`, `rm`, `psql`, `pg_restore`, `brew install`. Each can delete data, spend
  money or change the machine, which CLAUDE.md says to ask about.

**Denied always:**

| Rule | What it prevents |
| --- | --- |
| `Read(**/.env)` | Claude reading the real secrets file, here or in any worktree. Claude never needs the values, only the key names in `.env.example`. |
| `Edit(//Users/rushil/agentic-finance-platform/**)` | Any file edit in the old project. The `//` prefix makes the path absolute; a single `/` would be relative to the settings file. The docs say path rules are checked only for `Edit` and `Read`, so this one rule also covers the Write tool. |
| `Bash(git push --force *)`, `Bash(git push -f *)` | Rewriting `main` on GitHub, which would destroy commits other worktrees have already branched from. |

Two syntax choices: the rules use the form `Bash(git status *)` rather than the older
`Bash(git status:*)`. Both are valid; the docs prefer the space form. The space also matters:
`Bash(ls *)` doesn't match `lsof`.

### `.claude/settings.json`: attribution and plans

```json
"attribution": { "commit": "", "pr": "", "sessionUrl": false },
"plansDirectory": "plans",
```

By default Claude Code adds attribution to what it creates: a `Co-Authored-By` trailer on commits,
a line on pull requests, and a claude.ai session link. The
[settings reference](https://code.claude.com/docs/en/settings-reference) describes
`attribution.sessionUrl` as "Omit the claude.ai session link from cloud and Remote Control commits".
Unverified: that the link appears as a `Claude-Session:` trailer (the doc summary doesn't name it),
and that local sessions never add it (the summary doesn't say).
The plan says commits carry no Co-Authored-By line. An empty string for `commit` and `pr` turns
those off, and `sessionUrl: false` turns off the session link. The older setting
`includeCoAuthoredBy` is deprecated and is ignored once `attribution` is set, so it isn't used.

`plansDirectory` makes plan mode save plan files into the repo's `plans/` folder instead of
`~/.claude/plans/`, so plans are versioned with the code. Claude Code still picks the file name,
so CLAUDE.md says to rename an approved plan to `plans/phase-N-<topic>.md`.

### `.claude/hooks/commit-log-note.sh`

The hook is registered under `PostToolUse` with matcher `Bash`, so Claude Code runs it after every
successful Bash command and passes the call's details as JSON on standard input. The script:

```bash
set -uo pipefail
```
Unset variables and failed pipes are errors, but there is deliberately no `-e`. A hook that crashes
mid-way would surface noise in every session; this one exits quietly (status 0) at each guard instead.

```bash
cmd="$(jq -r '.tool_input.command // ""' <<<"$input")"
grep -Eq '(^|[;&|(]|[[:space:]])git([[:space:]]+-C[[:space:]]+[^[:space:]]+)?[[:space:]]+commit([[:space:]]|$)' <<<"$cmd" || exit 0
```
It pulls the shell command out of the JSON and exits unless that command runs `git commit`. The
pattern requires `git` at the start or after a separator (`;`, `&`, `|`, `(`, a space), allows
`git -C <path> commit`, and requires `commit` as a whole word. That is why `echo committed && git log`
does not match but `git add . && git commit -m x` does.

```bash
grep -q -- '--dry-run' <<<"$cmd" && exit 0
```
A dry run creates no commit, so there's nothing to log.

There's no check for a failed commit, and none is needed: the docs say PostToolUse fires only when
the tool succeeded. A failed Bash command goes to a separate event, `PostToolUseFailure`, which this
hook doesn't listen to.

```bash
cd "${CLAUDE_PROJECT_DIR:?}" || exit 0
sha="$(git rev-parse --short HEAD 2>/dev/null)" || exit 0
```
Claude Code sets `CLAUDE_PROJECT_DIR` for hooks. `:?` makes the script stop rather than run in
the wrong directory if it isn't set.

```bash
git diff-tree --no-commit-id --name-only -r --root HEAD | grep -qv '^docs/explanations/' || exit 0
```
This lists the files in the commit and continues only if at least one is outside
`docs/explanations/`. A commit containing only notes would otherwise ask for a note about the notes,
forever. `--root` makes it work on a repository's very first commit, which has no parent to diff against.

```bash
phase="$(sed -nE 's/^\*\*Current phase:\*\*[[:space:]]*([0-9]+).*/\1/p' docs/STATUS.md ...)"
phase="${phase:-0}"
```
The phase number comes from the `**Current phase:** 0 — Setup` line in STATUS.md, so the note
lands in the right `phase-N/` folder without the hook needing to know the plan.

```bash
grep -q "^## $sha " "$log" && exit 0
```
Dedup: if this commit already has an entry, stop. This makes the hook safe to run twice.

```bash
printf '\n## %s — %s\n%s · %s\n_note pending_\n' ... >>"$log"
jq -n ... '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: "..."}}'
```
It appends a stub (hash, subject, date, files changed) and prints JSON. Claude Code feeds the
`additionalContext` text back into the session, which is how the session is told to replace
`_note pending_` with the real note. The note is then committed with the next commit.

## 3. Decisions and rejected alternatives

**Hook stub plus an in-session note, instead of the old background writer.** The old project used
an untracked `.git/hooks/post-commit` that started a second, headless Claude run for every commit.
It was rejected for three concrete reasons: it needed an OAuth token in the environment, it could
spend up to $1 per commit, and it needed `--setting-sources user` to get around permission prompts
it couldn't answer. More basically, a fresh run sees only the diff, not the conversation, so it can
describe *what* changed but has to guess *why*. The session that made the commit knows why. The
cost of this choice: commits made outside Claude Code get no stub. Reversing it later is cheap,
since the hook is one script. See [decision 0004](../../decisions/0004-commit-log-hook-in-session.md).

**Commit and push ask every time, instead of being allowed.** Allowing them would remove two prompts
per step. It was rejected because the user reviews each step's files before they're recorded, and a
pushed commit is shared history that's awkward to take back. The cost is two extra confirmations per step.

**Only force-push is denied, not all push.** Denying all pushes would make "push after every commit"
impossible from inside Claude Code. A normal push only adds commits, while a force-push can delete
them from GitHub, so only the second is blocked outright.

**Deny reading `.env` instead of trusting the instruction not to.** An instruction can be forgotten
in a long session; a deny rule can't. Claude only ever needs key names, and those are in `.env.example`.

**Protect the old repo with a deny rule, not just the CLAUDE.md sentence.** Same reason: "never
modify it" is a rule the project depends on (Phase 1 restores data from it), so it's enforced, not just stated.

**Note in the next commit, instead of amending the commit it describes.** Amending would put the
note in the same commit, but it changes the hash (so the note would describe a hash that no longer
exists) and rewrites history that has already been pushed.

**Hook in `.claude/settings.json` (committed), not `.git/hooks/` (untracked).** Git hooks aren't
version-controlled, so every clone and worktree would need manual setup, and a new worktree would
silently skip notes. The settings file travels with the repo.

## 4. Concepts introduced

**Permission precedence.** When a tool call matches more than one rule, deny beats ask beats allow.
The practical consequence: a broad allow (like `uv run pytest *`) can be narrowed later by adding a
more specific ask or deny rule, without rewriting the allow.

**Hooks.** Commands Claude Code runs at fixed moments: before a tool call, after it, when a session
starts, and so on. Unlike an instruction in CLAUDE.md, a hook always runs; the model can't forget it.
Its output can feed text back into the session (`additionalContext`), which is how a deterministic
script and the model cooperate here.

**Git worktrees.** Several checkouts of one repository, each on its own branch, in separate folders.
Fathom runs up to three Claude Code sessions this way. Anything that must hold in every session, like
permissions and hooks, therefore has to be committed, not configured by hand in one folder.

**Commit trailers.** Lines at the end of a commit message in `Key: value` form, such as
`Co-Authored-By:`. GitHub reads them (for example, to show co-authors), which is why they're controlled
explicitly instead of left to defaults.

## 5. Verification

**What was tested, and how:**

- The hook script was run by hand with simulated hook input for five cases. A non-commit command
  (`git status`) wrote nothing. Text containing "commit" (`echo committed && git log`) wrote nothing.
  `git commit --dry-run` wrote nothing. A real commit command wrote a stub for `79d788b` and printed
  the context message. Running the same commit again produced no duplicate (still one entry).
- Live: committing step 2 (`9db2fd7`) made Claude Code run the hook on its own. It wrote the `9db2fd7`
  stub and sent the "replace `_note pending_`" message back into the session.
- `settings.json` parsed as valid JSON (`jq empty`), and the script passed `bash -n`.
- Both commit messages were printed with `git log -1 --format=%B` and contain no `Co-Authored-By`
  or `Claude-Session` line.
- `git ls-files` shows 27 tracked files; neither `.env` nor `docs/.Rhistory` is tracked.

**What this does not prove:**

- **The docs-only skip is untested.** No commit so far has touched only `docs/explanations/`.
- **The attribution settings are only partly proven.** Both commit messages were written in full
  by the session, so they show the result is clean but not that the setting is what made it clean.
  The [settings reference](https://code.claude.com/docs/en/settings-reference) says the session
  link is omitted from "cloud and Remote Control commits", so these local commits probably can't
  test `sessionUrl` at all. Unverified: whether a local session ever adds the link.
- **`plansDirectory` is untested.** The docs give no minimum version; the next plan-mode session will show it.
- **Deny rules were not tested by trying to break them.** No test attempted to edit the old repo or
  read `.env`. A combined Bash command that included `ls -la .env` was denied during review, but
  whether that was this rule or the user declining the prompt is unverified. Whether `Read(**/.env)`
  also stops a Bash command like `cat .env` is unverified.

**Known gaps:**

- **`Bash(uv run pytest *)` also matches `uv run pytest -m live`**, which would run tests against
  paid APIs without asking. Today no live tests exist, and pytest-socket (step 3) blocks every
  non-localhost connection anyway, so a live test can't reach the network unless it explicitly opts
  out. That's the backstop, but it's one layer, not two. To be closed before the first live test
  (Phase 2), for example by having live tests skip unless `FATHOM_ALLOW_LIVE=1` is set. A command
  starting with that variable doesn't match the allow rule, so it asks.
- **One Bash call with two commits logs only the last one**, because the hook looks at HEAD once.
  The session-handoff skill's check for unlogged commits catches it.
- **`git commit --amend`** gets a new stub under the new hash, and the old entry keeps a hash that no
  longer exists on the branch.
- **If `jq` is missing,** the hook silently writes nothing. jq 1.7.1 is installed on this machine;
  a new machine needs it.
- **Bash can still change the old repo** (e.g. `git -C /Users/rushil/agentic-finance-platform ...`).
  The Edit deny rule doesn't cover shell commands; the protection there is that such commands aren't
  allowed, so they ask.

## 6. Interview defense

**"Why not just put the rules in the prompt? Why permissions and hooks?"**
Instructions are probabilistic: in a long session the model can forget or misapply one. Permissions
and hooks are enforced by the tool, every time. The project's own principle is "code decides, AI
argues", and this applies it to the build process. The prompt still carries the reasons; the settings
carry the guarantees.

**"Why didn't you just auto-generate commit notes with a model after each commit, like before?"**
I did that in the previous project. It cost up to a dollar per commit, needed a stored OAuth token, and
had to bypass permission prompts because nobody was there to answer them. Worst of all, it only saw the
diff, so it guessed at intent. Moving the trigger into a deterministic hook and the writing into the
session that made the change fixed all three. The tradeoff is that commits made outside Claude Code
aren't covered, and I named that and added a backstop check.

**"Your allow list lets `uv run pytest` run anything. Couldn't that call a paid API?"** (hard)
Yes, as written, `uv run pytest -m live` matches the allow rule. Two things stop it from spending
money today: there are no live tests yet, and pytest-socket blocks every non-localhost connection in
every test run, so a live test fails before it reaches the network unless it explicitly opts out. But
that's one safeguard where I want two, so before the first live test lands I'm gating live tests behind
an environment variable whose command form falls outside the allow rule, which forces a prompt.

**"Isn't denying force-push overkill for a solo project?"**
It's solo, but not single-session: up to three worktrees branch from `main` on GitHub. A force-push
from one of them can delete commits the others are built on. The rule costs nothing until it matters.

**Honest weaknesses, stated plainly:** permissions are a guard against mistakes, not a security
boundary, since a shell command can do what a denied tool can't, unless it's also caught. The attribution
setting is verified only by its result, not in isolation. The hook depends on `jq` and on the STATUS.md
line format.

## 7. What comes next

Step 3 adds the first code: the FastAPI app with `/health`, its tests against real Postgres and Redis,
and pytest-socket, which is the second safeguard the live-test gap above relies on. If this setup were
wrong, it would show up as silent gaps rather than errors: unexplained commits in the log, a Claude
session editing the old repo, or a co-author trailer on a pushed commit. The verification above is the
evidence that, so far, none of those has happened.
