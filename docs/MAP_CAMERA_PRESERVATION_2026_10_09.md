# Harbor map camera persistence (2026-10-09)

## Operational problem

The live harbor map rebuilt berth/call markers and unconditionally fitted the camera to verified geographic coordinates whenever the focused call, marker filter, or color theme changed. A control-room operator zooming the harbor lost that camera position after selecting another call.

Reproduction against production showcase before the change:

- After pressing map zoom-in three times, the measured pixel separation between two recorded berth markers was approximately 760px.
- Selecting a different call reduced it to approximately 245px (0.323 of prior distance), proving the camera was reset.

## Correction

- Track a stable signature of the verified port and berth coordinate sets.
- Fit the initial camera only once for a set of coordinates, and refit only if actual coordinates change.
- Always rerender focused-call markers, incidents, filters and CSS theme as before.
- Preserve current zoom and pan when selecting calls, toggling layers, refreshing unchanged records or switching light/dark mode.
- Reset the cached camera signature when the map is destroyed so remounting still centers on the verified geography.
- No new network provider, data entry, imagery substitution or underlying record modification.

## Verification

- Dedicated Playwright browser regression added to e2e-product/map-camera.spec.ts.
- The new browser test failed on the prior production assets and passed with the patch (red/green evidence).
- It checks manual zoom-in followed by a new selected vessel, dark theme, and Exceptions only filter.
- Existing map fullscreen, Quay timeline, schematic fallback, authenticated record workflows and source authority behavior must retain their established test coverage.
- Production data and PostgreSQL volume remain unchanged, with Docker health checks and live browser confirmation required after shipping.

## Unresolved readiness gates

This is a real interaction-quality fix, not proof of a 10/10 product: independent operator acceptance, source integration contracts, realistic load testing, accessible visual audits and working hosted GitHub Actions remain external/open conditions.
