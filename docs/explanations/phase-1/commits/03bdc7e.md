# 03bdc7e — Number checker: non-ASCII minus signs and dashes keep their sign
2026-11-11 · 3 files changed, 56 insertions(+)
Hole 2 from the review: the number regex only knew ASCII "-", so "−0.941" read as 0.941 and
matched a +0.941 claim. The scan now maps six minus-like characters (U+2212, figure/en/em dash,
small and fullwidth hyphen-minus) one-for-one to "-" before parsing, so match positions used by
the self-reference check don't shift. It fails closed: an en-dash range like "2019–2021" now
reads -2021 and is flagged, exactly as an ASCII "2019-2021" already was.
