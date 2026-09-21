# PortFlow architecture

## v0.5

Synthetic operations and scenario injection feed a deterministic HarborSimulator.

The simulator owns canonical vessel, berth, port-call, weather, connectivity, and incident state.

Derived engines operate over that state:

- explainable risk engine
- incident propagation engine
- mechanical berth conflict detector
- dependency-order validation

Canonical HarborOverview state is exposed over REST and WebSocket.

OperationsStore persists:

- latest canonical snapshot
- append-only OperationsEvent ledger
- incident rows

The React console renders:

- MapLibre live harbor
- berth allocation Gantt
- port-call critical paths
- scenario controls
- durable event feed
- connectivity state

## Canonical domain primitives

- Vessel
- Berth
- PortCall
- PortCallStage
- WeatherState
- ConnectivityState
- Incident
- OperationsEvent
- HarborOverview

## Persistence

OperationsStore supports SQLite for zero-config local operation and PostgreSQL for the production-shaped path.

A fresh simulator restores directly from the persisted snapshot without losing incident-adjusted schedule state.

## Incident propagation

Pilot delay:
pilot stage shift -> dependent stage shift -> arrival/departure shift -> delay/exposure/risk recalculation.

Berth overrun:
extend current berth occupation -> overlap next scheduled port call -> conflict detector reports overlap -> both calls enter conflict-aware risk scoring.

Wind restriction:
activate movement restriction -> shift inbound pilot sequences -> recalculate all affected calls.

## Connectivity doctrine

FULL -> DEGRADED -> CRITICAL -> OFFLINE_EDGE

The UI communicates transport degradation separately from operational-state availability.

Offline-edge mode currently accumulates queued event count. The next milestone adds a durable spool with replay acknowledgements and idempotency receipts.

## Safety and evidence rules

- synthetic data is labeled synthetic
- derived risk is explainable
- no hidden LLM score is treated as operational fact
- schedule conflicts are mechanical interval overlaps
- event history is append-only
- incident effects remain in the audit trail after resolution


## Durable outbound replay

PortFlow separates two concepts:

1. local operations ledger
2. remote-delivery spool

The local ledger records what happened regardless of connectivity.

When the control-center link is OFFLINE_EDGE, each outbound event is also wrapped as a durable envelope keyed by its event id. Reconnect replays pending envelopes through a delivery adapter. Successful deliveries produce durable replay receipts.

Event id uniqueness plus receipt lookup make replay idempotent for the demo transport path.

## Service/resource graph

Every modeled port call owns a service chain:

pilot -> tug -> berth -> crane -> cargo -> customs -> departure

ServiceStep nodes carry explicit dependency ids and optional resource ids. ServiceResource records track pilots, tugs, cranes, customs teams, and berth assignments.

Incidents mutate resource/service state before risk and UI projection:

- delayed
- blocked
- unavailable
- assigned
- ready

Dependency-state propagation continues downstream until no graph state changes remain.


## Recovery decision support

Recovery is intentionally split into proposal and execution phases.

Proposal phase:

1. clone current HarborOverview
2. apply candidate corrective actions to the clone
3. recompute schedule, services, conflicts, risk, and delay
4. rank projections by disruption score
5. return assumptions and rationale

No proposal mutates live state.

Execution phase:

1. operator selects a proposal
2. current state is checked by regenerating the deterministic proposal id
3. actions are applied
4. service/risk state is recalculated
5. recovery event is appended
6. RecoveryApplicationReceipt is persisted

A proposal becomes stale after its underlying state changes or after it is applied.

Current action primitives:

- REASSIGN_RESOURCE
- MOVE_BERTH
- SHIFT_WINDOW

Current synthetic disruption score:

total delay minutes + 240 per berth conflict + 60 per blocked service + 5 per action

The score is an internal comparison heuristic, not a market price or safety certification.

## Recovery authority

PortFlow does not auto-execute corrective actions.

The authority boundary is explicit:

system may observe -> simulate -> rank -> explain

human operator must approve -> system may apply -> system records receipt

This keeps prediction/optimization separate from operational authority.


## Recovery state binding

Recovery proposal identity is not based on actions alone.

A proposal id includes a hash of a recovery-relevant state fingerprint covering:

- port-call berth and timing state
- delay state
- active incident identity and targets
- service-resource status and assignments
- weather movement restriction state

The fingerprint intentionally excludes continuously changing vessel map position and generated timestamps, so a proposal does not become stale merely because the live display ticked.

If relevant operational state changes before approval, proposal regeneration produces a different id. The old id is rejected as stale/unavailable.


## Resource availability and capacity

Recovery resource feasibility includes:

- available_from
- capacity
- existing service assignments
- separation windows

The current synthetic tug model compares an immediately busier resource against a later-free resource and ranks the resulting compound plans by projected operational disruption.

Resource availability and capacity are part of the recovery state fingerprint, so a plan becomes stale when those constraints change.

## Deployment boundary

The production-shaped deployment is:

client
  -> Nginx web container
      -> static React assets
      -> /api/* -> FastAPI
      -> /ws/* -> FastAPI WebSocket
      -> /healthz -> FastAPI
  -> FastAPI
      -> PostgreSQL

PostgreSQL is not exposed externally in docker-compose.prod.yml.

The public web surface uses one origin, avoiding a production dependency on browser cross-origin API access.
