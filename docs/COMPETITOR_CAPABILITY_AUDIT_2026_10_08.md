# Shorefront market capability audit, 2026-10-08

Scope: vendor-published product claims available publicly on 2026-10-08. This is not an exhaustive survey of every vendor, and not a test of competitors' live licensed systems. An advertised capability does not establish an independent benchmark. The objective is a differentiated real operational product, not a pixel-copy of competing proprietary interfaces.

## Direct and adjacent products

| Vendor / product | Publicly advertised strength | Shorefront's implemented equivalent | Material gap |
| --- | --- | --- | --- |
| Portchain Connect | Berth alignment, digital handshake, notifications, carrier/terminal integration, AIS tracking | Recorded call windows, accountable coordination, provenance, bounded partner projections and acknowledged delivery | Real partner data entitlement and externally accepted berth window agreements; no carrier AIS |
| Portchain Quay | Berth scenario planning, crane/gang allocation, maintenance and proforma scheduling, real-time sharing | New: uncommitted what-if berth/time comparisons; recorded berth horizon, constraints, resources and human decision packets | Crane/gang allocation and model-calibrated optimization absent; advanced work sequencing not offered |
| Awake.AI Port Vision | AIS tracks, JIT predictions, situational map, geofences/weather, chat, port-call collaboration | Geospatial berth/call map, linked incidents/tasks, scoped account roles, change history, coordination | No licensed AIS/weather/geofence feeds, chat/media, JIT model, or predicted traffic |
| PortXchange Synchronizer | Shared evolving ETA/ETD information and port-call stakeholder collaboration | Two-clock recorded history, ETA/ETD planning, commitments/handoffs, reconciled partner exports | No actual subscribed external stakeholder network or live event exchange |
| Kaleris / Navis N4 | Full terminal operating system; yard/quay/gate/transport equipment planning and execution | Advisory coordination and source-of-truth record overlay, not TOS | TOS execution, equipment optimization, cargo inventory, yard algorithms are not Shorefront's claimed current scope |
| Tideworks Mainsail / Terminal View | TOS for vessel/yard/gate, 3D terminal digital twin, browser roles and customizations | Geographic map, source-aware operating deck, operational role enforcement | 3D surveyed digital twin, authenticated live equipment telemetry, terminal moves, advanced saved views/hotkeys |
| CyberLogitec OPUS Terminal/M | TOS work orders, vessel/yard/berth planning and 3D operating view | Advisory berth/port-call planning and evidence trail | Cargo/yard/gate work execution and live 3D crane/truck tracking |
| MarineTraffic Fleet Dashboard | Paid AIS fleet positioning, timeline, travel/ETA, notifications | Recorded vessel registry, call timeline, map placements only when sourced | No direct AIS feed, voyage tracking, prediction and alert subscription |

## New verified application capabilities on this branch

- GET /api/v1/readiness: authenticated deterministic review of real stored calls, berth assignment/geography, recorded dimensions, conflict rules, open incidents, tasks, coordination, and recorded port resources. Includes source attribution and knowledge time. Unknowns are named, not filled with fabricated data.
- Authenticated Readiness workspace: call coverage lenses, real source evidence, check-by-check review, actionable links, readable coastal light mode.
- POST /api/v1/plan/what-if: authenticated read-only re-evaluation of an existing active call against its proposed berth/time, using the same recorded constraints as the current plan. No database writes or external messaging.
- Authenticated Plan: side-by-side before/after schedule, conflict descriptions, delta timing, explicit uncommitted label and human-owned edit action.
- All above implemented on operational mode, not merely simulator. Tests use isolated generated customer fixtures, not live customer data.

## Hard technical boundaries

1. No synthetic AIS, metocean, berth limits, marine movements, berth capacity or predictive accuracy may be represented as facts. A position on a basemap only uses explicitly recorded coordinates, never fake real-time vessel location.
2. The what-if tool is not a berth-clearance, navigational safety or equipment dispatch decision. No maritime physical control paths should be created.
3. Customer data cannot be silently seeded for visual fullness. Empty real accounts get guided configuration, not a mock city.
4. Independent acceptance and permitted vendor data require buyer contracts and integration credentials. Neither a beautiful demo nor code-based fixtures can satisfy those gates.
5. Avoid broadening into a full N4/TOS clone before a real design-partner workflow validates buyer need and integration feasibility.

## Product priorities, ranked

| Priority | Testable milestone | External input / gate |
| --- | --- | --- |
| P0 | One real port operator runs a complete call from source to changes, decisions, handoffs and evidence; record completion time and failures | Named design partner and customer data |
| P0 | Real AIS/terminal feed, with licensing, source freshness, replay, outage, source attribution, scope and entitlement | Vendor or customer-provided authorization |
| P0 | Signed-off real deploy: independent security/accessibility review, Firefox/WebKit, capacity test, backup RTO/RPO, offsite encryption | Security/operations assurance |
| P1 | Per-call subscribable changes and configurable decision alerts; enforce origin/role and historical audit | Real notification transport, buyer workflows |
| P1 | Human-approved alternate plan packet with explicit accepted/rejected transition, idempotency, stale-input checks | Operator's process and acceptance criteria |
| P1 | Resource/berth planning allocation tied to actual pilot, tug, gang and crane capacity where recorded | Customer-confirmed resource schema |
| P2 | Historical playback/geofences and weather layers, with time-labeled licensed feeds | Contracted telemetry source, map geometry |
| P2 | Semantic source discrepancy resolution and externally attested evidence | Vendor agreements, external key custody |
| P2 | Optional terminal 3D view only from independently surveyed geometry and known equipment state | Terminal geometry and location source |

## Sources

- Portchain Connect: https://portchain.com/portchain-connect
- Portchain Quay: https://portchain.com/portchain-quay
- Awake.AI Port Vision: https://www.awake.ai/port-vision
- PortXchange terminals: https://port-xchange.com/terminals/
- Kaleris TOS: https://kaleris.com/solutions/terminal-operating-system/
- Tideworks: https://tideworks.com/
- Tideworks Mainsail: https://tideworks.com/mainsail/
- CyberLogitec OPUS Terminal: https://www.cyberlogitec.com/en/sub/solution/port/opus_terminal.php
- CyberLogitec OPUS Terminal M: https://cyberlogitec.com/en/sub/solution/port/opus_terminalM.php
- MarineTraffic Fleet Dashboard: https://support.marinetraffic.com/en/articles/9552751-fleet-dashboard-overview
