# Shorefront Living Harbor v1 — developer and operator note

Status: **feature branch / validation**, not production cutover. Canonical source: `am-selenephose/Shorefront`.

## Intent and aesthetic

Deliver the living-harbor direction from the user's golden-hour Shorefront thumbnail: immersive blue maritime setting, warm sunlight and worklights, cyan operational indicators, navy floating HUD cards, and **royal violet / lavender as distinct uncommitted planning-preview colors**. This milestone implements the animated renderer, real interface navigation and read-only operational integration. The scene uses deliberately low-/mid-poly modular Blender geometry and **does not yet match the photographic asset quality** or shoreline detail of the art-direction image.

## Access routes

- `/?showcase=1&living=1#overview`: **isolated public demo** with fictional facts; no operational API session required. This is the canonical visual showcase.
- `/?living=1#overview`: **authenticated operational Living Harbor**, reached after signing in through the existing product. Reads the current installation's actual workspace and team state from existing authenticated parent session. It remains **read-only**. No extra signup, token, custom authentication pathway or parallel data persistence.
- `/`: existing secure operator console. Navigation back is provided in the Living Harbor sidebar.
- `/?showcase=1#pulse`: unchanged legacy public showcase.

## Current scene

Blender 5.2.2 LTS reproducible asset kit (`assets-source/blender/generate_living_harbor.py`) generates optimized embedded-material `.glb` files:

- `harbor_base.glb`: fixed illustrative quay surfaces, container stacks, roads, cranes, worklights and waterfront skyline
- `cargo_ship.glb`
- `tug.glb`
- `pilot.glb`

Browser: React 19 + React Three Fiber + Three.js + Drei, glTF geometry, orthographic perspective, custom shader water with controlled time, slow ambient ship movement, simulated tug/pilot circuit, yard vehicles, glowing lights, clickable cargo vessels and inspector. No realtime AIS is represented. A source-backed geographic view remains in the existing operational workspace.

HUD: responsive sidebar, large branded Overview, call panel, berth timeline, resource meters, typed object inspector, navy scene controls and purple **visual-only** proposed berth overlay. Eight navigation surfaces: Overview, Port Calls, Berth Planning, Resources, Operations, Incidents, Reports, Administration. More advanced evidence/recovery functionality remains available through links to existing typed product components.

## Truth and permissions

- The example fictional calls are only in the explicitly selected public demonstration.
- Authenticated **Overview, geographic/records view, Port Calls, Berth Planning, Incidents, Operations coordination and Reports** use the same source-backed workspace records, never the imported demonstration workspace. Scenario/conflict alternatives are offered through existing authorized operational controls; the Living Harbor itself issues no mutations.
- Authenticated path **does not inject fictional calls or decorative support craft**. When spatial coordinates are unavailable, the scene is labelled *illustrative / not navigational / positions illustrative*. Its vessel arrangement is an art/schematic coordinate, **not a real-world position**.
- The client never requests write APIs from scene controls. Operational changes, approvals, and reconciliation must be done through the existing authorized product UI and server policies.
- Mobile and WebGL-unavailable path retains accessible operational record controls. Reduced-motion preference pauses ambient animation by default.
- No autonomous physical execution or authorization is introduced.

## Development verification

```sh
cd apps/web
npm ci
npm run typecheck
npx vite build --config vite.config.ts --outDir /tmp/shorefront-living-build --emptyOutDir
SHOREFRONT_E2E_DIST_DIR=/tmp/shorefront-living-build \
PYTHONPATH=../../apps/api/src npm run test:intelligence
```

The Playwright intelligence suite exercises all eight modes, vessel inspector with source context, read-only preview, accessibility fallback, authenticated access, and unauthenticated denial.

### Observed limitations / follow-up

- Current scene fidelity is **modular stylized 2.5D**; it does not replicate the original cinematic photo reference in terrain detail, materials, vegetation, harbor realism or motion polish. That is a dedicated art-production milestone.
- Browser rendering engines produce ~1MB (minified) dynamic chunks for each Three.js and MapLibre. Profile mobile/GPU performance before release; implement quality presets and asset/LOD budgets.
- Geographic position rendering must remain a separate source-backed feature; never auto-place a vessel at a fictional location while implying it's actual.
- Scenario overlay is presently illustrative only; future design should preview results of an actual recorded read-only what-if packet and explicitly label source scope.
- No customer pilot or licensed metocean/AIS feed is implied.

## Release boundary

This branch must be reviewed and CI-validated separately; do not deploy or replace the current production app until browser coverage, accessibility and visual design review pass.
