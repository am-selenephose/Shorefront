# Full-screen geographic harbor map, 2026-10-08

## User-facing behavior

- The operational Pulse map and the public showcase map now include a visible
  "Full screen" button within the map's existing Layers toolbar.
- Clicking it expands the **same** map section to the entire viewport, keeping
  geographic vector layers, recorded port and berth markers, berth-linked call
  labels, layer filters, source/data boundary and map zoom controls.
- "Exit full screen" restores the embedded map, as does Escape.
- Native browser Fullscreen API is preferred. A viewport-fixed mode is used
  when fullscreen is unavailable or denied (including restricted mobile
  browsers); its Exit and Escape behavior also works.
- MapLibre receives ResizeObserver-triggered resize calls when its container
  changes size. State is retained: selected call, layer toggles, center and zoom
  are not reset merely by entering or leaving fullscreen.
- If no WebGL2 is available, the existing recorded-berth schematic also
  expands. It explicitly does not impersonate geographic vessel positions.
- At 390px viewport width, the tools become a horizontal, scrollable control
  strip, the layer legend remains accessible, and there is an always-visible
  exit path. Normal viewport scrolling is restored when leaving fallback mode.
- Light and dark semantic palettes remain inherited from the existing source
  tokens. This feature adds no continuous animation and no new network API.

## Safety and data handling

- No direct API writes or changes to operational source-of-truth data.
- The fullscreen map shares a single MapLibre instance instead of instantiating
  an alternative map or synthesizing harbor coordinates.
- The layers are the same verified inputs and disclose that berth-linked call
  markers are **not** live AIS vessel locations.

## QA

- New browser regression exercises native fullscreen, layers/legend
  preservation, full-viewport geometry and Escape restoration on desktop.
- Separate browser regression disables fullscreen and WebGL2 deliberately,
  tests the schematic fallback on a 390px mobile viewport, Exit button and
  Escape restoration.
- Existing isolated authenticated operational test opens Pulse and verifies
  map fullscreen enter and exit with real test-created customer records.
- Full operational browser, training/browser, frontend TypeScript, production
  build and web-only production cutover checks are recorded separately after
  release. No testing with customer's real data was required.
