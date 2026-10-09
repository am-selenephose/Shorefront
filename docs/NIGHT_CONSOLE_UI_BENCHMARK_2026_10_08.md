# Night Console v4, design and competitor benchmark (2026-10-08)

## Diagnosis

- Light-only rules in product.css restored Shorefront coastal peach/sunlight
  for bright mode, but did not provide corresponding dark emphasis.
- The 2026-10-07 dark override applied largely monochrome teal surfaces.
- Before fix, the dark active berth-horizon control computed as cream
  RGB(236,234,193) instead of Shorefront's peach RGB(254,175,119).
- Prior dark mode still functioned: this was a visual identity and focus
  hierarchy regression, not a disabled theme or missing business data.

## Sophisticated UI patterns studied

These observations come from public supplier descriptions and published
screenshots/demos, not proprietary access or independently measured benchmarks.

| Supplier | Useful interface capability | Shorefront design implication | Functional boundary |
| --- | --- | --- | --- |
| Portchain Quay | Scenario berth timeline, crane/gang/maintenance overlays, collaborative view | Distinct berth windows, strong currently selected scenario contrast, visible conflict evidence and rapid call switching | Shorefront does not yet optimize crane/gang loads |
| Awake.AI Port Vision | Layered maps, weather/geofences, interactive port calls, chat, task tracking | Treat map as the spatial hub and give every layer a grounded label and interaction; tasks/events stay adjacent | Never fabricate AIS, weather, tracking or external chat data |
| Tideworks Terminal View | 3D operational digital twin, historic playback, detailed equipment moves | Reserve high-contrast detail-on-demand views and visual timeline context | A schematic map is not a real terminal digital twin |
| Kaleris N4 Control Room | Dense role-focused vessel, yard, truck/crane and equipment control, favorite tabs | Differentiate urgent vs contextual information, fast keyboard retrieval, source-aware detail drawer | Shorefront is advisory, not a TOS or equipment dispatch system |
| PortXchange Synchronizer | Continuously coordinated arrival/departure information | Keep source, recorded-at, conflict and accountable recipient/decision visible | External shared event network is not presently connected |
| MarineTraffic | Vessel location/filter/map-centric operational overviews | Interactive map, focused call, search and state legend | No live licensed AIS data yet |

## Design contract

A sophisticated product is not more decorative panels. The sequence must be:
1. What needs attention now?
2. Where and when is it happening?
3. What is the selected call and why is the state uncertain?
4. What source proves this claim?
5. What action can an authorized operator safely take next?

No UI element should imply real vessel positions, weather or commitments not
present in the installation. All actions remain human-authorized.

## Night Console v4 change list

- Coastal palette restored with peach #FEAF77 and sunlight #FED987 even
  on midnight-teal backgrounds; hue is an accent, not a blanket tint.
- Stacked ambient gradients and soft instrumental lighting on surfaces,
  no continuous canvas/GPU animations. Shared CSS remains dark responsive.
- Real-time control-room emphasis in operational sidebar navigation, status
  bar, decision cockpit, focus card, selected arrival runway, berth horizon,
  call timeline, truth ribbon, resource/evidence instrumentation.
- Coordinate and fallback schematic map themes; warm highlight on selected
  berth/call without shifting underlying geospatial facts.
- Coordination graph, progress states, readiness checklist and what-if
  scenario comparison share the same night tokens.
- Native keyboard operation: Control+K / Command+K focuses actual global
  customer-record search; Escape dismisses and clears it.
- Light-theme settings and primary peach CTA are preserved.
- Focus-visible outlines and reduced-motion preference are preserved.

## Objective QA

- Built-in rendered browser asserts actual dark computed colors of selected
  berth controls and active workspace navigation.
- Tests exercise toggling back to light mode.
- Desktop 1536px plus 390px mobile page-width tests and screenshots.
- Authenticated checks on real operational workspace with isolated customer
  records for Readiness and What-if planning.
- Existing full operational, training, delivery tests run before cutover.
- Not claiming independent WCAG certification, load/stress superiority or
  higher UX conversion than competitors. Those require independent research.

## Public references

- Portchain Quay: https://portchain.com/portchain-quay
- Awake.AI Port Vision: https://www.awake.ai/port-vision
- Tideworks Terminal View: https://info.tideworks.com/3d-terminal-view-ipro-demo
- Kaleris N4 Control Room: https://kaleris.com/solutions/terminal-operating-system/container-terminals/
- PortXchange: https://port-xchange.com/terminals/
- MarineTraffic Fleet Dashboard: https://support.marinetraffic.com/en/articles/9552751-fleet-dashboard-overview
