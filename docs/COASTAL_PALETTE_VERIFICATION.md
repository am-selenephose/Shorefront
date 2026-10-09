# Shorefront coastal palette — local verification

**Historical checkpoint:** the owner rejected the dark-first composition and
requested a pale-cream base plus stylish, futuristic typography. The current
implementation and evidence are in [cream workspace verification](CREAM_WORKSPACE_VERIFICATION.md).
The results below document the earlier implementation, not the current UI.

Date: 2026-10-02. Branch: `feat/shorefront-identity`.
Baseline: `f83dec1e8b5d66f9e18a8693b5eef058e5133f53`.
Palette changes are local and uncommitted at this verification checkpoint.
No source push, pull request, deployment, database migration or KRATIA edit occurred.

## Scope

Applied the owner's five sampled colours to the existing dark-first frontend.
See [brand.md](../brand.md) for the exact reference, roles and contrast rules.
CSS now has one semantic colour authority; MapLibre canvas markers and labels
read those same tokens. Browser theme metadata was updated. The loading
pseudo-element's leftover `K` was corrected to `S`.

No layout redesign, new navigation workflow, theme switch, new dependencies,
font replacement or backend behavior change was introduced.

## Test results

| Check | Result |
|---|---|
| `apps/api`: `uv run pytest -q` | 145 passed; 4 existing dependency/datetime deprecation warnings |
| `apps/web`: `npm run typecheck` | Passed |
| `apps/web`: `npm run test:config` | 1 passed |
| `apps/web`: `npm run build` | Passed; existing large MapLibre chunk warning remains |
| `apps/web`: `env -u LD_LIBRARY_PATH -u LD_PRELOAD npm run test:e2e` | 13 passed in Chromium, 46.8 seconds |
| `git diff --check` | Passed |

Browser runs use isolated temporary databases and test-only credentials. They do
not use live operational feeds. The map still uses external OpenStreetMap tiles;
the tile artwork is not recoloured to five flat brand colours.

### Regression proof

- First palette tests failed against the original rendered blue shell and the
  loading screen's `K` pseudo-element, then passed after implementation.
- Independent review caught disabled recovery hover losing text contrast,
  high/critical Gantt bars collapsing to identical risk styling, and a reduced-
  motion specificity issue. A browser regression reproduced all three failures
  before fixing the CSS. The final 13-test run includes the passing regression.
- That review's follow-up found the three issues resolved and no additional
  concrete palette, token-wiring, cascade or identity regressions.
- Rendered secondary-text contrast: **118 pairs, minimum 5.31:1, zero below
  4.5:1**. This covers selected operational labels, not every possible pixel/state.
- Keyboard focus remains visible; reduced-motion removes the added transitions.
- Desktop 1440 × 1000, tablet 768 × 1024, mobile 375 × 812 viewport captures were
  inspected. Full-page captures also record the incident/recovery state.

## Local evidence

Screenshots, contrast results, initial failing-test logs and final API/browser
logs are retained under `.artifacts/coastal-palette-2026-10-02/` (git-ignored).

- [Desktop](../.artifacts/coastal-palette-2026-10-02/coastal-desktop.png)
- [Tablet](../.artifacts/coastal-palette-2026-10-02/coastal-tablet.png)
- [Mobile](../.artifacts/coastal-palette-2026-10-02/coastal-mobile.png)
- [Full desktop workspace](../.artifacts/coastal-palette-2026-10-02/coastal-desktop-full.png)
- [Computed contrast pairs](../.artifacts/coastal-palette-2026-10-02/operational-text-contrast.json)

Re-run the browser suite to regenerate evidence on another checkout.

## Limits

This completes the selected colour application, not the wider high-end product
redesign or commercial release. Existing dense typography, mobile navigation,
map-data licensing/attribution, comprehensive accessibility, cross-browser testing
and commercial release gates still need their own work. No live port integration
or production readiness is asserted. See [next work](NEXT.md).
