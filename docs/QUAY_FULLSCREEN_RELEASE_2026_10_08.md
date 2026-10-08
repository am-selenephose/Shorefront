# Shorefront Quay fullscreen capability - 8 October 2026

## What was requested

The user requested a full-screen option on Quay, the berth-occupancy timeline
and planning context, not merely the geographic harbor map. The earlier
map-fullscreen release did not satisfy this requirement.

## Where it works

1. Pulse / Quay Operating Horizon: native or fixed-viewport fullscreen
   alongside selectable 6H / 12H / 24H / 48H recorded time windows. Selecting
   a call continues to update the existing operational focus.
2. Plan / Quay Berth Planning Board: expand real Recorded occupancy windows.
   Original berth rows, vessel call blocks, source information and permitted
   edit action are preserved.
3. Both use QuayFullscreen.tsx for Full screen, Exit full screen and Escape,
   independent of geographic map fullscreen.

## Implementation boundaries

- Native browser fullscreen preferred, fallback when unavailable.
- Light and dark modes share warm peach/orange interaction treatment.
- Scroll inside expanded board; body scroll restored on exit.
- No extra map renderer, API change, hidden data write or synthetic call data.
- Physical vessel clearance is not implied by a berth timeline.

## Verification criteria

- Dedicated Playwright desktop Plan, Pulse timeframe and mobile fallback tests.
- Dedicated npm run test:quay isolated port/database runner.
- Authenticated operator Plan and Pulse Quay tests in test:intelligence.
- Full operational browser suite and image HTTP/TLS checks before cutover.
- Existing PostgreSQL volume and API remain unchanged.

## Source continuity

This work extends published feat/shorefront-v2-convergence at 487cfce from a
clean checkout. Astra's audit source snapshot matched that published commit;
the older original checkout contains separate uncommitted work that must not
be reset or overwritten. Map fullscreen remains independent.
