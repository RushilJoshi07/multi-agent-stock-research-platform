---
paths:
  - "web/**"
---

# Frontend

Applies to: the React app in `web/`.

## Design
- Colors come from light and dark tokens taken from the mockups. No hard-coded colors in components.
- Every screen works on phone and desktop widths.
- Build from the mockups; new screens or features wait in `docs/ideas.md` until v1.

## Honest numbers
- Every number shown traces to a stored source; the UI can show where it came from.
- Missing data shows as "unavailable", never as 0, a dash that looks like a value, or a placeholder number.
- No sample or fake data in shipped screens. Test data lives only in tests.

## API
- The API contract is fixed before frontend and backend work split (see parallel-work.md).
- The dev server proxies `/api/*` to the API; no hard-coded API hosts in components.

## Tests
- Vitest for components; Playwright for the key flow (analyze, report, paper trade).
- After changing code, restart the dev server before checking it in the browser.
