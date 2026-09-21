# PortFlow architecture

## v0.9

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

Every modeled port call owns a branched service dependency graph.

The graph is a deterministic decision-support model, not a normative port procedure. The exact edge set is synthetic and must be configured for the target port/terminal/authority workflow in a production deployment.

Canonical demo graph:

    pilot -> tug -> berth
    berth -> crane -> cargo
    berth -> bunker
    berth -> stores
    berth -> documents
    cargo + documents -> customs
    cargo + customs -> gate
    cargo + bunker + stores + customs + gate -> departure

ServiceStep nodes carry explicit dependency ids and optional resource ids. ServiceResource records track pilots, tugs, berths, cranes, bunker barges, stores teams, document desks, customs teams, and gate teams.

Incidents mutate resource/service state before risk and UI projection:

- delayed
- blocked
- unavailable
- assigned
- ready

Dependency-state propagation continues downstream until no graph state changes remain.


## Standards / local-process boundary

PortFlow distinguishes standardized port-call information exchange from local operational sequencing.

Standards-backed boundary:

- IMO FAL covers arrival, stay, and departure formalities and documentary requirements.
- Maritime Single Window requirements govern electronic exchange with public authorities.
- IMO port-call operational-data guidance supports port- and trade-agnostic data exchange so local processes can be implemented consistently.
- Port Call Optimisation practice relies on continuously updated data from the actual data owners.

Local-model boundary:

- the ordering and dependency of bunker, stores, documents, customs, gate, cargo, and departure can differ by terminal, port, trade, vessel, authority, and contract;
- PortFlow's v0.9 edge set is therefore a canonical demo fixture;
- production use requires a port-specific dependency map before those edges are treated as operational rules.

A Rotterdam-specific implementation pattern supports including bunker completion and cargo completion in departure planning, but PortFlow does not generalize that local practice into a universal legal dependency.

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

The current synthetic resource model supports compound recovery for shared tug and bunker workloads. It compares alternative resources using availability, capacity, existing assignments, and service-specific separation windows, then ranks the resulting plans by projected operational disruption.

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


## Identity and approval boundary

Recovery authority is enforced server-side.

Authentication flow:

opaque bearer credential
  -> SHA-256
  -> constant-time digest comparison
  -> OperatorIdentity
  -> role authorization
  -> recovery apply

Roles:

- viewer: authenticated audit read
- operator: recovery approval
- supervisor: recovery approval

The UI reflects this boundary but does not define it. Calling the API directly cannot bypass the role dependency.

Recovery proposals themselves remain readable without approval authority so planning and execution remain separate capabilities.

## Credential configuration

PORTFLOW_APPROVERS_JSON is a JSON array of records containing:

- token_sha256
- operator_id
- display_name
- role

Only the digest is configured server-side.

docker-compose.prod.yml requires PORTFLOW_APPROVERS_JSON so a production-shaped stack cannot silently start with an open recovery approval path.

The API validates approver configuration at startup.

## Identity-bound audit receipts

RecoveryApplicationReceipt persists the identity and role that authorized the state mutation.

The authority chain is therefore:

observed state
  -> deterministic proposal
  -> state fingerprint
  -> authenticated identity
  -> role authorization
  -> explicit apply
  -> identity-bound durable receipt

This keeps decision support, authority, mutation, and audit as distinct stages.


## Deterministic scenario boundary

Operational demos are expressed as backend-owned ScenarioFixture records.

A scenario is an ordered list of explicit actions:

- INCIDENT
- CONNECTIVITY

The run contract is:

clear synthetic demo state
  -> instantiate canonical harbor
  -> apply actions in declared order
  -> recompute operational state
  -> return harbor + recovery projections

This prevents browser-only scenario logic from becoming a second source of truth.

The Scenario Lab consumes GET /api/v1/scenarios and executes fixture ids through POST /api/v1/scenarios/{scenario_id}/run.

## Browser E2E boundary

Playwright starts isolated API and Vite processes for browser verification.

The Chromium E2E suite covers:

recovery authority:
scenario fixture
  -> React state
  -> recovery proposal
  -> unauthenticated UI authority boundary
  -> bearer identity verification
  -> server-side role authorization
  -> state mutation
  -> durable identity receipt
  -> browser reload/session restoration

data provenance:
synthetic AIS
  -> authenticated recorded-fixture ingest
  -> entity/source provenance update
  -> stale adapter remains blocked
  -> browser reload preserves recorded-source projection

service DAG / shared recovery:
bunker-loss fixture
  -> Bunker Barge 4 unavailable
  -> Aurora + Glory bunker/departure blockage
  -> topological dependency UI
  -> authenticated compound recovery
  -> both affected departures unblocked

