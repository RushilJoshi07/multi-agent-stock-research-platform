---
paths:
  - "src/backtester/**"
  - "src/research_stats/**"
  - "tests/**/*backtest*"
---

# Backtesting rigor

Applies to: the imported backtester, the significance test, the Backtest lab, pattern detectors.
Adapted from the old project's `backtesting-rigor.md`.

## Sacred Gate 1: no lookahead
At each bar, decisions use only data available up to that bar. Simulate sequentially;
vectorized code makes it easy to peek at the future. Prove it by deliberately attempting
lookahead in a test and confirming the engine prevents it.

## Costs and fills are mandatory
Include transaction costs and realistic fills. A backtest without costs is not a backtest.

## Build on the library
The engine wraps backtesting.py. Don't write a backtesting engine from scratch.

## The control is mandatory
The question is "did it beat random entries at the same trade frequency", not "did it make
money". That comparison is the "chance this is luck" number.

## Multiple comparisons
Testing many patterns guarantees some pass by chance. Count the tests run, correct the
threshold (the imported `research_stats` does this), and disclose the count.
Too few occurrences to judge is reported as exactly that.

## Zero trades is a result, not a crash
A backtest with no trades returns a clean "no trades" result (the old engine crashed on an
empty win rate; Phase 1 fixes it before the backtester becomes an agent tool).

## Determinism
Same inputs, same outputs. The backtester does not reason or decide, and is never called an agent.
