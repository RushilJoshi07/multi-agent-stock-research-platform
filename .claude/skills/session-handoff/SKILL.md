---
name: session-handoff
description: End a session cleanly. Fill pending commit-log notes, update docs/STATUS.md, and write the next session's opening message. Use at the end of a session, when context passes about 60-70%, or when the user asks for a handoff.
---

# Session handoff

1. **Commit-log notes.** In `docs/explanations/phase-N/commit-log.md`, replace every
   `_note pending_` with a 3–6 line note. Then list commits since the last logged hash
   (`git log --oneline`) that have no entry (e.g. commits made outside Claude Code) and add them.
2. **STATUS.md.** Update `docs/STATUS.md` from facts, not memory: check `git log`, `git status`,
   and which servers are actually up (`docker compose ps`). Update Done, In progress, Next,
   Known issues, Servers currently up, and the "Last updated" line. Only mark something done if
   it was verified; say how.
3. **Uncommitted work.** Report `git status`. Don't commit or push unless the user says so.
4. **Opening message.** Write the next session's first message for the user to paste:
   ```
   Read CLAUDE.md, docs/STATUS.md, the Phase N section of docs/plan.md, and the git log and status.
   Last session: <one line>. Next task: <the next numbered step>.
   Open questions: <any>. Explain your approach before writing anything.
   ```
5. Show the STATUS.md diff and the opening message, then stop.
