# PortFlow

PortFlow is a port-call operations control tower for live vessel, berth, weather, incident, delay, connectivity, and schedule state.

## Status

Private portfolio build, v0.5 constrained recovery + deployable operations core.

## Product principles

- Operational software first, AI/ML as bounded capabilities.
- Real-time state must remain inspectable and attributable.
- Synthetic demo data must never be presented as real port operations.
- Degraded connectivity is a first-class operating mode.
- Port-call dependencies are modeled explicitly, not hidden behind chat.
- Scenario effects must propagate mechanically through schedule state.
- Operational history must survive restart.

## Monorepo

- apps/api: FastAPI service, simulator, persistence layer, event ledger, incident engine
- apps/web: React + TypeScript operations console
- docker-compose.yml: PostgreSQL development service

## Demo domain

The demo uses a fictionalized Rotterdam-like topology and fully synthetic operational data.

Current modeled vessels include MSC Aurora, Maersk Lima, Ever Glory, Nordic Atlas, Seaway Polaris, and Ocean Nova. Names and IMO values are synthetic demonstration data.

## v0.2 proof

### Durable state

- SQLAlchemy-backed canonical snapshot persistence
- SQLite default for zero-config local use
- PostgreSQL support through DATABASE_URL
- append-only operations event ledger
- persistent incident history
- restart restoration of port-call schedule, incidents, risk, and connectivity state

PostgreSQL persistence has been runtime-tested against the included Postgres 17 container.

### Incident propagation

Available deterministic scenarios:

- pilot boarding delay
- tug unavailable
- berth occupation overrun
- high-wind pilot/tug restriction
- control-center connectivity loss

Example demo:

pc-glory berth overrun +90 min -> B07 occupation extends -> pc-nova overlaps -> 55-minute mechanical berth conflict -> both calls become risk-scored from the updated schedule.

### Scheduling and risk

- mechanical berth conflict detection
- dependency-order validation
- explainable risk scoring
- modeled cost exposure
- 16-hour berth Gantt
- conflict highlighting
- port-call stage timeline
- weather/tide restrictions

### Connectivity

Modes:

FULL -> DEGRADED -> CRITICAL -> OFFLINE_EDGE

Loss of transport does not imply loss of local operational state. Offline-edge mode accumulates queued events for future replay work.

## Run

### API with zero-config SQLite persistence

    cd apps/api
    uv sync --extra dev
    uv run uvicorn portflow_api.main:app --reload --port 8100

### API with PostgreSQL

    sudo docker compose up -d postgres
    cd apps/api
    DATABASE_URL=postgresql+psycopg://portflow:portflow-dev-only@127.0.0.1:55432/portflow uv run uvicorn portflow_api.main:app --reload --port 8100

### Web

    cd apps/web
    npm install
    npm run dev

Open http://localhost:5173.

### Production-shaped container stack

The production-shaped stack runs Postgres, FastAPI, and Nginx/React behind one web origin.

    cp .env.example .env
    # set a strong PORTFLOW_DB_PASSWORD in .env
    sudo docker compose -f docker-compose.prod.yml up -d --build

Default external HTTP port is 8088 and can be changed with PORTFLOW_HTTP_PORT.

The production compose intentionally requires PORTFLOW_DB_PASSWORD instead of shipping a fallback password.

## Verification

    cd apps/api
    uv run pytest -q

    cd ../web
    npm run build
    npm audit --omit=dev --audit-level=high

Current local verification target:

- 26 backend/domain/API/storage/recovery tests
- production web build
- zero production npm vulnerabilities

GitHub Actions workflow is committed. The linked GitHub account currently has Actions disabled at account level, so local verification is the canonical proof until that account setting changes.

## API highlights

- GET /healthz
- GET /api/v1/harbor
- GET /api/v1/events
- GET /api/v1/incidents
- POST /api/v1/incidents
- PATCH /api/v1/incidents/{incident_id}/resolve
- GET /api/v1/berth-conflicts
- GET /api/v1/port-calls/{call_id}/risk
- POST /api/v1/connectivity
- POST /api/v1/demo/reset
- WS /ws/harbor

## v0.3 proof

### Durable offline delivery

- outbound operational events are durably queued while OFFLINE_EDGE
- queue state is persisted separately from the local audit ledger
- reconnect to FULL triggers replay through an explicit delivery adapter
- each successful replay creates a durable ACK receipt
- replay is idempotent: already acknowledged envelopes are not delivered twice
- UI queue count reflects the actual durable spool, not a synthetic timer

Runtime proof:

- 2 events queued during offline incident flow
- 2 events acknowledged on reconnect
- 0 events pending after replay
- max delivery attempts: 1

### Service dependency graph

Each scheduled port call now carries a canonical service chain:

pilot -> tug -> berth -> crane -> cargo -> customs -> departure

The graph has explicit resources and dependency edges. Current synthetic resources include:

- Pilot Alpha / Pilot Bravo
- Tug 14 / Tug 22
- berth resources
- terminal cranes
- Customs Team 1

Incidents change canonical service state:

- pilot delay marks pilot delayed and propagates delay downstream
- tug unavailable marks the assigned tug unavailable and blocks downstream services
- berth conflict blocks the later vessel's berth access and downstream crane/cargo/customs/departure path
- wind restriction blocks pilot/tug movement chains for affected inbound calls

