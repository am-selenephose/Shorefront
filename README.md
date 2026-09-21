# PortFlow

PortFlow is a port-call operations control tower for live vessel, berth, weather, incident, delay, connectivity, and schedule state.

## Status

Private portfolio build, v0.4 recovery decision-support core.

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

## Verification

    cd apps/api
    uv run pytest -q

    cd ../web
    npm run build
    npm audit --omit=dev --audit-level=high

Current local verification target:

- 24 backend/domain/API/storage/recovery tests
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
- blocked services: -> 0
- current modeled arrival window preserved
- B15 crane assignment updates to crane-b15-a

Tug failure:

Tug 14 failure affects every modeled call assigned to that tug, not only the incident's initiating vessel.

The recovery engine generates a compound plan that moves the affected Tug 14 workload to Tug 22 and shifts only the window required to maintain the synthetic 45-minute resource separation.

Runtime proof:

- global blocked services: -> 0
- pc-aurora tug state: assigned
- pc-aurora tug resource: tug-22
- downstream departure chain: unblocked

### Recovery APIs

- GET /api/v1/recovery/proposals
- POST /api/v1/recovery/proposals/{proposal_id}/apply
- GET /api/v1/recovery/receipts

## Next engineering milestone

- idempotent offline event spool and replay
- durable action receipts
- berth rescheduling proposal engine
- service dependencies such as pilots, tugs, cranes, bunkers, customs
- deterministic scenario fixture packs
- browser E2E tests
- API/web containerization
- deployment
