---
name: explanation-writer
description: Write teaching explanations of work just completed. A step explainer when a working component is finished, and a phase summary when a phase passes its gate. Use when a component works, a phase completes, or the user asks for an explanation. Every explanation must justify why each choice was made and why the alternatives were rejected.
---

# Explanation writer

Adapted from the old project's skill: "stage" is now "phase", and commit notes come from the hook.

## Purpose
These documents are the user's learning record and interview preparation. Write for a reader
who must be able to rebuild this phase from scratch and defend every line under questioning,
months from now, with no other context. Teach, don't summarize.

## Three levels
1. **Commit note** (3–6 lines per commit): written in-session when the commit-log hook asks,
   in `docs/explanations/phase-N/commit-log.md`. Not this skill's job.
2. **Step explainer** (per working component): `docs/explanations/phase-N/step-<NN>-<component>.md`,
   e.g. `docs/explanations/phase-2/step-03-edgar-client.md`. A component is the smallest piece
   that works on its own: if someone could ask "walk me through how you handled X", X is a
   component. Go deep on this component only; link to other step files instead of repeating them.
3. **Phase summary** (when a phase gate passes): `docs/explanations/phase-N/phase-N-summary.md`.
   Synthesis, not repetition: how the components fit and why the boundaries sit where they do,
   what the gate proved and what it did not, interview defense for the phase, and what breaks
   downstream if this phase is wrong.

## Sections

| Section | Step | Phase summary |
|---|---|---|
| 1. What this does, and what it doesn't | yes | yes |
| 2. Every meaningful line explained | yes | no, link step files |
| 3. Decisions and rejected alternatives | yes | cross-component only |
| 4. Concepts introduced | yes | cross-component only |
| 5. Verification | how this component was tested | the full gate |
| 6. Interview defense | yes | yes |
| 7. What comes next | brief | yes |

Both levels are self-contained: define terms on first use, never write "as we discussed".

## The central requirement
Every explanation answers **"why this and not the other way?"** For every meaningful decision:
what was chosen, the realistic alternatives, **why each alternative was rejected** (the specific
failure it would cause), and what it would cost to change later. A choice described without a
rejected alternative is incomplete. If a decision note exists in `docs/decisions/`, link it.

## Section guidance
- **Lines explained:** what each meaningful line or block does, why it's written that way, and
  what breaks if written differently. Say which bug or bias a line prevents. Name what you skipped as boilerplate.
- **Concepts:** include domain concepts (lookahead bias, survivorship bias, adjusted vs raw
  prices, multiple comparisons, as-of queries), with a concrete example of the failure.
- **Verification:** what was tested, how, what it proves and **what it does not prove**. For the
  three sacred gates (no lookahead, no invented numbers, code acts), be exhaustive, and say loudly if
  a gate is weakly verified.
- **Interview defense:** at least three questions, at least one genuinely hard, at least one
  "why didn't you just do X?", and the honest weaknesses with how to state them confidently.

## Style
Plain language, jargon explained on first use. Prose over bullet fragments for reasoning,
because causality is what's being taught. Be honest about shortcuts and limits. Never assert
something the code doesn't actually do; if the implementation is partial, say which part is missing.