The API exposes an explainable dependency graph for each port call.

### New APIs

- GET /api/v1/replay/pending
- POST /api/v1/replay
- GET /api/v1/replay/receipts
- GET /api/v1/port-calls/{call_id}/dependency-graph

## v0.4 proof

### Recovery proposal engine

PortFlow now evaluates corrective actions without mutating live state.

Current recovery actions:

- reassign a service resource
- move a vessel to a compatible clear berth
- shift an operating window

Each proposal is simulated against a cloned HarborOverview before it is ranked.

Proposal output includes:

- projected total delay minutes
- projected modeled delay exposure
- projected berth conflicts
- projected blocked services
- projected target-call risk
- disruption score
- rationale
- explicit assumptions
- approval-required flag

The engine never auto-applies a proposal.


Each proposal is bound to a recovery-state fingerprint derived from recovery-relevant schedule, active-incident, resource-assignment, and weather-restriction state. If that state changes before approval, the old proposal id becomes stale and apply is rejected.

### Human authority boundary

Recovery execution is a separate explicit action.

Flow:

incident -> generate proposals -> compare projections -> operator approves -> apply -> durable receipt

Applied recovery decisions produce a RecoveryApplicationReceipt with:

- proposal id
- application time
- target port call
- exact actions
- resulting conflicts
- resulting blocked services
- resulting total delay
- resulting modeled cost
- approved_by = human_operator

Receipts are persisted in the SQL operations store and exposed by API.

### Demonstrated recovery cases

Berth overrun:

B07 overrun creates a 55-minute modeled overlap with pc-nova.

Ranked options include:

1. move pc-nova to Berth 15
2. hold pc-nova until B07 clears plus operating buffer

The current synthetic ranking selects Berth 15:

- conflicts: 1 -> 0
- blocked services: incident-blocked chain -> 0
- current modeled arrival window preserved
- B15 crane assignment updates to crane-b15-a

Tug failure:

Tug 14 failure affects every modeled call assigned to that tug, not only the incident's initiating vessel.

The recovery engine generates a compound plan that moves the affected Tug 14 workload to Tug 22 and shifts only the window required to maintain the synthetic 45-minute resource separation.

Runtime proof:

- global blocked services: incident-blocked chain -> 0
- pc-aurora tug state: assigned
- pc-aurora tug resource: tug-22
- downstream departure chain: unblocked

### Recovery APIs

- GET /api/v1/recovery/proposals
- POST /api/v1/recovery/proposals/{proposal_id}/apply
- GET /api/v1/recovery/receipts

## v0.5 proof

### Availability- and capacity-aware resource recovery

Recovery feasibility now considers:

- resource available_from
- resource capacity
- existing service assignments
- synthetic 45-minute pilot/tug separation windows

A third synthetic tug, Tug 31, is available 20 minutes after the initial demo epoch with no pre-existing workload.

For the same Tug 14 failure, the engine currently compares:

Tug 31 plan:

- wait 20 minutes for Tug 31 availability
- move the Tug 14 workload to Tug 31
- projected total delay: 60 minutes
- blocked services after recovery: 0
- disruption score: 75

Tug 22 plan:

- use an already-worked Tug 22 schedule
- shift the Aurora tug window 39 minutes to preserve separation
- projected total delay: 79 minutes
- blocked services after recovery: 0
- disruption score: 94

The lower-disruption Tug 31 plan ranks first. This behavior is regression-tested.

### Recovery-state binding

Proposal ids include a recovery-relevant state fingerprint.

Changing schedule timing, active incidents, resource assignments/status, resource availability/capacity, or movement restrictions changes the fingerprint and invalidates old proposal ids.

Live vessel-map movement and generated timestamps are deliberately excluded so harmless display ticks do not stale an approval.

### Frontend loading

The MapLibre harbor layer is lazy-loaded.

Measured production build:

- initial application JS: about 242 KB minified
- HarborMap/MapLibre path: about 1.01 MB minified, loaded separately
- production npm vulnerabilities: 0

This replaces the previous roughly 1.25 MB synchronous initial JavaScript path.

### Deployable stack

Added:

- FastAPI production Dockerfile
- React multi-stage Node -> Nginx Dockerfile
- Nginx REST + WebSocket reverse proxy
- external /healthz proxy
- docker-compose.prod.yml
- required database secret
- .env.example
- Postgres persistent volume
- API/web health checks

Both images were built from the repository Dockerfiles.

End-to-end stack proof:

Postgres healthy -> API healthy -> Nginx web -> /api/v1/harbor

The stack returned the PortFlow UI, six synthetic vessels, four port calls, service-resource state, and the explicit synthetic-data disclaimer through the web proxy.

On the current Raptor host, Docker build-stage DNS required manual verification with --network=host. That is a host Docker DNS issue, not an application dependency or Dockerfile requirement.

## Next engineering milestone

v0.6 should focus on operator identity and external-data boundaries:

- authenticated operator roles for recovery approval
- approval receipts bound to operator identity and role
- deterministic scenario fixture packs
- browser E2E tests
- richer multi-resource / multi-call optimization
- bunker, stores, gate, and additional customs dependencies
- adapter interfaces for AIS, weather/tide, and port-call feeds
- explicit live-vs-synthetic data provenance at adapter boundaries
- deployment configuration for a real hosted demo