The suite uses system Chromium rather than a mocked DOM environment.

## Development transport configuration

Vite uses PORTFLOW_API_TARGET when present and defaults to http://127.0.0.1:8100.

The WebSocket target is derived from the same backend target.

This preserves one backend source for both REST and live harbor stream during isolated development and E2E runs.


## External data provenance boundary

Operational state no longer assumes all data has the same origin.

Entity source binding:

Vessel.source_id
Berth.source_id
PortCall.source_id
WeatherState.source_id
        |
        v
DataSourceProvenance

DataSourceProvenance carries source mode, provider, observation/receipt timestamps, freshness, stale threshold, health, and record count.

HarborOverview carries the active source set.

## Adapter contract

All adapters converge on:

ExternalDataAdapter.snapshot()
        |
        v
AdapterSnapshot
  - adapter_id
  - provenance
  - records

Current implementations:

- RecordedFixtureAdapter
- HttpJsonAdapter

Recorded fixtures support deterministic offline verification.

HttpJsonAdapter supports environment-configured live JSON endpoints and never appears unless a URL is configured.

## Live transport boundary

Live URLs are deployment configuration.

There is no API accepting an arbitrary user-provided URL.

Policy:

- HTTPS for deployed providers
- HTTP only for loopback development
- bounded request timeout
- JSON-object response contract
- observed_at required
- records array required
- stale observation -> STALE
- transport/shape failure -> ERROR

Only healthy, fresh snapshots may cross the ingest boundary.

## Ingest transaction boundary

Ingestion is logically split:

adapter fetch / replay
  -> provenance health check
  -> validate all records
  -> normalize all records
  -> apply records
  -> bind source ids
  -> update active source provenance
  -> durable audit event
  -> persist HarborOverview

Validation happens before mutation.

This prevents a multi-record payload from partially changing harbor state when a later record is malformed.

## Adapter authority and audit

Preview is read-only.

Manual fixture/live snapshot ingest is an operational state mutation and therefore uses the same authenticated operator/supervisor role boundary as recovery execution.

The durable adapter-ingest event records:

- actor_id
- actor_role
- source_id

A viewer can inspect state but cannot trigger ingest.

## Freshness semantics

Current source freshness is recalculated from observed_at when HarborOverview is generated.

For non-synthetic sources:

freshness_seconds = now - observed_at

freshness_seconds > stale_after_seconds
  -> stale=true
  -> health=STALE

Stale source state remains visible so operators can understand what the current model was based on, but stale snapshots cannot be newly ingested.

## Source-truth UI

The Data Feeds panel renders both:

1. current source provenance actually backing harbor state
2. available adapter snapshots that could be ingested

Synthetic, recorded, and live are visually distinct.

The interface never labels a recorded fixture as live.


## Multi-source domain semantics

A data domain is not assumed to have one provider for every entity.

Example after recorded AIS fixture ingest:

- v-aurora -> recorded-ais
- v-glory -> recorded-ais
- remaining modeled vessels -> synthetic-ais

Both recorded-ais and synthetic-ais remain in HarborOverview.data_sources because both actively back entities.

Data source pruning is reference-based:

active source ids =
  vessel source ids
  + berth source ids
  + port-call source ids
  + weather source id

A newly ingested source is removed from the active source list if no modeled entity actually references it.

An adapter snapshot that applies zero records is rejected rather than being presented as the current domain source.

## External-source ownership versus simulation tick

Synthetic background motion/weather generation only owns synthetic-source state.

Vessel movement tick:

source_id == synthetic-ais
  -> synthetic movement allowed

source_id != synthetic-ais
  -> position remains adapter-owned until next adapter observation

Weather tick:

source_id == synthetic-weather
  -> synthetic metocean evolution allowed

source_id != synthetic-weather
  -> metocean values remain adapter-owned

This prevents externally sourced values from being silently modified while retaining a recorded/live provenance label.


## v0.9 service-DAG migration boundary

Older persisted snapshots may contain the previous seven-kind service graph.

On simulator restore, PortFlow verifies the canonical service-kind set independently for every port call. If any persisted call graph lacks v0.9 service kinds, service steps are reconstructed from the persisted port-call state.

This migration prevents an old snapshot from silently projecting an incomplete dependency model after an application upgrade.

The canonical v0.9 graph contains eleven service kinds:

- pilot
- tug
- berth
- crane
- cargo
- bunker
- stores
- documents
- customs
- gate
- departure

## Dependency-truth projection

A branched backend DAG must not be rendered as a fake linear chain.

The React service projection derives topological depth from ServiceStep.dependency_step_ids and groups nodes by dependency stage.

Each non-root node also displays its actual upstream service kinds.

This is a projection of canonical dependency metadata, not a second frontend-owned dependency model.
