# Cream-first Shorefront workspace — verification

2026-10-02 · local branch `feat/shorefront-identity` · uncommitted changes.

This is the cream-layout checkpoint. The owner subsequently requested optional
dark mode; cream remains the default. See [day/night verification](THEME_SWITCH_VERIFICATION.md)
for the later implementation, production worker fix and current test results.

## Owner correction and implemented result

The dark-first palette application was rejected. The owner explicitly wanted
pale cream as the base, a different stylish font and a more futuristic/technical
interface. The corrected direction uses exact `#ECEAC1` for the canvas/sidebar,
deep blue-green text, ivory panels, peach actions/exposure, and yellow attention.
The five palette seeds are unchanged; their roles and derived contrast colours
are corrected. See [brand.md](../brand.md).

- Space Grotesk for the UI and Space Mono for short technical annotations.
- Three local WOFF2 files, copyright/licence files and hash provenance; no runtime
  Google Fonts dependency. Latin subsets, not a claim of full language coverage.
- Larger operational body text, geometric headings, tabular metrics, grouped
  summary layout and a full-height modeled-exposure panel.
- Larger schedule bars with matching lane spacing, roomier operational panels,
  light map treatment and shared semantic map-marker colours.
- Navigation remains available on mobile/tablet as a horizontal scroll region.
- Forty-pixel minimum visible control heights on the tested mobile state,
  dark visible focus rings, disabled/hover separation and reduced-motion support.

No API behavior, database/configuration authority, integration contracts or
operator-approval boundaries were changed. KRATIA was not edited.

## Fresh verification

| Command / check | Result |
|---|---|
| `apps/api`: `uv run pytest -q` | 145 passed in 4.27 seconds; 4 existing deprecation warnings |
| `apps/web`: `npm run typecheck` | Passed |
| `apps/web`: `npm run test:config` | 1 passed |
| `apps/web`: `npm run build` | Passed; existing large MapLibre chunk warning |
| `apps/web`: `env -u LD_LIBRARY_PATH -u LD_PRELOAD npm run test:e2e` | 14 passed in Chromium in 24.5 seconds |
| `git diff --check` | Passed |

The changed cream/ink/font tests first failed against the previous dark version;
the pre-existing disabled/reduced-motion/risk regression remained passing.
The final browser suite verifies local fonts actually reach `loaded` state even
when Google Fonts endpoints are blocked, no document overflow at 375/768/1280/1440
pixels, readable operational text sizing, mobile navigation to recovery, control
heights, cream loading state, preserved risk distinction, focus and core workflows.

Computed colour checks cover **118 text/background pairs**, minimum **5.71:1**,
zero below 4.5:1. This is a targeted contrast check, not a full accessibility audit.

Visual captures at desktop 1440 × 1000, tablet 768 × 1024 and mobile 375 × 812
are retained with full-page views. Screenshots use synthetic demo data after the
berth-crunch scenario; displayed exposure is modeled, not real financial activity.
Fonts are local; OpenStreetMap raster tiles still require network access.

## Evidence and limitations

Local evidence directory: `.artifacts/cream-workspace-2026-10-02/` (git-ignored).

- [Desktop](../.artifacts/cream-workspace-2026-10-02/cream-desktop.png)
- [Full workspace](../.artifacts/cream-workspace-2026-10-02/cream-desktop-full.png)
- [Tablet](../.artifacts/cream-workspace-2026-10-02/cream-tablet.png)
- [Mobile](../.artifacts/cream-workspace-2026-10-02/cream-mobile.png)
- [Contrast pairs](../.artifacts/cream-workspace-2026-10-02/operational-text-contrast.json)

The development-server log contains WebSocket ECONNRESET/EPIPE messages during
browser context setup/teardown; the workflow checks passed. These logs are retained
rather than described as warning-free. No deployment or cross-engine reliability
claim follows from this browser run.

Font licensing notices are included, but broader map attribution/data licensing,
commercial onboarding, authorization/atomicity/replay issues, cross-browser QA and
product validation remain separate work. See [NEXT.md](NEXT.md).

No commit, push, PR or deployment was performed for this correction. Temporary
pre-change backup: `/tmp/shorefront-cream-backup.zGJgP7/`. Previous dark screenshots
remain under `.artifacts/coastal-palette-2026-10-02/` as historical evidence only.
