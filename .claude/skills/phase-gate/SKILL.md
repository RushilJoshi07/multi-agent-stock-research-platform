---
name: phase-gate
description: Run a phase's gate checks and report pass or fail with evidence. Use when a phase's work is believed complete, or the user asks whether phase N passes its gate.
---

# Phase gate

1. Read the phase's "Done when" in `docs/plan.md` and any approved changes in `docs/decisions/`.
   List each condition separately.
2. For each condition, say how it is checked: an automated test in `tests/gates/`, a CI run, or
   a written walkthrough step for the user. If a condition has no check, say so; don't mark it passed.
3. Run `make gate PHASE=N` and capture the full output. Don't summarize away failures.
4. CI: the user checks the GitHub Actions run for the pushed commit (gh is not installed).
   First confirm the commit is on GitHub (`git fetch`, then `git status` says up to date with
   `origin/main`), and tell the user the commit SHA to look for on the Actions page. Then ask
   for the result; don't assume it.
5. Report a table: condition, how checked, PASS / FAIL / NOT CHECKED, evidence (command and
   the relevant output lines). The gate passes only if every condition is PASS.
6. On pass, with the user's approval, record the result, date and evidence in the
   "Gate results" table in `docs/STATUS.md`. On fail, record nothing as passed; list what's missing.
