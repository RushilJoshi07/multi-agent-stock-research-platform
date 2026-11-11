# 68bacdf — Phase 1 step 10: number checker extracted from old verdict.py (73ae58e)
2026-11-11 · 5 files changed, 623 insertions(+)
The number checker (Sacred Gate 2) lands in `src/fact_check/` as a faithful extraction of the old
`verdict.py` at 73ae58e: `validate_claims`, `scan_for_unreferenced_numbers` and helpers, with the
same logic and 0.01 tolerances. The verdict flow around them stayed behind. 18 of the old 33 tests
came over, plus 2 new NaN tests. The checker takes any object with id/tool_name/is_error/result,
so it never imports the database. The holes the reviewer found are deliberately unfixed in this
commit; the follow-up commits fix them test-first.
