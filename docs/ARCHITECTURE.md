# PortFlow architecture

## v0.3

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
