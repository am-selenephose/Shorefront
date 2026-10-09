# Shorefront day/night mode — verification, 2026-10-02

Request: add the first version's opposite contrast as an optional dark mode.
Cream remains the default, and both modes keep the corrected Space Grotesk/Space
Mono typography, layout and mobile navigation. This is a local source change;
it does not authorize or imply a commit, push, deployment or commercial release.

## Implementation

- `apps/web/src/styles.css`: shared semantic roles plus a `data-theme='dark'`
  override. Warm exposure/actions retain ink text; warning badges use the active
  warning surface. Navigation, native controls and keyboard focus adapt too.
- `apps/web/public/theme-init.js` and `apps/web/index.html`: restore the explicit
  `shorefront.theme` preference before visible content or the app module renders.
  The stylesheet precedes initialization in both source and built HTML. Browser
  theme-colour metadata reads the computed canvas token, without another palette.
- `apps/web/src/App.tsx`: accessible pressed-state button, local persistence,
  graceful blocked-storage behavior, no operational command or map remount.
- `apps/web/src/HarborMap.tsx`: update existing raster/label paint and detach stale
  load listeners. Preserve the map instance, viewport and live data sources.
  Explicitly bundle the map worker through Vite's `?worker&url` import, with
  Vite client type declarations in `src/vite-env.d.ts`.
- `apps/web/e2e/shorefront-theme.spec.ts`: default, inverse contrast, keyboard,
  refresh, app-independent restoration, invalid/blocked storage, responsive
  layout, existing-canvas identity and absence of mutating API requests. Live
  canvas screenshots also verify the raster visibly darkens immediately on
  toggle, before reload. Held keyboard/pointer tests cover secondary text.
- `apps/web/playwright.config.ts`: optional `SHOREFRONT_E2E_BUILT=1` uses Vite
  preview for the same suite, with the same isolated test API and credentials.

## Verification status

The new behavior was first tested against the old app: the new test failed
because the Dark mode button did not exist. Development-browser verification
then passed all 17 tests. After the production worker fix and the additional
pressed-state regression test, final results were:

| Check | Result |
|---|---|
| TypeScript: `npm run typecheck` | Passed |
| Test configuration isolation: `npm run test:config` | 1 passed |
| Production build: `npm run build` | Passed; separate worker asset emitted |
| Full Chromium suite against Vite dev | 18 passed in 34.0 seconds |
| Same full Chromium suite against built Vite preview | 18 passed in 25.6 seconds |
| API regression: `uv run pytest -q` | 145 passed in 3.27 seconds; 4 existing deprecation warnings |
| `git diff --check` | Passed |

The first production-preview run exposed an existing packaging issue: the
library's relative worker URL requested a missing asset, and the SPA returned
HTML with status 200. Raster tiles showed up, but vessel markers did not; the two
visual tests timed out waiting for network idle. A dedicated content-type
assertion reproduced this precisely (`text/html`, expected JavaScript). The map
worker is now an explicit bundled asset. Neither the timeout nor the missing
markers was bypassed or reclassified as a passing visual test.

A bounded independent review found no critical/important issues and identified
two minor gaps. The pressed-state secondary text issue was reproduced in the
browser before correction; button-local muted text now follows the pressed ink
foreground, and the toggle's active fill wins over hover. The other gap was
closed with live canvas pixel comparison before reload. A follow-up reviewer
turn was unavailable because of its usage limit; final validation of these
small changes is the primary agent's source review and fresh browser tests.

Sampled operational contrast in the successful production-preview pass: 215 rendered
pairs per mode; minimum 5.706:1 in light and 5.310:1 in dark. These are real
rendered text/background checks, not an exhaustive WCAG audit or a guarantee for
every possible data state, map-tile label or third-party basemap asset.

## Reproduction

From `apps/web`:

```sh
npm run typecheck
npm run test:config
env -u LD_LIBRARY_PATH -u LD_PRELOAD npm run test:e2e
npm run build
env -u LD_LIBRARY_PATH -u LD_PRELOAD SHOREFRONT_E2E_BUILT=1 npm run test:e2e
```

The environment cleanup avoids unrelated host preload/library overrides. Tests
run on local ports 8150/5175 with a temporary SQLite database and test-only
credentials; operational feeds are disabled. Basemap tile requests remain
external. Do not reuse those ports for a parallel test run.

## Evidence and limits

Evidence is retained locally under `.artifacts/theme-switch-2026-10-02/`
(git-ignored), including screenshots, contrast samples and command logs.

- [Dark desktop](../.artifacts/theme-switch-2026-10-02/dark-desktop.png)
- [Light desktop](../.artifacts/theme-switch-2026-10-02/light-desktop.png)
- [Dark mobile](../.artifacts/theme-switch-2026-10-02/dark-mobile.png)
- [Production contrast samples](../.artifacts/theme-switch-2026-10-02/reviewed-built/shorefront-theme-day-and-n-84819-eserve-the-operational-view/theme-text-contrast.json)
- [Map immediately before toggle](../.artifacts/theme-switch-2026-10-02/reviewed-built/shorefront-theme-day-and-n-84819-eserve-the-operational-view/live-map-light.png)
- [Map immediately after toggle, no reload](../.artifacts/theme-switch-2026-10-02/reviewed-built/shorefront-theme-day-and-n-84819-eserve-the-operational-view/live-map-dark.png)

The production desktop views and dark mobile view were also visually inspected:
matching layout/type hierarchy, readable exposure values, visible toggle, and
restored vessel markers/labels on the subdued night map. Test screenshots use
synthetic operations; modeled exposure is not real money or trading activity.

Viewport checks cover desktop 1440, tablet 768 and mobile 375 pixels wide.
No cross-engine or physical-device validation is claimed. The existing large
MapLibre bundle warning and development websocket teardown warnings remain.
The wider [commercial release gates](NEXT.md) are unchanged.

Source checkout: `/home/nur/Projects/shorefront`, branch `feat/shorefront-identity`,
base HEAD `f83dec1e8b5d66f9e18a8693b5eef058e5133f53`. The earlier cream UI changes
and this theme feature remain uncommitted. No push or deployment was performed.
Pre-theme working-file backup: `/tmp/shorefront-theme-backup.bRYS91/` (temporary).
